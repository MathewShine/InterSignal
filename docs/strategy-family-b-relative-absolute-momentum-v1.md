# InterSignal Strategy Family B — Relative + Absolute Momentum V1

Status: `PREREGISTERED_RESEARCH_FAMILY`
Version: `STRATEGY_FAMILY_B_RELATIVE_ABSOLUTE_MOMENTUM_V1`
Profile: `RELATIVE_PLUS_ABSOLUTE_MOMENTUM_V1`
Protocol: `FAMILY_B_RESEARCH_PROTOCOL_V1`
Governance: `RESEARCH_EXPERIMENT_GOVERNANCE_V2`

This document freezes the Family B hypothesis, parameters, controls, numerical decision rules, and structural-validation boundary before any Family B performance evaluation. Step 03.02 / Command 01 does not compute a final development result, inspect future returns, access validation, or create Strategy V2.

## Rationale and distinction from Family A

Family A ranks stocks relative to other members of the point-in-time Nifty 500. A stock can therefore rank highly while its own trend is negative in a broadly weak market. Family B tests whether retaining the fixed Family A 6M cross-sectional ranking while adding a simple stock-level absolute condition improves downside robustness without destroying return quality.

Family B does not modify or rerun Family A. It defines two new treatments and compares them later with a read-only reference to the frozen MOM-A-002 architecture. It does not add a market or Nifty regime filter and is not an explicit market-timing system. When few stocks pass, the portfolio naturally holds fewer names or cash.

## CONTROL-B-000

`CONTROL-B-000` is a `REFERENCE_CONTROL` and must not be relabeled as Family B. Its underlying architecture is the frozen `MOM-A-002` design:

- 6M compounded cross-sectional momentum, descending rank;
- point-in-time Nifty 500 with the frozen infrastructure gates;
- top-decile, long-only, equal-weight selection;
- quarterly formation and next-eligible-session-open execution;
- no leverage, stop, or target;
- ₹500,000 executable whole-share research capital; and
- any mechanical reproduction is labeled `CONTROL_REPRODUCTION_ONLY`.

The ₹500,000 amount is inherited from Family A A2-002 as the practical implementation-fidelity reference for broad 20–35-name whole-share portfolios. It is not an alpha parameter, profitability assumption, live-capital recommendation, or proof that higher capital is inherently superior.

## Frozen population and infrastructure

The development partition is exactly 2022-01-01 through 2024-12-31. No 2025+ or validation data is authorized.

All records use the existing point-in-time Nifty 500 reconstruction; current-constituent substitution is forbidden. Before ranking, a stock must satisfy:

- price at least ₹100;
- 20-session median traded value at least ₹10 crore per day;
- corporate-action research safety;
- valid required adjusted history;
- point-in-time membership; and
- an executable next eligible NSE-session open.

## Shared relative-momentum rule

Both experiments calculate the 126-trading-session (6M) compounded return and rank eligible stocks descending, breaking ties by symbol ascending. The candidate entry pool is the top 10%, rounded up from the eligible-universe count. The signal, lookback, rank direction, and percentile are fixed for Family B V1.

## MOM-B-001

Name: `RELATIVE_6M_PLUS_ABSOLUTE_6M_POSITIVE_V1`

A stock qualifies only when it is in the relative 6M top decile and its same 6M compounded return is strictly greater than zero. An exact zero is rejected. There is no buffer and no alternative +2%, +5%, or +10% threshold.

This experiment tests the simplest absolute-momentum interpretation: a stock must be strong relative to peers and actually positive over the same trailing horizon.

## MOM-B-002

Name: `RELATIVE_6M_PLUS_200DMA_TREND_V1`

A stock qualifies only when it is in the relative 6M top decile and its formation-date adjusted close is strictly greater than its 200-session simple moving average. Equality is rejected. SMA200 uses exactly the most recent 200 valid adjusted-close observations available through formation; future observations and calendar-day approximations are forbidden. With fewer than 200 valid observations, the absolute signal is unavailable.

This experiment tests a conventional long-term trend-state interpretation. No other moving average or tolerance band is authorized.

## Portfolio and execution contract

Formation occurs at the eligible quarter-end NSE session close and execution at the next eligible NSE session open; same-close execution is prohibited. Qualifying names receive equal target weights based on available portfolio equity. Executable evaluation uses whole shares, includes the frozen cost engine, and leaves residual whole-share cash as cash.

Positions are held until the next quarterly rebalance. There is no interim absolute-momentum exit, retention band, stop, or target. Entry and retention use the same current-quarter rules.

No backfilling is allowed. If only 12 top-decile candidates pass the absolute condition, the portfolio holds 12 names. Lower-ranked stocks cannot be added to reach a target count. At least 10 securities must qualify for portfolio formation. When fewer than 10 qualify, record `INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH`; do not force formation. Existing holdings are liquidated at the scheduled rebalance unless they independently satisfy the current Family B rules, and the portfolio may remain in cash.

## Cost and capital model

All three records use exactly:

- `INDIA_EQUITY_COST_MODEL_V1`;
- `NSE_CASH_DELIVERY_RESEARCH_V1`;
- `COST-SCENARIO-002`; and
- 5 basis points of slippage per side.

The primary later evaluation mode is `EXECUTABLE_INTEGER_SHARE_500K`. `IDEALIZED_EQUAL_WEIGHT_PERCENTAGE` is supported only as an implementation diagnostic, and practical decisions must prioritize executable results.

## Frozen future metrics

The future evaluation must report net total return, net CAGR, max drawdown, annualized volatility, a Sharpe-like metric, positive calendar-month rate, positive rebalance-period rate, annualized turnover, total modeled costs, average invested percentage, average cash percentage, minimum and median holdings, and yearly returns.

## Frozen numerical success criteria

Standard support requires all criteria A–G:

A. `RETURN_PRESERVATION`: treatment net CAGR is at least 85% of CONTROL-B-000 net CAGR.

B. Drawdown: absolute max-drawdown magnitude improves by at least 15% relative, or at minimum does not worsen by more than 10% relative. Material improvement is `(control magnitude - treatment magnitude) / control magnitude >= 0.15`.

C. Temporal support: at least two of the three development years have treatment net return at least zero, and treatment underperforms control by more than 15 percentage points in no more than one year.

D. Cost efficiency: normalized modeled cost drag increases by no more than 25% relative to control.

E. Breadth: at least 80% of scheduled development rebalances have at least 10 qualifying holdings.

F. Capital deployment: average cash allocation is no more than 35%.

G. Accounting and data integrity pass.

The allowed future experiment labels are `STRONGLY_SUPPORTED`, `SUPPORTED`, `PARTIALLY_SUPPORTED`, `FAILED`, and `INCONCLUSIVE`. `SUPPORTED` means supported for further research; it is not deployment approval.

`STRONGLY_SUPPORTED` requires all standard criteria plus at least 90% CAGR preservation, at least 15% relative drawdown improvement, no negative development year, and clean accounting.

`PARTIALLY_SUPPORTED` is allowed only with no fatal failure, at least four of A–G passing, and an interpretable result.

## Frozen fatal failure criteria

Any one of the following requires `FAILED`:

- treatment CAGR is strictly below 70% of control CAGR;
- drawdown magnitude worsens by strictly more than 20% relative;
- fewer than 60% of scheduled rebalances have at least 10 qualifying names;
- average cash is strictly above 50%;
- an implementation or data failure occurs; or
- lookahead is detected.

The success criteria and fatal criteria are persisted in `governance/success_criteria_v1.json` and bound by `success_criteria_hash`. A future performance command must verify that hash before evaluation. Post-hoc threshold creation is prohibited.

## Structural validation completed by Command 01

Command 01 is limited to signal-rule fixtures, structural breadth counts, an exact SMA200 reconciliation, a relative-rank reconciliation, a one-rebalance whole-share accounting pilot for each treatment, and no-lookahead checks. These artifacts contain no final equity curves and do not assign an experiment or family performance classification.

The local adjusted-history series begins on 2021-09-07. Consequently, MOM-B-002 has no SMA200 signal at the first 2022 quarterly formation. This is recorded as a data-readiness limitation, not silently backfilled and not treated as performance evidence.

## Governance V2 and validation

The preregistration checklist records all 14 required items: hypothesis, experiment ID, population, exact parameters, control, primary and secondary metrics, numerical success criteria, failure criteria, stop conditions, validation eligibility, cost model, data partition, and hashes.

Family B validation is `NOT_AUTHORIZED` and was not accessed. A treatment may become `ELIGIBLE_FOR_VALIDATION_DESIGN` only after a passing development evaluation, no unresolved data issue, no parameter mutation, governance review, and explicit later human approval. Validation never follows automatically from the first development run.

No live signals, orders, broker calls, remote migrations, or Supabase writes are part of this research protocol.
