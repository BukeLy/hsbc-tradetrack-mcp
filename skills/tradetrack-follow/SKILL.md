---
name: tradetrack-follow
description: Follow HSBC TradeTrack's top 5% traders with Interactive Brokers - turn today's TradeTrack lists into reviewed IBKR order instructions.
disable-model-invocation: true
---

# Follow the top 5% with IBKR

An example workflow, not investment advice. It joins two MCP servers:

- **TradeTrack** (`hsbc-tradetrack-mcp`): tools `tradetrack` and `tradetrack_history`.
- **Interactive Brokers** (IBKR's official connector): account, quotes, contracts, order instructions.

The strategy has not been backtested. Run it on an IBKR paper account until it has been.

A run is **unattended** when the request says so, for example a scheduled task. Nobody answers during an unattended run, so each step that asks or waits carries an unattended rule.

## Parameters

Use these defaults unless the user overrides one in their request. Echo the values in the report. Each default cites its basis; until a backtest on the `data` branch replaces them, they lean conservative: fewer, stronger entries and earlier exits.

| Parameter | Default | Meaning | Basis |
|---|---|---|---|
| `markets` | `US, HK` | Markets to scan | |
| `buy_days` | 2 | Consecutive trading days on `top_buy` before an entry (1 or 2) | [1] |
| `min_hot_buy_pct` | 80 | If the stock is on the hot list, its `buy_pct` must be at least this | [2] |
| `exit_sell_all_pct` | 0 | Exit when the stock is on `top_sell` with `sell_all_pct` at least this; 0 exits on any appearance | [3] |
| `stop_loss_pct` | 7 | Exit when price is this % below average cost | [4] |
| `position_pct` | 5 | Target size of a new position, % of net liquidation value | [5] |
| `max_positions` | 10 | Open positions this strategy may hold, all markets together | [6] |
| `exclude` | none | Held symbols the strategy must leave alone | |

1. Daily order imbalance persists: first-lag autocorrelation about 23% (Chordia & Subrahmanyam, "Order imbalance and individual stock returns", *JFE* 72, 2004, 485–518). No study compares 1 with 2 days; 2 is the conservative choice.
2. Order-flow studies call the top quintile of buy imbalance strong (Barber, Odean & Zhu, *RFS* 22(1), 2009; Boehmer, Jones, Zhang & Zhang, *JF* 76(5), 2021). 80 sits above the 75th percentile of retail buy share (65.7%) and below the top-decile midpoint (92.3%) in Kelley & Tetlock, *JF* 68(3), 2013, Table I.
3. No source gives a threshold, and selling carries little information (Lakonishok & Lee, *RFS* 14(1), 2001; Chen, Jegadeesh & Wermers, *JFQA* 35(3), 2000). 0 is the earliest exit; the stop loss is the main risk exit.
4. "Always, without Exception, Limit Your Losses to 7% or 8% of Your Cost" (O'Neil, *How to Make Money in Stocks*, 4th ed., 2009, ch. 10, pp. 242–244). 7 is the conservative end.
5. A diversified fund holds at most 5% of total assets in one issuer ([15 U.S.C. 80a-5(b)(1)](https://www.law.cornell.edu/uscode/text/15/80a-5)); FINRA reports experts capping one stock at 10% ([FINRA](https://www.finra.org/investors/insights/love-your-company-stock-what-to-know)).
6. "If you're uncomfortable and nervous with only six or seven, then own ten" (O'Neil 2009, ch. 12, pp. 273–275), for a whole portfolio.

## Signals

Every STK position in the account counts as held by this strategy, for exits and for `max_positions`, except symbols in `exclude`. Positions carry no market field: `currency` USD means US, HKD means HK. A held stock is matched only against its own market's lists.

- **Entry**: the stock is on `top_buy` with `rank_today` set, and also `rank_yesterday` when `buy_days` is 2 (the top 5% bought it two trading days in a row); it passes the hot-list check (absent from `hot`, or `buy_pct` >= `min_hot_buy_pct`), it does not meet the `top_sell` exit rule below (the top 5% can be buying and selling the same stock), and it is not already held.
- **Exit**, for each held stock, the first that applies:
  - it is on `top_sell` with `sell_all_pct` >= `exit_sell_all_pct`;
  - its `market_price` is `stop_loss_pct` or more below its `average_price`.

## Steps

1. **Fetch the lists.** Call `tradetrack` with `lists=["hot","top_buy","top_sell"]` for each market. `trading_date` is the session the lists belong to; between sessions it is the last session's final list, which is what an order before the next open should act on. The top 5% lists refresh three times a session (US 11:30, 13:00, 16:00 ET; HK 12:30, 15:30, 16:10 HKT) and `hot` every 30 minutes, so the signal is most complete after the last refresh. Report each list's `trading_date` and `refreshed_at`.
   - Unattended: the run is scheduled either before the market's open (US and HK both 09:30 local: [NYSE](https://www.nyse.com/markets/hours-calendars), [HKEX](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market?sc_lang=en)), to act on pre-market quotes, or after its last refresh. In the market's time zone (US America/New_York, HK Asia/Hong_Kong), today must be a weekday, and `top_buy`'s `trading_date` must be before today before the open (the last session, even across a holiday) and today after the last refresh. Otherwise the market is closed: report it with the current time in that zone, so a mis-scheduled run shows, and drop it from the run. A pre-open run cannot see a holiday on the run day itself; the user reviewing the drafts before the open catches it.

   Done when every remaining market has its three lists.

2. **Read the account.** Call `get_flow_type` once, then `get_account_summary`, `get_account_positions`, `get_order_instructions` and `get_account_orders`. The connector does not return the account id: take paper (`DU...`) or live from the request, otherwise ask the user (unattended: stop with "account type not stated"), and state it in the report. Done when you know the summary's `net_liquidation`, `available_funds` and `currency` (the base currency); for every position its `contract_description` (symbol), `position` (quantity), `average_price`, `market_price`, `currency` and `contract_id`; and the **pending** set: each saved instruction's `contract_id_ex` and `side`, and each working order's symbol and side (from `primary_description`, such as `Buy 1 SPCX`).

3. **Resolve entry candidates.** Held stocks already have `contract_id` and `market_price` from step 2. For each entry candidate, call `search_contracts`:
   - US: the row whose `symbol` equals the ticker exactly and whose `country_code` is `US`.
   - HK: TradeTrack codes are zero-padded (`00700`). Search without leading zeros (`700`) and take the row whose `exchange` is `SEHK` and whose `symbol` equals that unpadded code exactly.
   - Keep the row only if one of its `sections` has `security_type` `STK`. Other sections such as `OPT` or `WAR` are derivatives on the stock and do not disqualify it. The contract id is `underlying_contract_id`. No matching row: skip with "unresolved".

   Then call `get_price_snapshot` with `market_data_names=["last","bid_ask"]` for each entry candidate and each exit, adding `exchange: "SEHK"` for HK (without it the response is empty). The price is `bid-ask`'s `ask` for a buy and `bid` for a sell; if it is missing, use `last.price`; if both are missing, skip with "no quote". Quotes already sit on a valid tick, so the price needs no rounding. Done when every candidate and exit has a contract id and a price, or a skip reason.

4. **Decide.** Evaluate every exit before any entry. Then take entries by lowest `rank_today` on `top_buy` first, while open positions across all markets stay within `max_positions`.
   - Size: the target is `position_pct`% of `net_liquidation`, in the base currency; convert it to the stock's currency before dividing. Quantity = `floor(target / price)`, keeping a running total within `available_funds`. Quantity 0: skip with "target below one share".
   - HK trades in board lots that these tools do not expose: leave `quantity` unset, show the HKD target in the table, tell the user to set a whole number of lots, and warn that one lot may exceed the target.
   - Exits sell the full `position`.
   - Limit price: the step 3 price, so a buy pays at most the ask and a sell takes at least the bid. HKEX rejects a limit buy above the best ask ([trading mechanism](https://www.hkex.com.hk/Services/Trading/Securities/Overview/Trading-Mechanism?sc_lang=en)), which rules out any premium in HK.
   - A buy or sell whose stock and side are already in the pending set: skip with "already pending". An earlier run's draft or order covers it, and repeat runs stay idempotent.

   Done when every candidate and every held stock has a decision: buy, sell, hold, or skip with the reason.

5. **Confirm, then place.** Show the decision table (market, symbol, signal, list figures, price, side, quantity or HKD target, limit) and wait for the user's go-ahead. Unattended: go ahead in `REVIEW_AND_APPROVE`, where every instruction still waits for the user in IBKR; in `AUTONOMOUS`, place nothing and end with the report. Then:
   - `REVIEW_AND_APPROVE`: `create_order_instruction` per approved decision with `contract_id_ex` (the contract id as a string), `side` (`"BUY"` or `"SELL"`), `quantity` (omit for HK buys), `order_type: "LIMIT"`, `limit_price`, `time_in_force: "DAY"`. Give the user each returned URL; nothing trades until they submit it in IBKR.
   - `AUTONOMOUS`: place the same orders with `submit_order`, following its own preview and question steps.

   Done when every approved decision has an instruction URL or an order id, and failures are reported with the error text.

## Report

End with: parameters used, paper or live, `trading_date` and `refreshed_at` per list, the decision table, instruction URLs or order ids, and everything skipped with its reason.
