# Transaction Cost, Taxes, and Slippage Research V1

STATUS: RESEARCH INFRASTRUCTURE — NET ESTIMATE / COST ASSUMPTIONS

## Scope and frozen baseline

`INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` applies a deterministic cost overlay to the frozen `PORTFOLIO_BACKTEST_V1` long cash-equity delivery ledger. The output version is `PORTFOLIO_BACKTEST_V1_COSTED_RESEARCH`; it is not Strategy V2 and does not change signals, rankings, admissions, quantities, entry prices, exit prices, stop/target decisions, or the four-session horizon.

The baseline remains 728 trades, ₹86,107.226785713465 ending equity, -13.892773214286535% gross return, -3.182877736277989% CAGR, and 25.7681532620974% maximum drawdown before costs.

## Components and side semantics

Every trade exposes brokerage, STT, NSE exchange transaction charge, SEBI turnover charge, GST, stamp duty, DP charge, other regulatory cost, and slippage separately on buy and sell sides. Buy cash is reduced by effective entry notional plus buy charges. Sell cash is increased by effective exit proceeds less sell charges. GST is applied only to its explicit taxable fee base—brokerage, exchange charge, SEBI charge, DP charge, and other regulatory fees—not to security notional, STT, or stamp duty.

The baseline brokerage model is `ZERO_DELIVERY_RESEARCH_ASSUMPTION`; it is provider-neutral and is not a claim about every broker. The ₹13.50 sell-side DP charge is also a configurable research proxy rather than a universal retail tariff.

## Central rates and source status

The central effective-date schedule records value, basis, applicability, source status, research-assumption status, notes, and URL. NSE's published investor page supports 0.100% STT on both sides of delivered shares, 0.015% buyer stamp duty, 18% GST on stock-broking services, and ₹10/crore SEBI turnover fees. NSE circulars support the dated exchange-charge assumptions: the first member-turnover slab was ₹3.45/lakh before April 2023 and ₹3.25/lakh from April 2023; a uniform ₹2.97/lakh applies from 1 October 2024.

The pre-October-2024 exchange calculation uses the first published member-volume slab because the executing member's actual monthly tier is unavailable. STT is calculated per frozen trade side rather than reconstructed contract-note aggregation. Therefore the overall precision is `APPROXIMATE_RESEARCH_ASSUMPTION`, and every net output carries `NET_RESULTS_ARE_APPROXIMATE_RESEARCH_ESTIMATES`.

Sources:

- NSE, SEBI turnover fees, stamp duty, GST, and STT: https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies
- NSE circular dated 24 March 2023: https://nsearchives.nseindia.com/content/circulars/FA56129.pdf
- NSE circular dated 27 September 2024: https://nsearchives.nseindia.com/content/circulars/FA64232.pdf
- CBIC GST circular: https://cbic-gst.gov.in/pdf/circular-cgst-119.pdf
- CDSL DP tariff context: https://www.cdslindia.com/DP/CurrentDPs.html

## Rounding and slippage

Raw amounts are retained, while each side/component is rounded independently to ₹0.01 using `ROUND_HALF_UP`, then summed. This is deterministic but may differ from broker contract-note aggregation.

`SLIPPAGE_MODEL_V1` supports zero, fixed-bps, turnover-tiered, and a non-executable liquidity-aware future placeholder. The primary assumption is a preregistered 5 bps per side: long entries move upward and long exits move downward. The trigger path remains frozen; slippage changes only derived execution economics.

## Preregistered scenarios

- `COST-SCENARIO-001`: statutory/broker/DP costs with zero slippage.
- `COST-SCENARIO-002`: statutory/broker/DP costs plus 5 bps per-side slippage; primary net research estimate.
- `COST-SCENARIO-003`: statutory/broker/DP costs plus 10 bps per-side slippage; sensitivity only.
- `COST-SCENARIO-004`: zero-cost reference; must exactly reproduce the frozen gross baseline.

No other scenario is run, and assumptions are not selected from resulting P&L.

## Accounting boundary

The primary mode is `FROZEN_TRADE_SET_COST_OVERLAY`. Derived trade and daily ledgers live under `data/research/backtests/swing/portfolio/v1_costed/`. Costs are applied chronologically at entry and exit rather than subtracted only at the end. A separate cash-feasibility diagnostic records where the frozen trade would have been unaffordable after costs, but it never changes the 728 admissions or quantities.

## Limitations and readiness

This is historical research, not a broker statement, tax statement, live P&L, or liquidity-aware fill model. Actual broker tariffs, DP billing, tax rounding/aggregation, and market impact can differ. Daily OHLC cannot resolve intraday execution order, and frozen stop/target semantics remain authoritative. `LIVE_TRADING_READY` and `SMALL_CAPITAL_LIVE_READY` remain false.
