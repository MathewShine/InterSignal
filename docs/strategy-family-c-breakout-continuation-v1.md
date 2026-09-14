# Strategy Family C: Breakout Continuation V1

## Scope and rationale

`STRATEGY_FAMILY_C_BREAKOUT_CONTINUATION_V1` / `DAILY_BREAKOUT_CONTINUATION_V1` is a preregistered, long-only, event-driven swing research family governed by `FAMILY_C_RESEARCH_PROTOCOL_V1` and `RESEARCH_EXPERIMENT_GOVERNANCE_V2`. It asks whether a simple closing breakout has medium-short-horizon continuation edge after realistic costs, and whether either prior compression or formation-day volume expansion improves breakout quality.

Command 01 is specification, preregistration, architecture, and structural pilots only. It does not calculate returns, run final DEVELOPMENT performance, access validation, select a result, create Strategy V2, or start Family D. Promotion and validation remain prohibited.

## Independence and population

Family C does not use Strategy V1 score or regime, R:R score, CAP4, entry score, intraday confirmation, catalyst score, or sector score. It uses the reconstructed point-in-time Nifty 500, adjusted close of at least ₹100, 20-session median traded value of at least ₹10 crore/day, and the existing corporate-action structural exclusion layer. Current-constituent hindsight is prohibited.

The DEVELOPMENT partition is exactly 2022-01-01 through 2024-12-31. Pre-2022 `DAILY_HISTORY_PREHISTORY_V2` overlap is used only for causal lookbacks. No 2025-or-later data is loaded.

## Common portfolio and execution architecture

The executable research scale is ₹500,000. At most 20 positions may be open. Each new position targets 5% of current portfolio equity, limited by cash and whole-share execution. Existing positions are not rebalanced; leverage, shorting, derivatives, pyramiding, and adding to winners are prohibited. A symbol may re-enter only after its prior position has fully exited.

When valid same-day signals exceed available slots, they are ranked by `BREAKOUT_STRENGTH_PCT` descending and then symbol ascending. No discretionary selection is allowed.

Formation occurs at session T close. Entry is the next eligible NSE session open, T+1; same-close execution is prohibited. The actual T+1 open is accepted even after a positive gap, and a future evaluation must record `entry_gap_pct`. Positions are held for exactly ten completed sessions, T+1 through T+10, and exit at the next eligible open, conceptually T+11. There is no stop loss, profit target, or trailing stop. If signal quality is not positive under this common horizon, exit optimization must not manufacture an edge; later exit research requires separate authorization.

## Frozen control and treatments

`CONTROL-C-000` (`PURE_20D_CLOSE_BREAKOUT_V1`) requires adjusted close at T to be strictly greater than the maximum adjusted high of the previous 20 valid sessions, T-20 through T-1. Formation T is excluded. Missing history produces no signal, and the lookback is never shortened. Breakout strength is `formation_close / prior_20_session_high - 1`.

`BRK-C-001` (`20D_BREAKOUT_WITH_10D_COMPRESSION_V1`) uses the exact control breakout plus:

`(max(high[T-10..T-1]) - min(low[T-10..T-1])) / close[T] <= 0.08`.

The ten sessions are immediately before T; the inclusive 8% threshold is fixed.

`BRK-C-002` (`20D_BREAKOUT_WITH_VOLUME_EXPANSION_V1`) uses the exact control breakout plus:

`volume[T] / median(volume[T-20..T-1]) >= 1.50`.

The formation session is excluded from the 20-session median. The compression and volume filters are isolated; no combined filter exists in Family C V1.

## Costs and future reporting

A future DEVELOPMENT evaluation must use `INDIA_EQUITY_COST_MODEL_V1`, `NSE_CASH_DELIVERY_RESEARCH_V1`, `COST-SCENARIO-002`, and 5 bps slippage per side. The architecture supports entry/exit prices and dates, gross and net position return, MFE, MAE, holding sessions, entry gap, transaction costs, cash, equity, open positions, slots, intended and actual notional, shares, residual cash, and capacity rejection.

The preregistration freezes future reporting of net total return, net CAGR, max drawdown, annualized volatility, Sharpe-like ratio, position count and win rate, average winner and loser, median return, expectancy, profit factor, positive-month rate, each 2022–2024 return, turnover, transaction costs, average concurrent positions, capacity rejection rate, and average cash.

`HIGH_WIN_RATE_FLAG = YES` at position win rate of at least 60%. It is descriptive only and is not independently required for support.

## Frozen success and failure criteria

The control is viable only when all hold: net CAGR above zero; profit factor at least 1.05; net expectancy above zero; drawdown magnitude at most 35%; at least two of three years nonnegative; at least 100 closed positions; and accounting/data integrity passes. Fatal control failure occurs at net CAGR at most -5%, profit factor below 0.90, drawdown above 45%, fewer than 50 closed positions, or implementation/data failure.

Treatments use seven standard criteria: 90% CAGR preservation when control CAGR is positive (otherwise absolute profitability); positive expectancy and profit factor at least 1.10; drawdown not worse by more than 10% (fatal above 20%); at least two nonnegative years and no more than one year lagging control by over 15 percentage points; normalized cost drag no more than 1.30 times control unless turnover is lower; at least 75 positions for normal interpretation (50–74 limited and below 50 fatal); and clean accounting/data integrity.

Quality dimensions are win-rate improvement of at least 5 percentage points, profit-factor improvement of at least 0.05, expectancy at least 1.10 times a positive control (or positive when control is nonpositive), and relative drawdown improvement of at least 10%. Capacity is material when more than 25% of otherwise-valid signals are rejected because all 20 slots are occupied.

`STRONGLY_SUPPORTED` requires all seven standard criteria, at least two quality dimensions, CAGR not below control, and no negative year. `SUPPORTED` requires all standard criteria and at least one quality dimension. `PARTIALLY_SUPPORTED` requires no fatal failure, at least five standard criteria, and interpretability. `FAILED` means any fatal condition or fewer than five standard criteria; `INCONCLUSIVE` is reserved for unresolved data or mechanics. No classification is assigned in Command 01.

## Governance and readiness

All fourteen Governance V2 fields are persisted: hypothesis, experiment ID, population, exact parameters, control, primary metrics, secondary metrics, numerical success criteria, failure criteria, stop conditions, validation eligibility, cost model, data partition, and hashes. Future performance must verify `success_criteria_hash` before evaluation.

Validation is not authorized or accessed. A future candidate can become `ELIGIBLE_FOR_VALIDATION_DESIGN` only after clean DEVELOPMENT evaluation, sufficient sample, no unresolved attribution/data issue, no parameter mutation, governance review, and explicit human approval.

Structural counts, signal overlap, causal lookback availability, next-open and holding-path availability, deterministic capacity occupancy, and synthetic signal/chronology/cost-accounting pilots are allowed. None inspects outcomes. Known limits are the declared partial reconstructed-membership history and incomplete T+11 paths for the final 2024 formations when prohibited 2025 data is not loaded.
