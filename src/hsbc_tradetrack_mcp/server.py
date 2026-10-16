"""HSBC TradeTrack MCP server.

Live lists come from HSBC's public no-login endpoints (see docs/hsbc-api.md); history comes from the
`data` branch of this repo.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import httpx2
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

REPO_URL = "https://github.com/BukeLy/hsbc-tradetrack-mcp"
HSBC_BASE = (
    "https://investments4.personal-banking.hsbc.com.hk/api/"
    "wealth-trade-equity-public-shp-api-hk-hbap-prod-proxy/v0/equities/public/srbp/hk/online/"
)
HISTORY_BASE = "https://raw.githubusercontent.com/BukeLy/hsbc-tradetrack-mcp/data/"
ENDPOINTS = {
    "hot": "top-active-traded-products",
    "top_buy": "top-buying-products",
    "top_sell": "top-selling-products",
    "top_hold": "top-holdings",
}
ASSET_CLASSES = {"US": ["SEC"], "HK": ["SEC", "WRTS"]}
DATE_TYPES = {
    "today": "TODAY",
    "yesterday": "LAST_1_DAY",
    "last_month": "LAST_1_MONTH",
    "last_3_months": "LAST_3_MONTH",
    "last_6_months": "LAST_6_MONTH",
}
HOLDINGS_ONLY_PERIODS = {"last_3_months", "last_6_months"}
MAX_HISTORY_DAYS = 31

try:
    __version__ = version("hsbc-tradetrack-mcp")
except PackageNotFoundError:  # Horizon runs this file without installing the package
    __version__ = "0+unknown"

Market = Literal["US", "HK"]
ListName = Literal["hot", "top_buy", "top_sell", "top_hold"]
Period = Literal["today", "yesterday", "last_month", "last_3_months", "last_6_months"]
ALL_LISTS: list[ListName] = ["hot", "top_buy", "top_sell", "top_hold"]


class Stock(BaseModel):
    symbol: str = Field(description="US ticker, or 5-digit HK stock code such as 00700")
    currency: str | None = None
    rank_today: int | None = Field(None, description="Rank in today's top 10; null when not in it")
    rank_yesterday: int | None = None
    rank_last_month: int | None = None
    rank_last_3_months: int | None = Field(None, description="top_hold only")
    rank_last_6_months: int | None = Field(None, description="top_hold only")
    buy_pct: float | None = Field(None, description="hot: % of HSBC investors' traded volume that was buying")
    sell_pct: float | None = Field(None, description="hot: % that was selling; buy_pct + sell_pct = 100")
    new_pct: float | None = Field(None, description="top_buy: % of the top 5%'s buying that opened new positions")
    add_pct: float | None = Field(None, description="top_buy: % that added to existing positions; new + add = 100")
    reduce_pct: float | None = Field(None, description="top_sell: % of the top 5%'s selling that only reduced")
    sell_all_pct: float | None = Field(None, description="top_sell: % that fully exited; reduce + sell_all = 100")
    avg_buy_price: float | None = Field(None, description="hot, top_buy: average buy price, in `currency`")
    avg_sell_price: float | None = Field(None, description="hot, top_sell: average sell price, in `currency`")


class Snapshot(BaseModel):
    market: Market
    list_name: ListName
    period: Period
    trading_date: date = Field(description="Trading day the data belongs to, market-local")
    is_today: bool = Field(description="False before the day's first refresh: the data is the previous day's final")
    refreshed_at: datetime | None = None
    next_refresh_at: datetime | None = None
    fetched_at: datetime | None = Field(None, description="When the collector stored this snapshot (history only)")
    stocks: list[Stock]


def _complement(pct: float | None) -> float | None:
    return None if pct is None else 100 - pct


def _normalize(
    market: Market, list_name: ListName, period: Period, raw: dict, fetched_at: str | None = None
) -> Snapshot:
    items = next((v for v in raw.values() if isinstance(v, list)), None)
    if items is None or "nearestTradingDate" not in raw:
        raise ToolError(f"HSBC returned an unexpected response for {market} {list_name}; the API may have changed")
    stocks = [
        Stock(
            symbol=item["productId"]["productAlternativeNumber"],
            currency=item.get("currencyProductCode"),
            rank_today=item.get("rankToday"),
            rank_yesterday=item.get("rankYesterday"),
            rank_last_month=item.get("rankLastMonth"),
            rank_last_3_months=item.get("rankLast3Month"),
            rank_last_6_months=item.get("rankLast6Month"),
            buy_pct=item.get("buyVolume"),
            sell_pct=item.get("sellVolume"),
            add_pct=item.get("buyMore"),
            new_pct=_complement(item.get("buyMore")),
            sell_all_pct=item.get("sellAll"),
            reduce_pct=_complement(item.get("sellAll")),
            avg_buy_price=item.get("averagePurchasePrice"),
            avg_sell_price=item.get("averageSellPrice"),
        )
        for item in items
    ]
    return Snapshot(
        market=market,
        list_name=list_name,
        period=period,
        trading_date=raw["nearestTradingDate"][:10],
        is_today=raw.get("todayFigure", True),
        refreshed_at=raw.get("currentRefreshTime"),
        next_refresh_at=raw.get("nextRefreshTime"),
        fetched_at=fetched_at,
        stocks=stocks,
    )


# ponytail: unbounded in-process dict; entries are a few KB and keys are bounded by markets x lists x days.
_cache: dict[str, tuple[float, Any]] = {}
_transport: httpx2.AsyncBaseTransport | None = None  # tests inject httpx2.MockTransport


async def _cached(key: str, expires_at: Callable[[Any], float], fetch: Callable[[], Awaitable[Any]]) -> Any:
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    value = await fetch()
    _cache[key] = (expires_at(value), value)
    return value


def _client() -> httpx2.AsyncClient:
    headers = {"User-Agent": f"hsbc-tradetrack-mcp/{__version__} (+{REPO_URL})", "Accept": "application/json"}
    return httpx2.AsyncClient(transport=_transport, timeout=20, headers=headers)


async def _get(client: httpx2.AsyncClient, url: str, what: str, **kwargs: Any) -> httpx2.Response:
    try:
        response = await client.get(url, **kwargs)
    except httpx2.HTTPError as e:
        raise ToolError(f"Could not reach {what} ({type(e).__name__}); retry in a minute") from e
    if response.status_code >= 400 and response.status_code != 404:
        raise ToolError(f"{what} returned HTTP {response.status_code}; it may be under maintenance, retry later")
    return response


async def _fetch_live(client: httpx2.AsyncClient, market: Market, list_name: ListName, period: Period) -> dict:
    body = {"assetClassCode": ASSET_CLASSES[market], "marketCode": market, "dateType": DATE_TYPES[period]}
    response = await _get(client, HSBC_BASE + ENDPOINTS[list_name], "HSBC", params={"body": json.dumps(body)})
    try:
        return response.json()
    except ValueError as e:
        raise ToolError(f"HSBC returned non-JSON for {market} {list_name}; the API may have changed") from e


def _until_next_refresh(raw: dict) -> float:
    try:
        next_refresh = datetime.fromisoformat(raw["nextRefreshTime"]).timestamp()
    except (KeyError, TypeError, ValueError):
        next_refresh = 0
    return max(next_refresh, time.time() + 60)  # HSBC can publish late; recheck a minute later


async def _fetch_day(client: httpx2.AsyncClient, market: Market, day: date) -> str:
    response = await _get(client, f"{HISTORY_BASE}{market}/{day.isoformat()}.jsonl", "GitHub")
    return "" if response.status_code == 404 else response.text  # 404: no trading or not collected


def _day_file_expiry(day: date) -> Callable[[Any], float]:
    finished = day < datetime.now(UTC).date() - timedelta(days=1)
    return lambda _: float("inf") if finished else time.time() + 600


mcp = FastMCP(
    "HSBC TradeTrack",
    instructions=(
        "Unofficial HSBC TradeTrack data for US and HK stocks. Lists: hot = top 10 most traded by all HSBC "
        "personal banking investors; top_buy / top_sell / top_hold = top 10 bought / sold / held by HSBC's "
        "top 5% performing traders (top 5% portfolio return over 6 months). Hot refreshes every 30 minutes "
        "in market hours; top 5% lists 3 times a day (US 11:30, 13:00, 16:00 ET; HK 12:30, 15:30, 16:10 HKT). "
        "Use tradetrack for the latest data and tradetrack_history for past intraday snapshots."
    ),
    version=__version__,
    website_url=REPO_URL,
)
READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}


@mcp.tool(annotations=READ_ONLY)
async def tradetrack(market: Market, lists: list[ListName] | None = None, period: Period = "today") -> list[Snapshot]:
    """Latest HSBC TradeTrack lists for a market. `lists` defaults to all four.

    `period` picks the ranking window: today, yesterday or last_month for every list;
    last_3_months and last_6_months for top_hold only.
    """
    lists = lists or ALL_LISTS
    if period in HOLDINGS_ONLY_PERIODS and set(lists) != {"top_hold"}:
        raise ToolError(f"period={period} exists only for lists=['top_hold']")
    async with _client() as client:
        raws = await asyncio.gather(
            *(
                _cached(
                    f"live:{market}:{name}:{period}",
                    _until_next_refresh,
                    lambda name=name: _fetch_live(client, market, name, period),
                )
                for name in lists
            )
        )
    return [_normalize(market, name, period, raw) for name, raw in zip(lists, raws, strict=True)]


@mcp.tool(annotations=READ_ONLY)
async def tradetrack_history(
    market: Market,
    date_from: date,
    date_to: date | None = None,
    lists: list[ListName] | None = None,
    symbol: str | None = None,
) -> list[Snapshot]:
    """Past intraday snapshots of the "today" lists, one per HSBC refresh, collected since 2026-10-16.

    Dates are trading days (market-local), inclusive, at most 31 days per call. Pass `symbol` to keep only
    snapshots that contain that stock (HK codes may omit leading zeros). Days without trading return nothing.
    """
    date_to = date_to or date_from
    days = (date_to - date_from).days + 1
    if not 1 <= days <= MAX_HISTORY_DAYS:
        raise ToolError(f"date_to must be on or after date_from, and the range at most {MAX_HISTORY_DAYS} days")
    wanted = set(lists or ALL_LISTS)
    if symbol:
        symbol = symbol.upper().zfill(5) if market == "HK" and symbol.isdigit() else symbol.upper()

    day_list = [date_from + timedelta(days=i) for i in range(days)]
    async with _client() as client:
        files = await asyncio.gather(
            *(
                _cached(
                    f"history:{market}:{day}", _day_file_expiry(day), lambda day=day: _fetch_day(client, market, day)
                )
                for day in day_list
            )
        )

    snapshots = []
    for text in files:
        for line in text.splitlines():
            record = json.loads(line)
            if record["dateType"] != "TODAY" or record["list"] not in wanted:
                continue
            snapshot = _normalize(market, record["list"], "today", record["raw"], record["fetched_at"])
            if symbol:
                snapshot.stocks = [s for s in snapshot.stocks if s.symbol == symbol]
                if not snapshot.stocks:
                    continue
            snapshots.append(snapshot)
    return snapshots


def main() -> None:
    mcp.run()
