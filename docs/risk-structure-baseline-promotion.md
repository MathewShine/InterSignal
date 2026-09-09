# Risk Structure Baseline Promotion

## Status

- Step 02.9 / Command 04: **COMPLETE**
- Current forward baseline: `RISK_STRUCTURE_V1_1`
- Current config hash: `f66fbdf2fc5aecd0`
- Current dataset SHA-256: `b5628df1edfe5cc62f4bccf3caf3de3a86ad55bc4f8cbcc3886acbcd459ea1cc`

## Decision

`RISK_STRUCTURE_V1_1` is the active forward baseline because Command 03 confirmed the setup-specific invalidation-priority correction while target and capital semantics remained unchanged. This promotion command changes version resolution and handoff metadata only; it does not change methodology, thresholds, stop logic, target logic, or position sizing.

`RISK_STRUCTURE_V1` is superseded for forward use but remains immutable and available for historical reproduction, comparison, and audit. Its dataset SHA-256 remains `cbd4b8bc9a6a5fe7e8080680a85c2698ad780597d28056d59c77bd4950619896`.

## Handoff

Downstream code should use `get_current_risk_structure_version()` and `resolve_current_risk_structure_dataset()` from `app.risk`. The generic build command defaults to the current baseline; historical V1 reproduction remains available through `backend/scripts/build_risk_structures.py --version v1`.

See [the V1.1 methodology delta](strategy-v1-risk-structure-v1-1.md) and [the structural audit](strategy-v1-risk-structure-audit.md) for the evidence behind the promotion.

Final strategy scoring and trade signals remain outside Step 02.9 and are still `NOT_IMPLEMENTED` and `NOT_GENERATED`. No orders, remote migrations, or Supabase persistence are part of this promotion.
