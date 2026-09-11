# Strategy V1 Portfolio Backtest Foundation

STATUS: ACTIVE_MECHANICAL_BACKTEST_BASELINE

- Version/profile: PORTFOLIO_BACKTEST_V1 / SWING_PORTFOLIO_BACKTEST_V1
- Config hash: `6e98307afead0ffa`
- Trade dataset hash: `75128be670e085e3d9f2d19e89eb35722ba20631beddb448e69394e656763c4d`
- Daily dataset hash: `80746b25c0a9c4f7d2bc792f0d7a2c2552c36a37391f2fb7ae182e4b58fd9155`
- Skipped dataset hash: `4a6ab9a9cdf6032def1c28402533a71890cd141344a3f1ba80757c4220f7feca`
- Audit: `PORTFOLIO_BACKTEST_AUDIT_V1` — [structural audit](strategy-v1-portfolio-backtest-audit.md)
- Baseline decision: A FREEZE UNCHANGED
- Step 02.12 — Portfolio Backtest Foundation: COMPLETE
- Period: 2022-01-03 to 2026-08-19
- Starting/ending equity: ₹100000 / ₹86107.226785713465
- Gross return: -13.89277321428653500%
- Opportunities/entered/skipped: 3296 / 728 / 2568

## Contract

Each session begins with prior positions and opening cash. New T+1-open opportunities are ranked and admitted before any same-day high/low exit is processed, so intraday exit proceeds cannot fund entries retroactively. Positions then process stop/target events, conservative same-bar ambiguity, and session-4 close exits before end-of-day close marking.

The portfolio starts with ₹100,000, holds at most four long cash-equity positions, risks at most 1% of current opening equity per new trade and 4% in total planned open risk, and never uses leverage, margin, borrowing, pyramiding, or multiple concurrent positions in one symbol.

Ranking uses only entry-time evidence: raw score, effective R:R, setup quality, momentum, RVOL, relative strength, lower required notional, then symbol. Future outcomes, MFE/MAE, future returns, and exits never influence admission.

Target and stop prices remain frozen. TARGET_EXIT uses the target, STOP_EXIT uses the stop, NEITHER exits at session-4 close, and a same-bar stop/target touch is retained as ambiguous while conservatively filled at the stop.

## Research boundary

All figures are HISTORICAL RESEARCH / GROSS BEFORE COSTS. Transaction costs and slippage are NOT_MODELED. No parameter sweep, optimization, signal generation, live execution, broker call, migration, or Supabase write occurred.

Daily OHLC cannot recover intraday path. The ambiguity assumption, fixed four-session hold, frozen opportunity quality, and omitted execution frictions mean this active mechanical baseline is not deployable performance evidence.

## Audit review notes

The 4% cap is an admission constraint. Mark-to-market equity changes can cause passive post-admission risk-ratio drift above 4%; this does not trigger forced deleveraging and is not an admission violation.

Ranking is mechanically valid and deterministic but has EXTREME sensitivity in fixed audit counterfactuals. Selection distortion is HIGH because finite slots, capital, and risk admitted 728 of 3,296 mechanically valid opportunities. The historical gross pattern is WEAK and YEARLY_UNSTABLE; costs could materially worsen it. TARGET and TIME exits contributed positively in aggregate, while STOP exits made a large negative contribution. None of these review notes changes the frozen rules.
