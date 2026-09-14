# Strategy Family E: Pullback / Reclaim Continuation V1

## Rationale and independence

Family E asks whether an established upward-trending NSE stock can continue after a controlled short-term pullback and bullish reclaim, and whether preserving the broader SMA50 structure throughout that pullback improves setup quality. It isolates trend → pullback → reclaim → continuation. It does not use Strategy V1 scoring, CAP4, market regime, news, sector scores, intraday confirmation, Family C breakout rules, or Family D opening-range logic.

## Frozen specification

The point-in-time Nifty 500 DEVELOPMENT window is 2022-01-01 through 2024-12-31, using `DAILY_HISTORY_PREHISTORY_V2` only for causal indicators. Adjusted close must be at least ₹100; 20-session median traded value must be at least ₹10 crore/day; the frozen corporate-action eligibility layer applies. The family is long-only, unlevered, event-driven, and uses ₹500,000 research capital, 0.50% current-equity risk per trade, whole shares, available cash, one position per symbol, no pyramiding, and at most 10 concurrent positions.

`CONTROL-E-000` (`TREND_PULLBACK_RECLAIM_V1`) requires at T: close > SMA50, SMA20 > SMA50, and 20-session compounded return >0. The pullback window is exactly T-5 through T-1, with at least one low <= that session's SMA20. T must close strictly above both T-1 high and SMA20(T). The control does not require every pullback close to remain above SMA50.

`PBR-E-001` (`TREND_PULLBACK_RECLAIM_WITH_50DMA_STRUCTURE_V1`) keeps every control rule and adds exactly one filter: every close from T-5 through T-1 must be >= that session's SMA50. Equality passes. No distance, ATR-depth, percentage-decline, Fibonacci, volume, RSI, MACD, stochastic, ADX, breakout, or other treatment was added.

Signal formation is T close; entry is the next eligible session open with the actual gap accepted and recorded. The stop is the minimum adjusted low over T-5 through T inclusive, without an ATR buffer. A valid entry must be strictly above the stop. There is no target or trailing stop. A stop is evaluated before the time exit, with a gap below the stop executed at the actual session open. The time exit is the open after 10 completed holding sessions. Required paths crossing into 2025 are excluded rather than completed with validation-era data.

Both control and treatment use 20-session return descending, then symbol ascending, when entry-ready signals exceed available slots.

## Structural audit

The structural scan produced 199,915 eligible universe rows, 84,980 trend-pass rows, 39,150 pullback-touch rows, 10,754 control signals, and 8,343 E001 signals. E001 subset violations are 0; the SMA50 structure filter removed 22.41956481309280267807327506% of control signals. These are structural counts only, not performance.

## Frozen evaluation criteria

The control later requires positive net expectancy and CAGR, PF >=1.05, drawdown <=30%, at least two nonnegative DEVELOPMENT years, at least 150 closed positions, and accounting/data integrity. Fatal thresholds are PF <0.90, expectancy <=-0.10%, CAGR <=-5%, drawdown >40%, fewer than 75 positions, or implementation/data failure.

Treatment return preservation is at least 85% of positive control CAGR (otherwise positive CAGR), with positive expectancy and PF >=1.10. Quality thresholds are +5 percentage points win rate, +0.05 PF, 1.10x positive-control expectancy (otherwise positive), and at least 10% relative drawdown improvement. Temporal, cost, sample, and accounting rules are frozen in `governance/success_criteria_v1.json`. `HIGH_WIN_RATE_FLAG=YES` at position win rate >=60%; it is descriptive only.

## Governance state

`family_e_config_hash`: `7e73a24b0c3d52c2727e36f38e607eb20e2c8369f4de743267ecd2eab101f6c3`
`CONTROL-E-000 reference hash`: `05e66547c89a74926810351898f848dbedc0f7b4282fe87f04d1cde7a99bd212`
`PBR-E-001 parameter hash`: `a64ff19f3de639baf3b5a9d701f3683d46e805ccbccba32840b3532c4ba81cc0`
`PBR-E-001 preregistration hash`: `7b0e988c7e49b0fa3f7e92a213e991cd5880ad2d0747279b2a29aa7f664a8108`
`family_e_success_criteria_hash`: `f9a685f3458f13cb7bc2b3d5df3a1bab86d544246d59be6f2ca48889fa96ad5f`

`FAMILY_E_DATA_READINESS`: `READY_WITH_LIMITATIONS`
`FAMILY_E_ARCHITECTURE_RESULT`: `READY_FOR_DEVELOPMENT_BACKTEST`

Command 01 ran no final DEVELOPMENT performance, accessed no validation data, and created no Strategy V2. Family F was not started.
