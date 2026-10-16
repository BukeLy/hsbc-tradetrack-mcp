"""Offline tests: HTTP is served by httpx2.MockTransport with synthetic payloads (no real HSBC data)."""

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from fastmcp.client import Client
from fastmcp.exceptions import ToolError

from hsbc_tradetrack_mcp import server

SCHEMA_SNAPSHOT = Path(__file__).with_name("tools.schema.json")


def item(symbol, **fields):
    return {"productId": {"productAlternativeNumber": symbol}, "currencyProductCode": "USD", "rankToday": 1, **fields}


def payload(*items, refreshed="2026-10-16T14:00:00-04:00", next_refresh="2999-01-01T00:00:00+00:00"):
    return {
        "todayFigure": True,
        "currentRefreshTime": refreshed,
        "nextRefreshTime": next_refresh,
        "nearestTradingDate": "2026-10-19T00:00:00.000+08:00",
        "topList": list(items),
    }


LIVE = {
    "top-active-traded-products": payload(item("AAA", buyVolume=70.0, sellVolume=30.0, averagePurchasePrice=10.5)),
    "top-buying-products": payload(item("BBB", buyMore=8)),
    "top-selling-products": payload(item("CCC", sellAll=100)),
    "top-holdings": payload(item("DDD", rankLast3Month=2, rankLast6Month=None)),
}


@pytest.fixture
def http(monkeypatch):
    """Route HSBC and GitHub URLs to `routes`; record every request."""
    routes, calls = {}, []

    def handler(request):
        calls.append(request)
        url = str(request.url)
        for prefix, response in routes.items():
            if url.startswith(prefix):
                return response(request) if callable(response) else response
        return httpx2.Response(404)

    monkeypatch.setattr(server, "_transport", httpx2.MockTransport(handler))
    monkeypatch.setattr(server, "_cache", {})
    return routes, calls


def live_routes(routes):
    for endpoint, body in LIVE.items():
        routes[server.HSBC_BASE + endpoint] = httpx2.Response(200, json=body)


async def call(tool, **args):
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    return result.structured_content["result"]


@pytest.mark.anyio
async def test_live_normalizes_all_lists_and_caches_until_next_refresh(http):
    routes, calls = http
    live_routes(routes)

    snapshots = await call("tradetrack", market="US")
    await call("tradetrack", market="US")

    by_list = {s["list_name"]: s["stocks"][0] for s in snapshots}
    assert by_list["hot"]["buy_pct"] == 70 and by_list["hot"]["sell_pct"] == 30
    assert by_list["hot"]["avg_buy_price"] == 10.5
    assert by_list["top_buy"]["add_pct"] == 8 and by_list["top_buy"]["new_pct"] == 92
    assert by_list["top_sell"]["sell_all_pct"] == 100 and by_list["top_sell"]["reduce_pct"] == 0
    assert by_list["top_hold"]["rank_last_3_months"] == 2
    assert snapshots[0]["trading_date"] == "2026-10-16"
    assert len(calls) == 4  # second call served from cache

    body = json.loads(parse_qs(urlparse(str(calls[0].url)).query)["body"][0])
    assert body == {"assetClassCode": ["SEC"], "marketCode": "US", "dateType": "TODAY"}
    assert calls[0].headers["user-agent"].startswith("hsbc-tradetrack-mcp/")


@pytest.mark.anyio
async def test_live_errors_are_actionable(http):
    routes, _ = http
    routes[server.HSBC_BASE] = httpx2.Response(500)
    with pytest.raises(ToolError, match="HTTP 500"):
        await call("tradetrack", market="HK", lists=["hot"])
    with pytest.raises(ToolError, match="only for lists"):
        await call("tradetrack", market="US", period="last_3_months")


@pytest.mark.anyio
async def test_history_reads_today_snapshots_and_filters_symbol(http):
    routes, _ = http

    def record(list_name, date_type, *items):
        return json.dumps(
            {
                "list": list_name,
                "dateType": date_type,
                "fetched_at": "2026-10-16T18:00:00+00:00",
                "raw": payload(*items),
            }
        )

    day_file = "\n".join(
        [
            record("hot", "TODAY", item("00700"), item("09988")),
            record("hot", "LAST_1_MONTH", item("00700")),
            record("top_buy", "TODAY", item("09988")),
        ]
    )
    routes[server.HISTORY_BASE + "HK/2026-10-16.jsonl"] = httpx2.Response(200, text=day_file)

    # 10-16 has data, 10-17 is a 404 (weekend)
    snapshots = await call(
        "tradetrack_history", market="HK", date_from="2026-10-16", date_to="2026-10-17", symbol="700"
    )

    assert [(s["list_name"], [x["symbol"] for x in s["stocks"]]) for s in snapshots] == [("hot", ["00700"])]
    assert snapshots[0]["fetched_at"].startswith("2026-10-16T18:00")

    with pytest.raises(ToolError, match="at most 31 days"):
        await call("tradetrack_history", market="US", date_from="2026-01-01", date_to="2026-03-01")


@pytest.mark.anyio
async def test_tool_schema_matches_snapshot():
    """The tool schema is the public API: a diff here means a feat or a breaking (!) change.

    Regenerate with UPDATE_SCHEMA_SNAPSHOT=1 uv run pytest.
    """
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
    schema = {
        t.name: {
            "inputSchema": t.input_schema,
            "outputSchema": t.output_schema,
            "annotations": t.annotations.model_dump(exclude_none=True),
        }
        for t in tools
    }
    if os.environ.get("UPDATE_SCHEMA_SNAPSHOT"):
        SCHEMA_SNAPSHOT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    assert schema == json.loads(SCHEMA_SNAPSHOT.read_text())
