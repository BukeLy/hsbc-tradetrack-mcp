# hsbc-tradetrack-mcp

Unofficial MCP server for **HSBC TradeTrack** (汇丰交易追踪 / 匯豐交易追蹤): the US and Hong Kong stocks HSBC personal banking investors trade most, and what HSBC's top 5% performing traders buy, sell and hold.

All data comes from HSBC's **public, no-login endpoints** (the same ones behind the pre-logon TradeTrack page). No HSBC account, API key or authentication is needed.

关键词：汇丰交易追踪、汇丰热门股票、前5%表现最好投资者、买入卖出比例、美股、港股、MCP。

<!-- mcp-name: io.github.BukeLy/hsbc-tradetrack-mcp -->

> **Status:** work in progress. The MCP tools are not released yet; historical snapshots are already being collected (see below).

## Lists

| List | What it shows | US refresh (ET) | HK refresh (HKT) |
|---|---|---|---|
| Hot (all investors) | Top 10 most actively traded stocks, buy % vs sell % | 09:35, then every 30 min 10:00–16:00 | 09:35, then every 30 min 10:00–16:30 |
| Top buy (top 5%) | Top 10 stocks bought; split into new vs added positions | 11:30, 13:00, 16:00 | 12:30, 15:30, 16:10 |
| Top sell (top 5%) | Top 10 stocks sold; split into partial vs full exits | same | same |
| Top hold (top 5%) | Top 10 holdings with 1d / 1m / 3m / 6m ranks | same | same |

"Top 5%" means active HSBC stock traders whose portfolios returned the top 5% over the past 6 months.

## Historical data

HSBC only serves today, yesterday and last month. A scheduled workflow appends every new snapshot to the [`data` branch](https://github.com/BukeLy/hsbc-tradetrack-mcp/tree/data), one file per market per trading day:

```
https://raw.githubusercontent.com/BukeLy/hsbc-tradetrack-mcp/data/<US|HK>/<YYYY-MM-DD>.jsonl
```

Each line is `{"list", "dateType", "fetched_at", "raw"}`, where `raw` is HSBC's unmodified response.

## Disclaimer

Not affiliated with, endorsed by, or connected to HSBC. "HSBC" and "TradeTrack" are trademarks of their owner. The data belongs to HSBC and may be delayed, incomplete or wrong. Nothing here is investment advice.

## License

[MIT](LICENSE)
