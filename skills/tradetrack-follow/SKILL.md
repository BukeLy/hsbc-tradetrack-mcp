---
name: tradetrack-follow
description: Follow HSBC TradeTrack's top 5% traders with Interactive Brokers - turn today's TradeTrack lists into reviewed IBKR order instructions.
disable-model-invocation: true
---

# Follow the top 5% with IBKR

An example workflow, not investment advice. It joins two MCP servers:

- **TradeTrack** (`hsbc-tradetrack-mcp`): tools `tradetrack` and `tradetrack_history`.
- **Interactive Brokers** (IBKR's official connector): account, quotes, contracts, order instructions.

The strategy has not been backtested. Run it on an IBKR paper account (account id starting with `DU`) until it has been.

## Parameters

Use these defaults unless the user overrides one in their request. Echo the values in the report.

| Parameter | Default | Meaning |
|---|---|---|
| `markets` | `US, HK` | Markets to scan |
| `min_hot_buy_pct` | 60 | If the stock is on the hot list, its `buy_pct` must be at least this |
| `exit_sell_all_pct` | 50 | Exit when the top 5% are fully exiting at least this share of their selling |
| `stop_loss_pct` | 8 | Exit when price is this % below average cost |
| `position_pct` | 5 | Target size of a new position, % of net liquidation value |
| `max_positions` | 10 | Open positions this strategy may hold per market |
| `limit_offset_pct` | 1 | Buy limit = last x (1 + offset); sell limit = last x (1 - offset) |

## Signals

- **Entry**: the stock is on the `top_buy` list with both `rank_today` and `rank_yesterday` set (the top 5% bought it two trading days in a row), it passes the hot-list check (absent from `hot`, or `buy_pct` >= `min_hot_buy_pct`), it does not meet the `top_sell` exit rule below (the top 5% can be buying and fully exiting the same stock), and it is not already held.
- **Exit**, for each held stock, the first that applies:
  - it is on `top_sell` with `sell_all_pct` >= `exit_sell_all_pct`;
  - its last price is `stop_loss_pct` or more below the position's average cost.

## Steps

1. **Fetch the lists.** Call `tradetrack` with `lists=["hot","top_buy","top_sell"]` for each market. A snapshot with `is_today: false` is the previous session's final list, which is what an order before the next open should act on; report each market's `trading_date` and `refreshed_at`. The top 5% lists refresh three times a day (US 11:30, 13:00, 16:00 ET; HK 12:30, 15:30, 16:10 HKT), so the signal is most complete after the last one. Done when every market has its three lists and their trading date.

2. **Read the account.** Call `get_flow_type` once, then `get_account_summary` and `get_account_positions`. Report the account id and whether it is paper (`DU...`). Done when you know net liquidation value, available funds and every position's symbol, quantity and average cost.

3. **Resolve contracts.** For every candidate (each entry candidate and each held stock that appears on a list), call `search_contracts`:
   - US: the row whose `symbol` equals the ticker exactly, `country_code` `US`.
   - HK: TradeTrack codes are zero-padded (`00700`); search without leading zeros (`700`) and take the `SEHK` row.
   - Keep only rows whose `sections` include `STK`. Drop warrants and anything unresolved, and list them as skipped.

   Then call `get_price_snapshot` with `market_data_names=["last","bid_ask"]` for each resolved contract. Done when every candidate has a contract id and a last price, or is listed as skipped with the reason.

4. **Apply the signals.** Evaluate every exit before any entry. Cap entries so open positions per market stay within `max_positions`, taking the best `top_buy` rank first. Size each entry as `floor(position_pct% x net liquidation / last)`, limited by available funds. HK shares trade in board lots that these tools do not expose: for HK, leave `quantity` unset and tell the user to set a whole number of lots when reviewing. Exits sell the full position. Done when every candidate has a decision: buy, sell, or skip with the reason.

5. **Confirm, then place.** Show the decision table (market, symbol, signal, list figures, last price, side, quantity, limit) and wait for the user's go-ahead. Then:
   - `REVIEW_AND_APPROVE`: `create_order_instruction` per decision with `contract_id_ex` (the contract id as a string), `side`, `quantity`, `order_type: "LIMIT"`, `limit_price`, `time_in_force: "DAY"`. Give the user each returned URL; nothing trades until they submit it in IBKR.
   - `AUTONOMOUS`: place the same orders with `submit_order`, following its own preview and question steps.

   Done when every approved decision has an instruction URL or an order id, and failures are reported with the error text.

## Report

End with: parameters used, data refresh time per market, the decision table, instruction URLs or order ids, and everything skipped with its reason.
