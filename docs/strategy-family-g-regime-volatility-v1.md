# InterSignal Strategy Family G — Regime / Volatility V1

Step 03.07 / Command 01 defines `STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1` under profile `QUARTERLY_MOMENTUM_REGIME_PARTICIPATION_V1` and protocol `FAMILY_G_RESEARCH_PROTOCOL_V1`. This command is specification, preregistration, architecture, and structural-pilot work only. It contains no new strategy performance run, validation access, promotion decision, or Strategy V2.

## Rationale and scope

Family G asks one narrow question: can a causal broad-market trend state decide whether the already-frozen Family A quarterly six-month momentum portfolio participates or stays in cash? It is distinct from Strategy V1's regime score. Family G V1 is a binary quarterly participation gate around one fixed underlying strategy; it is not a new multi-factor score and does not alter security ranking.

`CONTROL-G-000` (`QUARTERLY_6M_MOMENTUM_ALWAYS_PARTICIPATE_V1`) reuses `MOM-A-002` with the ₹500,000 `A2-002` implementation evidence. Its point-in-time NIFTY 500 universe, six-month ranking, quarterly schedule, top-decile selection, equal weighting, whole-share execution, ₹100 price floor, 20-session ₹100,000,000 median-traded-value liquidity floor, next-eligible-open execution, and frozen India equity delivery cost model remain unchanged. The previously recorded A2-002 result values are integrity references only and were not recalculated in this command.

Exactly one treatment is preregistered: `REGIME-G-001` (`QUARTERLY_6M_MOMENTUM_WITH_MARKET_TREND_GATE_V1`). On each frozen Family A formation date T, it uses the official local NIFTY 500 close and a simple moving average of the latest 200 valid NIFTY 500 sessions including T. The causal rule is strictly `close[T] > SMA200[T]`; equality fails. A pass executes the same Family A rebalance and holding set. A fail liquidates any prior equities and holds 100% cash, earning 0%, until the next scheduled quarterly rebalance. There is no daily recalculation, partial exposure, mid-quarter override, or emergency re-entry.

No VIX, volatility threshold, breadth measure, SMA slope, RSI, MACD, global-market input, GIFT Nifty input, or second condition is present. Although the family name includes volatility, V1 deliberately isolates the market-trend participation effect first.

## Frozen evidence criteria

Control reproduction must match the frozen schedule, candidate and ranking logic, selected symbols before whole-share effects, and cost semantics exactly. A future numerical reproduction must be within ₹0.01 of ending equity and within 0.01 percentage point of net return, net CAGR, and maximum-drawdown magnitude.

The treatment must preserve at least 85% of control net CAGR, reduce maximum-drawdown magnitude by at least 15%, remain absolutely profitable, have at least two nonnegative DEVELOPMENT years, not exceed control costs absent a documented implementation artifact, include at least six invested quarters, and have clean accounting and data integrity. Fewer than six invested quarters is `LIMITED_SAMPLE`; fewer than four is a fatal sample failure. Lower volatility, better Sharpe-like return, fewer negative quarters, and a better worst quarter are separately frozen quality dimensions. Upside capture and control return during treatment cash quarters are descriptive attribution only.

## Structural data readiness

The exact market series used is `NIFTY 500` from `data/reference/nse/indices/normalized/benchmark_daily.csv`, with official NSE provenance. The local series starts on 2021-09-07. It therefore provides only 141 valid causal sessions at the first 2022-03-31 formation date, rather than the required 200. Command 01 does not fabricate prehistory, silently switch to NIFTY 50, or use future rows. This produces `FAMILY_G_DATA_READINESS = READY_WITH_LIMITATIONS` and `FAMILY_G_ARCHITECTURE_RESULT = METHODOLOGY_FIX_REQUIRED`. The same authorized NIFTY 500 series must be extended backward before any DEVELOPMENT performance command.

All structural rows end at 2024-12-31. Validation is not authorized or accessed. The regime and accounting pilots verify strict-gate behavior, quarterly cash semantics, pass-date holding identity, fail-date zero holdings, whole shares, frozen transaction costs, and cash/equity reconciliation without evaluating returns.
