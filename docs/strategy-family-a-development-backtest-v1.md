# Strategy Family A development backtest V1

## Scope and frozen linkage

`FAMILY_A_DEVELOPMENT_BACKTEST_V1` evaluates the three baselines preregistered under `STRATEGY_FAMILY_A_MOMENTUM_V1`. Before any performance calculation, the runner verifies family config hash `becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3` and the frozen parameter and preregistration hashes for `MOM-A-001`, `MOM-A-002`, and `MOM-A-003`.

The input window is 2022-01-01 through 2024-12-31 only. No 2025–2026 price or Family A validation performance is loaded. The result is development evidence, not validation or production authorization.

No parameter changed after results. The point-in-time Nifty 500 universe, ₹100 price floor, ₹10-crore 20-session median traded-value gate, top decile, equal weighting, next-open execution, ₹100,000 capital, long-only direction, no leverage, no stops or targets, and frozen cost assumptions remain exactly as preregistered. No extra strategy variant, alternate capital, absolute momentum, market regime, volatility scaling, fundamental filter, hysteresis, or Strategy V2 was introduced.

## Portfolio and execution accounting

Signals are formed at the prior eligible period-end close and orders execute at the next eligible NSE session open. Each valid rebalance determines the selected top decile, retains continuing names, sells removals and excess retained shares first, adds sale proceeds less sell costs to cash, then buys additions and retained-position increases in deterministic signal-rank/symbol order. Every purchase is capped by cash including its buy-side costs. Residual cash remains in the portfolio.

When a scheduled formation has fewer than 20 selected names, the rebalance is recorded as `INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO`; rules are not loosened. A held name that leaves point-in-time membership remains until the next valid scheduled rebalance. Missing execution opens defer an exit rather than inventing a price, although no fatal accounting failure arose in this run.

Adjusted prices from `PRICE_ADJUSTED_STRUCTURAL_V1` are used directly for signals, executions, and valuations. This keeps supported split/bonus continuity in one price basis and avoids a second share or price adjustment. Exact signal endpoints are never forward-filled. Missing daily closes for an already-held security use the latest known adjusted close only for marked valuation, not for signal formation or execution.

Executable gross results are a same-realized-holdings cost overlay: gross equity equals cost-adjusted cash plus holdings value plus cumulative charged costs. This isolates cost drag without creating a separate, potentially different integer-share trade path. Net equity deducts costs chronologically and drives later affordability and target-share calculations.

## Idealized versus executable modes

`IDEALIZED_EQUAL_WEIGHT_PERCENTAGE` permits fractional-share-equivalent holdings and rebalances to equal percentage weights without affordability constraints. It preserves realistic turnover. Percentage-like statutory, exchange, GST, stamp, and slippage costs are applied as a cumulative overlay. Flat sell-order DP charges and their associated GST are reported separately as excluded, so the status is `IDEALIZED_COST_MODEL_LIMITED` rather than a claim of executable realism.

`EXECUTABLE_INTEGER_SHARE_100K` uses whole shares, ₹100,000 initial cash, sell-before-buy chronology, full `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` costs, 5 bps slippage per side, sell-only DP charges, buy-side stamp duty, and explicit residual cash.

## Development results

These tables are a `RELATIVE_BASELINE_COMPARISON`; no row is labelled best, winner, or optimal.

| Baseline | Mode | Gross end | Net end | Net return | Net CAGR | Net max drawdown | Annualized turnover | Costs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MOM-A-001 | Idealized | ₹269,715.99 | ₹263,342.26 | 163.34% | 38.12% | -23.09% | 8.25x | ₹6,373.73 |
| MOM-A-001 | Executable | ₹233,504.41 | ₹220,370.85 | 120.37% | 30.16% | -20.57% | 7.23x | ₹13,133.56 |
| MOM-A-002 | Idealized | ₹199,285.03 | ₹196,376.87 | 96.38% | 25.25% | -23.30% | 4.43x | ₹2,908.16 |
| MOM-A-002 | Executable | ₹183,027.82 | ₹177,227.81 | 77.23% | 21.03% | -21.32% | 3.93x | ₹5,800.01 |
| MOM-A-003 | Idealized | ₹228,186.44 | ₹224,106.39 | 124.11% | 30.89% | -17.48% | 5.47x | ₹4,080.05 |
| MOM-A-003 | Executable | ₹208,432.57 | ₹199,437.15 | 99.44% | 25.89% | -16.30% | 4.85x | ₹8,995.42 |

The idealized net values are limited cost overlays; executable values include the full flat DP/order effects and cash-constrained whole-share mechanics.

### Executable yearly results

| Baseline | 2022 net return | 2023 net return | 2024 net return | 2022/2023/2024 net max drawdown |
|---|---:|---:|---:|---|
| MOM-A-001 | 13.87% | 48.73% | 30.12% | -20.57% / -15.99% / -14.95% |
| MOM-A-002 | 1.92% | 46.51% | 18.69% | -21.32% / -16.04% / -12.92% |
| MOM-A-003 | 2.16% | 56.28% | 24.92% | -9.64% / -13.04% / -15.28% |

All three had positive net calendar-year results, but all finished development in an unrecovered drawdown. Rebalance-period success rates were 61.76% for MOM-A-001, 80.00% for MOM-A-002, and 50.00% for MOM-A-003. These are portfolio-period statistics, not trade win rates.

## Turnover, costs, and capital distortion

MOM-A-002's quarterly schedule reduced annualized executable turnover to 3.93x versus 7.23x for monthly 6M momentum and reduced total executable costs to ₹5,800.01 versus ₹13,133.56. Its lower-frequency development return was also lower; the evidence is a trade-off, not a winner declaration.

MOM-A-003 had lower executable turnover, lower total costs, and a shallower aggregate drawdown than MOM-A-001, alongside a lower development return. Again, this is descriptive comparison only.

Executable average residual cash was 12.66% for MOM-A-001, 13.12% for MOM-A-002, and 12.35% for MOM-A-003. Maximum residual cash was 25.18%, 21.80%, and 21.54%, respectively. All three are `HIGH_DISTORTION` / `MATERIAL` capital-scale limitations at ₹100,000. No alternate capital amount was tested.

Turnover efficiency is `ACCEPTABLE` for all three. Cost efficiency is `WEAK` for MOM-A-001 and `MIXED` for MOM-A-002 and MOM-A-003. The classifications follow centrally encoded thresholds and do not alter any strategy input.

## Risk, stability, and result classifications

All three baselines are classified:

- `RETURN_QUALITY=STRONG`
- `RISK_QUALITY=ACCEPTABLE`
- `TEMPORAL_STABILITY_QUALITY=STRONG`
- `FAMILY_A_TEMPORAL_STABILITY=CONSISTENT`
- `FAMILY_A_BASELINE_RESULT=PROMISING`

`PROMISING` means only that the baseline produced sufficient development evidence to justify consideration for further development research. It does not mean validated.

The conservative Phase 2 gate additionally requires the executable portfolio never to fall below 20 actual holdings. MOM-A-002 satisfies that gate (`YES`); MOM-A-001 and MOM-A-003 reach 19 actual holdings at least once because of ₹100,000 whole-share constraints and are `NO`. Because at least one baseline survives, `FAMILY_A_PHASE2_AUTHORIZATION_CANDIDATE=YES`. This is a candidate status only and does not authorize Phase 2 automatically.

The family-level result is `FAMILY_A_DEVELOPMENT_RESULT=PROMISING_FAMILY`. No historical winner is selected.

## Verification and immutability

The actual-data pilot passed 14 of 14 checks covering monthly and quarterly timing, 6M and 12–1 ranks, top-decile membership, retention/removal/addition, idealized and integer allocations, an unaffordable stock, buy and sell costs, and full rebalance accounting. Cash and equity reconciliation violations are both zero at tolerance ₹0.000001.

The original Command 01 config and preregistration registry remain unchanged. A derived development registry records `DEVELOPMENT_EVALUATED` status and immutable result hashes. Any parameter or rule modification requires a new experiment ID or version.

No Family A validation was accessed or authorized. No live signal, order, broker call, migration, Supabase persistence, or Strategy V2 was created.
