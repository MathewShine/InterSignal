# STRATEGY_SCORE_V1 Structural Audit

- Audit version: STRATEGY_SCORE_AUDIT_V1
- Baseline: STRATEGY_SCORE_V1 / SWING_DAILY_EOD_V1 / `e257c76b90e25cb7`
- Dataset SHA-256: `52ef4f91fd598d137e34a60d0093a6bd180342232ab1c57739ce524b497b72ed`
- Active risk input: RISK_STRUCTURE_V1_1 / `f66fbdf2fc5aecd0`
- Scope: structural score behavior only; no outcomes, optimization, backtest, signals, or execution.

## Integrity

- Rows: 26130
- Arithmetic / cap / raw-bound violations: 0 / 0 / 0
- Available-weight / coverage / normalized-formula mismatches: 0 / 0 / 0
- Normalized-score isolation: NORMALIZED_DIAGNOSTIC_ISOLATED

## Gates And Coverage

- FULL / preview / exceptional / not eligible: 10791 / 3136 / 324 / 11879
- Raw >=80 / ordinary eligible / blocked difference: 4534 / 4268 / 266
- Exact blocked decomposition: {'RISK_REJECTION:RR_BELOW_MINIMUM': 266}
- Coverage frequencies: {'70': 105, '75': 28, '80': 11, '85': 25986}
- Insufficient-coverage causes: {'RS_UNAVAILABLE': 37}

## Structural Findings

- Missing components: CLEAN_MISSING_EVIDENCE_POLICY
- Gate/score separation: CLEAN_GATE_FIRST
- Component redundancy: MODERATE_OVERLAP_ACCEPTABLE
- Threshold structure: SELECTIVE_AND_COHERENT
- Score resolution: ADEQUATE_RESOLUTION
- Neutral ceiling: COHERENT_BUT_STRICT

## Decision

- Overall: STABLE_WITH_REVIEW_NOTES
- Baseline decision: A_FREEZE_UNCHANGED
- Review note: setup quality is a composite upstream judgment, so its overlap with dedicated momentum, RVOL, and RS components should remain visible in future outcome-based validation.
- STRATEGY_SCORE_V1 was not modified by this audit.

## Safety

- ZERO signals, orders, remote migrations, and Supabase persistence.
- Sector and catalyst remain unavailable; no historical values were inferred or back-projected.
- Normalized available score remains diagnostic only.
