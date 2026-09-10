# Strategy V1 Final Scoring

Step 02.10 - Strategy V1 Final Scoring Foundation

STATUS: ACTIVE_FORWARD_BASELINE

## Boundary

- The score ranks available evidence; it is not a predicted probability, trade signal, or order instruction.
- Mandatory candidate, setup, regime, entry, and risk gates run before score. A numerical score cannot rescue a failed gate.
- No outcome labels, future data, backtest, profitability optimization, paper trade, broker action, migration, or Supabase write is used.

## Version

- Score: STRATEGY_SCORE_V1 / e257c76b90e25cb7
- Profile: SWING_DAILY_EOD_V1
- Dataset SHA-256: `52ef4f91fd598d137e34a60d0093a6bd180342232ab1c57739ce524b497b72ed`
- Active risk input: RISK_STRUCTURE_V1_1 / f66fbdf2fc5aecd0

## Weights

- Setup 20; multi-day momentum 20; relative volume 15; benchmark relative strength 15.
- Market regime 10; sector 10; catalyst/news 5; reward:risk 5.
- Sector and catalyst are unavailable historically and contribute zero points and zero available weight.

## Component Mappings

- Setup quality: STRONG 20, VALID 16, WATCH 8, POOR 0.
- Multi-day momentum: candidate V1 5d, 10d, 20d, up-day-ratio-10, and up-day-ratio-20 thresholds contribute up to 4 points each; return_1d is excluded.
- Relative volume: EXCEPTIONAL 15, STRONG 13, GOOD 10, NORMAL 6, WEAK 0.
- Benchmark relative strength: STRONG 15, POSITIVE 11, NEUTRAL 6, WEAK 0.
- Regime: BULLISH 10, NEUTRAL 5, BEARISH 0; UNAVAILABLE contributes zero and removes 10 points from available weight.
- Sector: UNAVAILABLE / 0 because point-in-time stock-to-sector mapping does not exist.
- Catalyst/news: UNAVAILABLE / 0 because no historical point-in-time catalyst layer exists.
- Reward:risk: below 1.5R 0, 1.5R to below 2R 3, 2R to below 2.5R 4, at least 2.5R 5.

## Score Semantics

- Raw score is the unscaled sum on the locked 0-100 scale.
- Available weight counts only AVAILABLE components; historical coverage is normally 85%.
- Normalized available score is DIAGNOSTIC_ONLY and never controls bands or eligibility.
- Minimum coverage: 80%; entry threshold: 80; high-conviction threshold: 90.
- Preview rows remain PREVIEW_ONLY. Bearish exceptional longs remain EXCEPTIONAL_REVIEW.
- Penalties remain separate and retain their upstream severity and blocking status.

## Current Reachability

- Bullish theoretical maximum: 85; Neutral: 80; Bearish: 75.
- HIGH_CONVICTION_NOT_REACHABLE_WITH_CURRENT_HISTORICAL_COMPONENT_COVERAGE.

## Generation

- Full generation completed: True
- Rows: 26130; full / preview / exceptional / not eligible: 10791 / 3136 / 324 / 11879
- Entry eligible: 4268; high conviction: 0; exceptional review: 324
- Raw score min / median / mean / max: 26 / 67 / 66.737504783773 / 85
- Coverage at 85% / below / above: 25986 / 144 / 0

## Future Integration

- Add sector points only after point-in-time stock-to-sector history exists.
- Add catalyst points only through a separately approved point-in-time news research layer.
- Intraday scoring remains a separate future INTRADAY_SCORE_V1 profile.

## Audit Review Notes

- [STRATEGY_SCORE_AUDIT_V1](strategy-v1-final-scoring-audit.md) concluded `STABLE_WITH_REVIEW_NOTES` and recommended freezing STRATEGY_SCORE_V1 unchanged.
- Setup quality partially overlaps other evidence, but no high double-counting defect was found.
- Momentum/RS overlap is moderate and acceptable: FULL_SCORE Pearson 0.3838 and Spearman 0.3390.
- Neutral score 80 is ceiling-dependent and intentionally strict; threshold 80 remains structurally selective.
- Missing sector and catalyst evidence materially limits current score headroom.

## Status

- Step 02.10: COMPLETE.
- Forward scoring baseline: STRATEGY_SCORE_V1.
- Forward scoring profile: SWING_DAILY_EOD_V1.
