# HSBC TradeTrack upstream API

Undocumented. Reverse-engineered on 2026-10-17 from the pre-logon page
`https://investments4.personal-banking.hsbc.com.hk/public-stb/en-gb/market/trade-track`
(`getTopActiveTraded` / `getTopBuy` / `getTopSell` / `getTopHolding` in its `main.*.js` bundle).
No cookies, Referer or login are required. Response header advertises a limit of 200 requests per second.

## Request

```
GET https://investments4.personal-banking.hsbc.com.hk/api/wealth-trade-equity-public-shp-api-hk-hbap-prod-proxy/v0/equities/public/srbp/hk/online/<endpoint>?body=<url-encoded JSON>
```

`body`:

| Field | Values |
|---|---|
| `marketCode` | `US`, `HK` |
| `assetClassCode` | US `["SEC"]`; HK `["SEC", "WRTS"]` (the page's own values) |
| `dateType` | `TODAY`, `LAST_1_DAY`, `LAST_1_MONTH`; `top-holdings` also accepts `LAST_3_MONTH`, `LAST_6_MONTH` (others return an empty body) |

## Endpoints and field semantics

Every endpoint returns `currentRefreshTime`, `nextRefreshTime`, `nearestTradingDate` (HSBC's nearest trading day: it jumps to the next session as soon as a session's last refresh is out, so the session a response belongs to is the market-local date of `currentRefreshTime`), `todayFigure` (false before the first refresh of the day), `currentMarket`, and a 10-item list. Each item has `productId.productAlternativeNumber` (ticker / HK code), `rankToday`, `rankYesterday`, `rankLastMonth` (null = not in that period's top 10), `currencyProductCode`.

| Endpoint | List | Extra fields |
|---|---|---|
| `top-active-traded-products` | Hot: top 10 actively traded by all HSBC personal banking investors | `buyVolume` + `sellVolume` = 100 (% of volume); `averagePurchasePrice`, `averageSellPrice` |
| `top-buying-products` | Top 10 bought by the top 5% performers | `buyMore` = % of buying from existing holders adding; **new exposure = 100 − `buyMore`**. `averagePurchasePrice` |
| `top-selling-products` | Top 10 sold by the top 5% performers | `sellAll` = % of selling that fully exits; **reduce exposure = 100 − `sellAll`**. `averageSellPrice` |
| `top-holdings` | Top 10 held by the top 5% performers | `rankLast3Month`, `rankLast6Month` |

`buyMore` and `sellAll` describe the composition of the flow, not its strength. The same stock can appear on the buy and the sell list at once.

"Top 5%" = active stock traders with top-5% stock portfolio performance over the past 6 months.

## Refresh schedule

| List | US (ET) | HK (HKT) |
|---|---|---|
| Hot | 09:35, then every 30 min 10:00–16:00 | 09:35, then every 30 min 10:00–16:30 |
| Top buy / sell / hold | 11:30, 13:00, 16:00 | 12:30, 15:30, 16:10 |

Before the first refresh of a trading day, `TODAY` returns the previous trading day's final data.
