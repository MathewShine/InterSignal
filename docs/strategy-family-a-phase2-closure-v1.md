# Family A Phase 2 Closure V1

## Family A journey and frozen evidence

Family A began as `STRATEGY_FAMILY_A_MOMENTUM_V1`, a controlled DEVELOPMENT-only study of medium-term cross-sectional momentum. Command 01 preregistered three independent baselines without selecting a winner: MOM-A-001 (6M/monthly), MOM-A-002 (6M/quarterly), and MOM-A-003 (12-1/monthly). Command 02 evaluated all three and classified the family `PROMISING_FAMILY`. Their identities, parameter hashes, preregistration hashes, and result hashes remain frozen.

MOM-A-002 remains the primary architecture reference because it was Phase 2 eligible, turned over less than MOM-A-001, had positive DEVELOPMENT behavior, used a simple quarterly schedule, and subsequently produced clear capital-feasibility evidence. “Primary reference” does not mean best, winner, or optimal.

## Phase 2 rationale and closure decisions

Phase 2 isolated two implementation questions using the frozen 6M/quarterly reference. A2-001 tested a top-10% entry/top-15% retention band at ₹100,000. A2-002 changed only starting capital from ₹100,000 to ₹500,000.

A2-001 reduced annualized turnover by approximately 10.55% and modeled costs by approximately 7.25%, while increasing retention. Net return declined by approximately 5.02 percentage points, producing `MINOR_IMPROVEMENT`, `MODEST_DEGRADATION`, and `PARTIALLY_SUPPORTED`. The branch is now `CLOSED_NOT_ADVANCED`. Its 10/15 threshold will not be retuned, and no alternate retention threshold will be tried within the current Family A version. Retention remains conceptually possible, but is `DEPRIORITIZED_FOR_CURRENT_FAMILY_A_VERSION`; any revisit requires a genuinely new hypothesis, experiment ID, preregistration, and non-trivial conceptual justification.

A2-002 reduced average cash from approximately 13.12% to 2.65%, maximum cash from approximately 21.80% to 4.82%, unaffordable instances from 17 to zero, and both mean absolute and L1 weight error materially. It is retained as `SUPPORTED_IMPLEMENTATION_EVIDENCE`.

## Capital references

₹500,000 is frozen as `FAMILY_A_PRACTICAL_RESEARCH_CAPITAL_REFERENCE_V1` for broad 20–35-holding Family A research portfolios using whole-share execution. It is an implementation-fidelity reference—not a profitability threshold, alpha parameter, live-capital recommendation, or proof that larger capital always performs better. ₹100,000 remains the `SMALL_CAPITAL_REFERENCE` and all prior ₹100k results remain preserved.

## Family status and validation

Family A is `PAUSED_PENDING_LATER_VALIDATION_DESIGN` with `PROMISING_DEVELOPMENT_EVIDENCE_NOT_VALIDATED`. Validation is `NOT_ACCESSED`: no authorization, holdout run, or 2025+ performance access occurred. Strategy V2 is `NOT_CREATED`.

Family A may resume only for a formal validation design, a genuinely new hypothesis, or integration into a multi-strategy architecture—not incremental threshold tuning.

## Governance improvement

`GOVERNANCE_FINDING_NUMERIC_THRESHOLDS_V1` records that Command 03 froze qualitative labels but not exact numerical classification cutoffs before Command 04 evaluated performance. The Command 04 labels therefore remain descriptive rather than preregistered; immutable raw metrics take precedence.

`RESEARCH_EXPERIMENT_GOVERNANCE_V2` applies prospectively and does not rewrite historical records. Future controlled experiments must freeze exact numerical success/failure thresholds before performance evaluation whenever feasible. If thresholds are not frozen, post-hoc classifications must be explicitly labeled descriptive. The required checklist covers hypothesis, experiment ID, population, exact parameters, control, primary and secondary metrics, numerical success criteria, failure criteria, stop conditions, validation eligibility, cost model, data partition, and hashes.

## Family B planning handoff

`FAMILY_B_RELATIVE_PLUS_ABSOLUTE_MOMENTUM` is `NEXT_PLANNED`. Its high-level concept is to test whether strong cross-sectional momentum plus positive absolute momentum or trend improves robustness versus relative momentum alone. No parameters, experiments, code, or backtest are created by this closure command. Family B requires a separate future authorization.
