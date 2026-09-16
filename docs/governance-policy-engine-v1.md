# InterSignal governance policy engine v1

## Deterministic evaluation

Policies are immutable, versioned records containing declarative rules. Each rule names a context fact, a deterministic operator, an expected value, and a failure message. The engine supports equality, inequality, membership, truthiness, falsiness, and bounded numeric comparison. It performs no AI classification, recommendation, or implicit fact inference.

An evaluation records passed checks, failed checks, warnings, the observed values, missing facts, policy version, and a canonical context hash. Missing required facts produce `INCONCLUSIVE`. Failed blocking policies produce `BLOCKED`; other material failures produce `FAIL`; warning-only failures produce `PASS_WITH_WARNINGS`.

## Initial policies

The frozen V1 policy set is:

- `NO_LIVE_WITHOUT_VALIDATED_STRATEGY`
- `NO_PAPER_WITHOUT_APPROVED_CANDIDATE`
- `NO_BROKER_CONNECTION_WITHOUT_AUTHORIZATION`
- `NO_DATA_ACQUISITION_WITHOUT_AUTHORIZATION`
- `NO_STRATEGY_PROMOTION_WITHOUT_VALIDATION`
- `NO_POST_OUTCOME_AS_PRISTINE_VALIDATION`
- `NO_PRODUCTION_WITH_OPEN_BLOCKING_VIOLATIONS`
- `NO_DESTRUCTIVE_RESEARCH_MUTATION`

All eight current-state evaluations pass because live, paper, broker, acquisition, promotion, and production remain disabled; the formal/post-outcome distinction remains explicit; and frozen research was not mutated. A pass confirms compliant disabled state. It is not authorization to activate anything.

## Research integration

Family A retains separate `FORMAL`, `INVALIDATED_ATTEMPT`, CA audit, CA remediation, and `POST_OUTCOME` entries. Formal validation remains inconclusive; post-outcome evidence is unsupportive and is never treated as pristine holdout evidence.

Family D remains `DATA_BLOCKED`, with its resume requirement preserved and no strategy-failure inference. Family F remains `SOURCE_BLOCKED`, with the licensing/authorization gate and non-approved acquisition state explicit.

## Limitations

V1 evaluates caller-supplied deterministic facts. It has no rule-expression scripting, external policy server, temporal logic, role-based identity provider, signature workflow, automatic remediation, or direct domain mutation. Later policy versions must be appended and cannot silently replace an enabled version.
