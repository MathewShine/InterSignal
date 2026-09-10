# Strategy Score Baseline Promotion

STATUS: ACTIVE_FORWARD_BASELINE

- Version: STRATEGY_SCORE_V1
- Profile: SWING_DAILY_EOD_V1
- Config hash: `e257c76b90e25cb7`
- Dataset hash: `52ef4f91fd598d137e34a60d0093a6bd180342232ab1c57739ce524b497b72ed`
- Structural audit: STRATEGY_SCORE_AUDIT_V1 / STABLE_WITH_REVIEW_NOTES
- Decision: freeze the existing score unchanged; no new methodology version was created.

## Scope

The swing daily-EOD score is the current forward research baseline. Future consumers must resolve it through the central profile-aware baseline contract.

Sector and catalyst evidence remain unavailable historically. They contribute zero points and zero available weight, leaving typical coverage at 85%. Raw score remains the eligibility basis; normalized score remains diagnostic only.

No outcomes, backtest, signal generation, execution, broker action, migration, or Supabase persistence occurred during promotion.
