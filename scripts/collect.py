"""Append new HSBC TradeTrack snapshots to <out>/<market>/<YYYY-MM-DD>.jsonl.

Run by .github/workflows/collect.yml against a checkout of the `data` branch.
Stdlib only, so the workflow needs no install step.
"""

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = (
    "https://investments4.personal-banking.hsbc.com.hk/api/"
    "wealth-trade-equity-public-shp-api-hk-hbap-prod-proxy/v0/equities/public/srbp/hk/online/"
)
LISTS = {
    "hot": "top-active-traded-products",
    "top_buy": "top-buying-products",
    "top_sell": "top-selling-products",
    "top_hold": "top-holdings",
}
ASSET_CLASSES = {"US": ["SEC"], "HK": ["SEC", "WRTS"]}
DATE_TYPES = ["TODAY", "LAST_1_MONTH"]
USER_AGENT = "hsbc-tradetrack-mcp-collector (+https://github.com/BukeLy/hsbc-tradetrack-mcp)"


def fetch(endpoint: str, market: str, date_type: str) -> dict:
    body = {"assetClassCode": ASSET_CLASSES[market], "marketCode": market, "dateType": date_type}
    url = BASE + endpoint + "?" + urllib.parse.urlencode({"body": json.dumps(body)})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def key(record: dict) -> tuple[str, str, str]:
    raw = json.dumps(record["raw"], sort_keys=True).encode()
    return record["list"], record["dateType"], hashlib.sha256(raw).hexdigest()


def collect(out: Path, fetch=fetch) -> list[str]:
    """Append every snapshot not already in its day file; return errors instead of raising."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    errors = []
    for market in ASSET_CLASSES:
        for name, endpoint in LISTS.items():
            for date_type in DATE_TYPES:
                try:
                    raw = fetch(endpoint, market, date_type)
                    day = raw["nearestTradingDate"][:10]
                except Exception as e:  # noqa: BLE001 - one failing list must not stop the others
                    errors.append(f"{market} {name} {date_type}: {e!r}")
                    continue
                record = {"list": name, "dateType": date_type, "fetched_at": now, "raw": raw}
                path = out / market / f"{day}.jsonl"
                lines = path.read_text().splitlines() if path.exists() else []
                if key(record) in {key(json.loads(line)) for line in lines}:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return errors


if __name__ == "__main__":
    errors = collect(Path(sys.argv[1]))
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1 if errors else 0)
