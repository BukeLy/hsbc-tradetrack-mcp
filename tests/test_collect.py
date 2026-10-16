import json

from collect import collect


def fake_fetch(endpoint, market, date_type):
    if endpoint == "top-holdings":
        raise TimeoutError("upstream down")
    # Friday 16:00 ET final list, fetched after HSBC already moved nearestTradingDate to Monday
    refreshed = {"US": "2026-10-17T04:00:03.000+08:00", "HK": "2026-10-16T16:10:02.000+08:00"}[market]
    return {"nearestTradingDate": "2026-10-19T00:00:00.000+08:00", "currentRefreshTime": refreshed, "list": [endpoint]}


def test_appends_once_per_snapshot_and_reports_failures(tmp_path):
    errors = collect(tmp_path, fetch=fake_fetch)
    collect(tmp_path, fetch=fake_fetch)

    assert sorted(p.name for p in tmp_path.glob("*/*.jsonl")) == ["2026-10-16.jsonl", "2026-10-16.jsonl"]
    lines = (tmp_path / "US" / "2026-10-16.jsonl").read_text().splitlines()
    # 3 working lists x 2 date types, not duplicated by the second run
    assert len(lines) == 6
    assert {json.loads(line)["list"] for line in lines} == {"hot", "top_buy", "top_sell"}
    # top_hold fails for both markets and both date types
    assert len(errors) == 4
