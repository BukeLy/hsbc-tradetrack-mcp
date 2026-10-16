# data branch

Raw HSBC TradeTrack snapshots appended by [`collect.yml`](https://github.com/BukeLy/hsbc-tradetrack-mcp/blob/main/.github/workflows/collect.yml).
One file per market per trading day: `<US|HK>/<YYYY-MM-DD>.jsonl`, one `{"list", "dateType", "fetched_at", "raw"}` record per new snapshot.
Field meanings: [docs/hsbc-api.md](https://github.com/BukeLy/hsbc-tradetrack-mcp/blob/main/docs/hsbc-api.md).
