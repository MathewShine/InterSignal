# Strategy V1 Historical Outcomes Structural Audit

Current phase: Step 02.11 / Command 02

## Boundary

- STRATEGY_OUTCOME_AUDIT_V1 is diagnostic only and does not mutate STRATEGY_OUTCOME_V1.
- The audit uses future prices only inside the outcome/audit boundary.
- No score, stop, target, threshold, weight, entry rule, holding horizon, or exit methodology was changed.
- No backtest, trade P&L, signal, broker action, order, migration, or Supabase write was introduced.

## Frozen Baseline

- Outcome: STRATEGY_OUTCOME_V1 / SWING_DAILY_OUTCOME_V1 / 2ea683a8f8b5b041
- Outcome dataset SHA-256: 5c4ec28cb54f6567b04c3444a3f1d0dde5f03ac3c6518743268f9e4fda100538
- Score dataset SHA-256: 52ef4f91fd598d137e34a60d0093a6bd180342232ab1c57739ce524b497b72ed
- Risk V1.1 dataset SHA-256: b5628df1edfe5cc62f4bccf3caf3de3a86ad55bc4f8cbcc3886acbcd459ea1cc

## Population

- Total outcome rows: 14251
- Primary eligible rows: 4268
- Valid primary next-open entries: 3296
- Forward-data-unsafe primary rows: 700
- Entry-session unsafe: 700
- Later-window-only unsafe: 0

## Audit Classifications

- Forward safety: CONSERVATIVE_BUT_REASONABLE
- Entry revalidation: CLEAN_AND_USEFUL
- Outcome labels: CLEAN
- Four-session horizon: LIKELY_TOO_SHORT
- Descriptive pattern: WEAK
- Overall: STABLE_WITH_REVIEW_NOTES
- Baseline decision: A_FREEZE_UNCHANGED

## Interpretation Guardrails

- Target-first and stop-first are neutral path labels, not canonical win/loss labels.
- Intermediate R-level and extended-horizon results are diagnostics, not proposed exits or hold rules.
- Counterfactual below-threshold, exceptional-review, preview, and primary cohorts remain separate.
- Transaction costs and slippage remain NOT_MODELED.
