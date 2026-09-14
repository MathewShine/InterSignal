# Family A Phase 2 Controlled Research V1

## Scope and purpose

`FAMILY_A_PHASE2_RESEARCH_V1` uses the `MOMENTUM_IMPLEMENTATION_EFFICIENCY_V1` profile. It exists because Family A produced positive development evidence while also showing material turnover, transaction-cost, and small-capital implementation concerns. This command preregisters two implementation hypotheses; it does not search for a different signal and does not evaluate performance.

The frozen reference is `MOM-A-002`: 6-month compounded cross-sectional momentum, quarterly rebalancing, top-decile selection, equal weights, long only, and ₹100,000 starting capital. It is a reference—not a best, winner, or optimal strategy. Its immutable Command 01 parameter/preregistration hashes and Command 02 result hash are linked in the Phase 2 registry.

## A2-001 — MOMENTUM_RETENTION_BAND_V1

New positions may enter only in the top 10%. An existing holding may remain through a scheduled quarterly rebalance while it ranks in the top 15%. A holding exits outside the top 15%, or immediately when any mandatory point-in-time universe, ₹100 price, 20-session ₹10-crore median traded-value, valid-data, or corporate-action eligibility rule fails. Exits are replaced from current top-10% candidates in deterministic momentum-rank then symbol order. Retained and new positions are recalculated to equal weights.

The 10/15 rule creates one modest five-percentage-point hysteresis band while preserving the original entry definition. No 10/12, 10/20, 10/25, or other band is evaluated. Capital remains exactly ₹100,000 so the later experiment can isolate the retention-band effect.

The future development test will compare additions, removals, annualized/average/median/p90 turnover, retention, and transaction costs directly with the frozen ₹100,000 MOM-A-002 executable baseline. It will also examine the preregistered performance-safety metrics; no one-number CAGR, ending-equity, or win-rate rule may select an experiment.

## A2-002 — CAPITAL_FEASIBILITY_500K_V1

A2-002 is identical to MOM-A-002 except that starting capital is exactly ₹500,000. No ₹200k, ₹300k, ₹400k, ₹750k, ₹1m, ₹2.5m, or other capital is tested.

Family A typically selects about 20–35 names. At ₹100k, intended capital per position is approximately ₹2.9k–₹5k; at ₹500k it is approximately ₹14k–₹25k. The hypothesis is that ₹500k materially reduces unaffordable holdings, residual cash, equal-weight tracking error, and whole-share distortion. No performance advantage is assumed.

The future comparison will measure intended and actual holdings, unaffordable holdings, average/median/maximum cash percentage, actual invested percentage, intended-versus-realized weight error, and tracking difference from the idealized percentage portfolio. Percentage returns and equity curves normalized to 100 will be compared; raw rupee P&L cannot be evidence of superiority. Costs will be shown both in rupees and as a percentage of starting or evolving equity.

## Frozen shared methodology

Both experiments keep the 6M signal, quarterly schedule, point-in-time Nifty 500 universe, top-decile entry, equal weighting, next-eligible-session-open execution, ₹100 price gate, 20-session median traded-value gate of ₹10 crore, and the exact `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` / `COST-SCENARIO-002` model with 5 bps per-side slippage. There is no leverage, shorting, stop, target, intraday logic, absolute momentum, regime filter, volatility filter, or fundamentals overlay.

The only permitted period is DEVELOPMENT, 2022-01-01 through 2024-12-31. Family A validation and all 2025+ data remain inaccessible to this command. There is no parameter grid.

## Structural pilots and future metrics

The A2-001 pilot verifies the six boundary/eligibility decisions, deterministic replacement, and equal-weight recalculation using synthetic structural fixtures. The A2-002 pilot applies identical frozen MOM-A-002 selected symbols and next-open prices at one development rebalance to ₹100k and ₹500k ledgers. It verifies whole shares, affordability, nonnegative residual cash, weight error, normalized equity, and cost reconciliation. These are architecture checks—not full development backtests or performance findings.

Future performance-safety metrics are net CAGR, net total return, maximum drawdown, annualized volatility, positive-month rate, positive-rebalance-period rate, yearly return, and cost drag. The turnover and capital classifications are preregistered in the machine config and remain `NOT_EVALUATED` until a separate authorized command.

## Governance

Exactly `A2-001` and `A2-002` are registered as `PREREGISTERED` with `promotion_allowed=false`. Command 03 creates no Strategy V2, declares no winner, accesses no validation data, runs no performance test, emits no live signal/order, calls no broker, performs no database migration, and writes nothing to Supabase.
