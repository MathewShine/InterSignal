# Strategy V1 Portfolio Backtest Structural Audit

STATUS: READY_FOR_REVIEW

- Audit: PORTFOLIO_BACKTEST_AUDIT_V1
- Frozen baseline: PORTFOLIO_BACKTEST_V1 / SWING_PORTFOLIO_BACKTEST_V1 / `6e98307afead0ffa`
- Scope: 3296 opportunities, 728 trades, 2568 skips
- Overall result: STABLE_WITH_REVIEW_NOTES
- Baseline decision: A FREEZE UNCHANGED

## Mechanical findings

Independent daily replay found 0 chronology violations, 0 same-day cash-reuse violations, 0 cash mismatches, and 0 EOD-equity mismatches.

All 153 same-symbol skips, 2398 slot skips, 15 cash skips, and 2 portfolio-risk skips were independently reconstructed. Quantity mismatches: 0.

The 4% planned-risk cap had 0 admission violations. Existing positions drifted above 4% on 5 later session opens (maximum 4.077204317545559768983758982%) as marked equity moved; this is a MINOR_ISSUES review note because the frozen contract enforces the cap only when admitting a trade and has no forced-deleveraging rule.

Ranking mismatches: 0; cutline violations: 0; lookahead status: RANKING_LOOKAHEAD_CLEAN. Fixed audit-only counterfactuals classify mechanical sensitivity as EXTREME; none was adopted.

## Portfolio shape and result

Ending equity is ₹86107.226785713465 and gross return is -13.89277321428653500%. Reconstructed maximum drawdown is 25.76815326209741663605033331% from 2024-03-04 to 2026-07-24; recovery: NOT_RECOVERED.

Median gross exposure is 25.33273325434943231516233209%. Selection distortion is HIGH; skipped outcomes remain descriptive only. Gross pattern: WEAK.

## Audit boundary

This command did not alter the frozen portfolio contract, optimize parameters, adopt a ranking variant, add execution costs, generate live signals, place orders, run migrations, or persist to Supabase. All performance remains HISTORICAL RESEARCH / GROSS BEFORE COSTS.

## Known limitations

- Daily OHLC cannot resolve intraday path when stop and target touch in one bar; the frozen conservative stop-first convention remains.
- Ranking counterfactuals are fixed mechanical sensitivity diagnostics and are not optimization evidence.
- Costs, slippage, taxes, fees, liquidity, and fill uncertainty are not modeled.
- Skipped-outcome comparisons are descriptive and were never consumed by selection.
- Historical gross results are not live or deployable performance evidence.

## Recommendation

Review and freeze PORTFOLIO_BACKTEST_V1 unchanged as the mechanically audited baseline; defer any ranking or strategy research to a separately versioned later command.
