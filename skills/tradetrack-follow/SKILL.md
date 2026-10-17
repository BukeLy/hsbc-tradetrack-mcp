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

A run is **unattended** when the request says so, for example a scheduled task. Nobody answers during an unattended run, so each step that asks or waits carries an unattended rule. A run is **exits-only** when the request says so: it decides exits and skips every entry.

## Parameters

Use these defaults unless the user overrides one in their request. Echo the values in the report. Each default cites its basis; until a backtest on the `data` branch replaces them, they lean conservative.

| Parameter | Default | Meaning | Basis |
|---|---|---|---|
| `markets` | `US, HK` | Markets to scan | |
| `buy_days` | 2 | Consecutive trading days on `top_buy` before an entry (1 or 2) | [1] |
| `min_hot_buy_pct` | 80 | If the stock is on the hot list, its `buy_pct` must be at least this | [2] |
| `stop_loss_pct` | 7 | Exit when price is this % below average cost | [3] |
| `hold_weeks` | 3 | Exit a stock or ordinary ETF once held this many weeks | [4] |
| `winner_gain_pct` | 20 | A position whose close reached this % above average cost within its first 3 weeks is a winner | [5] |
| `winner_hold_weeks` | 8 | A winner exits once held this many weeks instead | [5] |
| `position_pct` | 5 | Target size of a new position, % of net liquidation value | [6] |
| `max_positions` | 10 | Open positions this strategy may hold, all markets together | [7] |
| `exclude` | none | Held symbols the strategy must leave alone | |

1. Daily order imbalance persists: first-lag autocorrelation about 23% (Chordia & Subrahmanyam, "Order imbalance and individual stock returns", *JFE* 72, 2004, 485–518). No study compares 1 with 2 days; 2 is the conservative choice.
2. Order-flow studies call the top quintile of buy imbalance strong (Barber, Odean & Zhu, *RFS* 22(1), 2009; Boehmer, Jones, Zhang & Zhang, *JF* 76(5), 2021). 80 sits above the 75th percentile of retail buy share (65.7%) and below the top-decile midpoint (92.3%) in Kelley & Tetlock, *JF* 68(3), 2013, Table I.
3. "Always, without Exception, Limit Your Losses to 7% or 8% of Your Cost" (O'Neil, *How to Make Money in Stocks*, 4th ed., 2009, ch. 10, pp. 242–244). 7 is the conservative end.
4. Stocks heavily bought by individual investors earn strong returns the following week, a pattern that "persists for a total of three to four weeks and then reverses" (Barber, Odean & Zhu, ["Do Noise Traders Move Markets?"](https://haas.berkeley.edu/wp-content/uploads/Noise.pdf), working paper, 2005, abstract; the paper's conclusion puts it at two weeks). 3 is the conservative end.
5. "If the stock was so powerful that it vaulted 20% in only one, two, or three weeks, it must be held for at least eight weeks from its buy point"; the stop still applies, and "any stock that rises close to 20% should never be allowed to drop back into the loss column" (O'Neil 2009, ch. 11, pp. 258–259).
6. A diversified fund holds at most 5% of total assets in one issuer ([15 U.S.C. 80a-5(b)(1)](https://www.law.cornell.edu/uscode/text/15/80a-5)); FINRA reports experts capping one stock at 10% ([FINRA](https://www.finra.org/investors/insights/love-your-company-stock-what-to-know)).
7. "If you're uncomfortable and nervous with only six or seven, then own ten" (O'Neil 2009, ch. 12, pp. 273–275), for a whole portfolio.
8. Leveraged and inverse ETFs that reset daily "typically are unsuitable for retail investors who plan to hold them for longer than one trading session" ([FINRA Regulatory Notice 09-31](https://www.finra.org/rules-guidance/notices/09-31)).

## Signals

Every STK position in the account counts as held by this strategy, for exits and for `max_positions`, except symbols in `exclude`. Positions carry no market field: `currency` USD means US, HKD means HK. A held stock is matched only against its own market's lists. A position's **age** is the time since its entry date (step 2).

- **Entry**: the stock is on `top_buy` with `rank_today` set, and also `rank_yesterday` when `buy_days` is 2 (the top 5% bought it two trading days in a row); it passes the hot-list check (absent from `hot`, or `buy_pct` >= `min_hot_buy_pct`); it is absent from `top_sell` (the top 5% selling it too is a conflicting signal); and it is not already held.
- **Exit**, for each held position, the first that applies:
  - **stop**: its `market_price` is `stop_loss_pct` or more below its `average_price`;
  - **daily reset**: it is a leveraged or inverse ETF and does not meet the entry rule today, apart from already being held [8]. Each run decides it afresh, whatever its profit;
  - **break-even**: it is a winner and its `market_price` is at or below its `average_price` [5];
  - **holding period**: any other position whose age has reached `hold_weeks`, or `winner_hold_weeks` if it is a winner.

  A position without an entry date has passed every holding period.

## Steps

1. **Fetch the lists.** Call `tradetrack` with `lists=["hot","top_buy","top_sell"]` for each market. `trading_date` is the session the lists belong to; between sessions it is the last session's final list, which is what an order before the next open should act on. The top 5% lists refresh three times a session (US 11:30, 13:00, 16:00 ET; HK 12:30, 15:30, 16:10 HKT) and `hot` every 30 minutes, so the signal is most complete after the last refresh. Report each list's `trading_date` and `refreshed_at`.
   - Unattended: the run is scheduled before the market's open (US and HK both 09:30 local: [NYSE](https://www.nyse.com/markets/hours-calendars), [HKEX](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market?sc_lang=en)), or after the session's first top 5% refresh. In the market's time zone (US America/New_York, HK Asia/Hong_Kong), today must be a weekday, and `top_buy`'s `trading_date` must be before today before the open (the last session, even across a holiday) and today after the first refresh. Otherwise the market is closed, or the run falls between the open and the first refresh: report which, with the current time in that zone so a mis-scheduled run shows, and drop the market from the run. A pre-open run cannot see a holiday on the run day itself; the user reviewing the drafts before the open catches it.

   Done when every remaining market has its three lists.

2. **Read the account.** Call `get_flow_type` once if the connector has it; without it (ChatGPT's IBKR app), the flow is `REVIEW_AND_APPROVE`. Then call `get_account_summary`, `get_account_positions`, `get_order_instructions`, `get_account_orders`, and `get_account_trades` with `period: "DAYS_90"`. The connector does not return the account id: take paper (`DU...`) or live from the request, otherwise ask the user (unattended: stop with "account type not stated"), and state it in the report. Done when you know:
   - the summary's `net_liquidation`, `available_funds` and `currency` (the base currency);
   - for every position its `contract_description` (symbol), `position` (quantity), `average_price`, `market_price`, `currency` and `contract_id`;
   - each position's **entry date**: the latest `trade_time` among its symbol's `BUY` trades, or none when it has no `BUY` in the last 90 days (the strategy never adds to a held stock, so the latest buy opened the position);
   - the **pending** set: each saved instruction's `contract_id_ex` and `side`, and each working order's symbol and side (from `primary_description`, such as `Buy 1 SPCX`).

3. **Resolve contracts and prices.** For each entry candidate (none in an exits-only run), call `search_contracts`:
   - US: the row whose `symbol` equals the ticker exactly and whose `country_code` is `US`.
   - HK: TradeTrack codes are zero-padded (`00700`). Search without leading zeros (`700`) and take the row whose `exchange` is `SEHK` and whose `symbol` equals that unpadded code exactly.
   - Keep the row only if one of its `sections` has `security_type` `STK`. Other sections such as `OPT` or `WAR` are derivatives on the stock and do not disqualify it. The contract id is `underlying_contract_id`. No matching row: skip with "unresolved".

   For each held position, call `search_contracts` with its symbol and read the name of the row whose contract id matches: a leveraged or inverse ETF says so in its name (for example "2X", "3X", "Ultra", "Bull", "Bear", "Inverse"). For each held stock or ordinary ETF whose age is between `hold_weeks` and `winner_hold_weeks`, call `get_price_history` (`contract_id`, `security_type: "STK"`, `period: "THREE_MONTHS"`, `step: "ONE_DAY"`, `outside_rth: false`) to see whether a close in its first 3 weeks reached `winner_gain_pct` above `average_price`.

   Then call `get_price_snapshot` with `market_data_names=["last","bid_ask"]` for each entry candidate and each exit, adding `exchange: "SEHK"` for HK (without it the response is empty). The price is `bid-ask`'s `ask` for a buy and `bid` for a sell; if it is missing, use `last.price`; if both are missing, skip with "no quote". Quotes already sit on a valid tick, so the price needs no rounding. Done when every candidate and exit has a contract id and a price, or a skip reason, and every held position is classified (leveraged or inverse ETF, winner, or neither).

4. **Decide.** Evaluate every exit before any entry. Then, unless the run is exits-only, take entries by lowest `rank_today` on `top_buy` first, while open positions across all markets stay within `max_positions`.
   - Size: the target is `position_pct`% of `net_liquidation`, in the base currency; convert it to the stock's currency before dividing. Quantity = `floor(target / price)`, keeping a running total within `available_funds`. Quantity 0: skip with "target below one share".
   - HK trades in board lots that these tools do not expose: leave `quantity` unset, show the HKD target in the table, tell the user to set a whole number of lots, and warn that one lot may exceed the target.
   - Exits sell the full `position`.
   - Limit price: the step 3 price, so a buy pays at most the ask and a sell takes at least the bid. HKEX rejects a limit buy above the best ask ([trading mechanism](https://www.hkex.com.hk/Services/Trading/Securities/Overview/Trading-Mechanism?sc_lang=en)), which rules out any premium in HK.
   - A buy or sell whose stock and side are already in the pending set: skip with "already pending". An earlier run's draft or order covers it, and repeat runs stay idempotent.

   Done when every candidate and every held position has a decision: buy, sell (naming the exit rule), hold, or skip with the reason.

5. **Confirm, then place.** Show the decision table (market, symbol, signal, list figures, age, price, side, quantity or HKD target, limit) and wait for the user's go-ahead. Unattended: go ahead in `REVIEW_AND_APPROVE`, where every instruction still waits for the user in IBKR; in `AUTONOMOUS`, place nothing and end with the report. Then:
   - `REVIEW_AND_APPROVE`: `create_order_instruction` per approved decision with `contract_id_ex` (the contract id as a string), `side` (`"BUY"` or `"SELL"`), `quantity` (omit for HK buys), `order_type: "LIMIT"`, `limit_price`, `time_in_force: "DAY"`. Give the user each returned URL; nothing trades until they submit it in IBKR.
   - `AUTONOMOUS`: place the same orders with `submit_order`, following its own preview and question steps.

   Done when every approved decision has an instruction URL or an order id, and failures are reported with the error text.

## Report

End with: parameters used, paper or live, exits-only or full, `trading_date` and `refreshed_at` per list, the decision table, instruction URLs or order ids, and everything skipped with its reason.
