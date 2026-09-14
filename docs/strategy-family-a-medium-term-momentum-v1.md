# Strategy Family A — Medium-Term Momentum V1

## Identity and purpose

- Family version: `STRATEGY_FAMILY_A_MOMENTUM_V1`
- Research profile: `MEDIUM_TERM_CROSS_SECTIONAL_MOMENTUM_V1`
- Family code: `FAMILY_A`
- Protocol: `FAMILY_A_RESEARCH_PROTOCOL_V1`
- Command: Step 03.01 / Command 01

Family A asks whether a lower-turnover portfolio of the strongest medium-term NSE stocks can produce a more stable, cost-efficient edge than Strategy V1's short-horizon breakout approach. It is an independent factor-portfolio research family. Strategy V1 scoring, R:R rules, CAP4, intraday confirmations, stops, targets, and the V1 maximum-four-position engine are not inputs.

The external basis and limitations are recorded separately in [strategy-family-a-literature-notes-v1.md](research/strategy-family-a-literature-notes-v1.md).

## Exactly three preregistered baselines

| ID | Name | Signal | Rebalance | Purpose |
|---|---|---|---|---|
| MOM-A-001 | SIX_MONTH_MOMENTUM_MONTHLY | 6M compounded return | Monthly | Straightforward medium-term momentum with monthly updating |
| MOM-A-002 | SIX_MONTH_MOMENTUM_QUARTERLY | 6M compounded return | Quarterly | The same signal with a lower-frequency rebalance architecture |
| MOM-A-003 | TWELVE_MINUS_ONE_MOMENTUM_MONTHLY | 12M excluding the last 1M | Monthly | Conventional skip-month momentum architecture |

All three have status `PREREGISTERED` and `promotion_allowed=false`. Their only differences are signal and rebalance frequency. The registry is the experiment allowlist; the generic 3M, 9M, and raw 12M calculators do not authorize additional experiments.

## Universe and data eligibility

The research universe is point-in-time Nifty 500 using the existing reconstructed membership intervals. Current constituents are never applied retrospectively. Membership source confidence and partial-history warnings stay attached to every signal row.

At each formation date a security must have:

- active point-in-time membership;
- adjusted close of at least ₹100;
- exactly 20 trading-session observations for median adjusted-close × adjusted-volume traded value, with median of at least ₹10 crore per day;
- exact signal endpoint observations;
- corporate-action-safe adjusted endpoints and no overlapping unsafe eligibility window; and
- an available positive next-session adjusted open.

Missing history or prices make the security unavailable. Future values are never backfilled. Membership exits and delistings are handled from then-known membership state and scheduled rebalance rules, without hindsight.

## Signals and causal timing

Lookbacks use exact NSE trading-session indices:

- 3M: formation close divided by close 63 sessions earlier, minus one;
- 6M: formation close divided by close 126 sessions earlier, minus one;
- 9M: formation close divided by close 189 sessions earlier, minus one;
- 12M: formation close divided by close 252 sessions earlier, minus one;
- 12M_EX_LAST_1M: close 21 sessions before formation divided by close 252 sessions before formation, minus one.

Monthly formation is the last eligible trading-session close of each month. Quarterly formation uses March, June, September, and December month-end sessions. Execution is the next eligible trading-session open. A formation close is never used for same-close execution. Portfolios hold until the next scheduled rebalance.

## Ranking, breadth, and weights

Authorized signals are ranked descending cross-sectionally. Symbol ascending is the deterministic tie-break. The top `ceil(eligible universe × 10%)` names are selected only when this produces at least 20 holdings; otherwise the date is flagged and no rule is loosened.

All positions are equal weight. The maximum position weight is therefore `1 / selected holdings`. Position count is derived from the top decile and is not capped at four. The strategy is long-only, unlevered, cash-equity only, with no shorting, derivatives, stop, target, or intraday rule.

## Rebalance and turnover

At every scheduled next-open rebalance, the engine retains names still selected, sells removals, buys additions, and adjusts retained names toward equal weight. It records traded notional separately for exits, entries, and retained-name weight adjustments. One-way turnover is total rebalance traded notional divided by portfolio value; round-trip-equivalent turnover divides by twice portfolio value; annualized turnover is the sum of one-way rebalance turnover within the year.

No hysteresis or no-trade band is present in the baseline.

## Costs and capital

Both `IDEALIZED_EQUAL_WEIGHT_PERCENTAGE` and `EXECUTABLE_INTEGER_SHARE_100K` architectures are prepared. The practical mode uses ₹100,000, next-open prices, floor-rounded integer shares, and explicit cash residual. Intended and actual weights, unaffordable positions, and missing execution prices are reported. Severe distortion is flagged without changing the top-decile rule or testing another capital size.

Scheduled orders use frozen `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` with preregistered `COST-SCENARIO-002` (5 bps slippage per side). The cost integration includes STT, exchange transaction charges, SEBI charges, GST, buy-side stamp duty, sell-side DP charge, configured brokerage, other-regulatory components, and slippage. A later performance command must always report gross and cost-adjusted results.

## Development and validation governance

The development window is 2022-01-01 through 2024-12-31. Command 01 creates definitions, deterministic inputs, structural pilots, readiness audits, and hashes only. It computes no post-formation portfolio performance, compares no baseline returns, and chooses no winner.

Family A validation is not authorized and was not accessed. Any later 2025–2026 evaluation must be labelled `FORMAL_HOLDOUT_WITH_PRIOR_MARKET_EXPOSURE`, because those market years were seen in aggregate during Strategy V1 research. CAP4's consumed validation remains a separate historical lifecycle and cannot be reused for Family A tuning.

The future performance command has preregistered return, risk, cost, stability, and turnover metrics. Highest win rate alone may not select a candidate. Allowed future baseline classifications are `PROMISING`, `MIXED`, `WEAK`, `FAILED`, and `INCONCLUSIVE`; none is emitted here. Command 01 emits only data and architecture readiness.

## Storage and safety

Family artifacts are under `data/research/strategy_families/family_a/v1/` with `registry`, `signals`, `rebalance_calendar`, `pilot`, and `manifests` subdirectories. Machine summaries are under `data/reports/`. These are offline research artifacts: zero live signals, orders, broker calls, provider headers, migrations, or Supabase persistence.

## Later controlled possibilities

Potential Phase 2 work includes separately preregistered absolute-momentum confirmation, regime or volatility analysis, no-trade bands, alternate capital-scale diagnostics, and other portfolio mechanics. They are not authorized experiments in this version and must not be inferred from the generic calculator support.
