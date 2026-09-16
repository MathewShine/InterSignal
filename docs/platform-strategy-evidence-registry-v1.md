# Platform Strategy and Evidence Registry V1

This foundation provides provider-neutral, append-only Strategy and Evidence registries for later use by the Research Workbench, Portfolio OS, Risk, Governance UI, Shadow Observation, and Data Observability. It does not authorize any strategy, run research, or start paper/live trading.

## Strategy record

`StrategyRecord` contains strategy ID, family, name, version, description, lifecycle state, configuration/preregistration/implementation hashes, creation and update timestamps, promotion permission, validation state, production state, and metadata.

The exact lifecycle enum is:

1. `IDEA`
2. `PREREGISTERED`
3. `DEVELOPMENT_EVALUATED`
4. `VALIDATION_CANDIDATE`
5. `VALIDATION_EVALUATED`
6. `PAUSED`
7. `REJECTED`
8. `DATA_BLOCKED`
9. `SOURCE_BLOCKED`
10. `PRODUCTION_CANDIDATE`

Transitions are explicitly validated. The main forward path is IDEA → PREREGISTERED → DEVELOPMENT_EVALUATED → VALIDATION_CANDIDATE → VALIDATION_EVALUATED → PRODUCTION_CANDIDATE. Any state may be paused. Relevant states may become rejected, data-blocked, or source-blocked. IDEA cannot jump directly to PRODUCTION_CANDIDATE. A production-candidate transition additionally requires explicit promotion permission and `VALIDATED` status.

Material lifecycle changes append a new immutable StrategyRecord version and a RegistryEvent. They never overwrite earlier history.

## Evidence record

`EvidenceRecord` contains evidence ID, title, description, classification, level, status, strategy reference, source artifact references, lineage references, creation time, effective period, optional confidence, limitations, and metadata.

Exact classifications are:

- `POSITIVE_EVIDENCE`
- `NEGATIVE_EVIDENCE`
- `BLOCKED_RESEARCH`
- `VALIDATION_EVIDENCE`
- `POST_OUTCOME_EVIDENCE`
- `DATA_INFRASTRUCTURE_EVIDENCE`

Exact levels are `STRATEGY_LEVEL`, `SIGNAL_LEVEL`, `DATA_INFRASTRUCTURE_LEVEL`, `IMPLEMENTATION_LEVEL`, and `GOVERNANCE_LEVEL`. Stable statuses are `ACTIVE`, `HISTORICAL`, `SUPERSEDED`, `RESEARCH_ONLY`, `NOT_VALIDATED`, and `BLOCKED`. None implies production authorization.

Evidence registration is rejected unless its strategy, artifacts, and lineage nodes already exist. Duplicate evidence IDs are rejected. There is no destructive delete method.

## Formal versus post-outcome evidence

Family A's records deliberately remain separate:

- `EVIDENCE-A-FORMAL-VALIDATION-001` is `VALIDATION_EVIDENCE`, retains formal status `INCONCLUSIVE`, and remains tied to the immutable one-shot validation result.
- `EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001` is `POST_OUTCOME_EVIDENCE`, records an `UNSUPPORTIVE` indication, and is explicitly not pristine holdout evidence or a replacement for the formal result.

This distinction prevents corrected post-outcome information from rewriting the historical validation decision.

## A–G seed mapping

| Family | Seed lifecycle | Preserved evidence |
|---|---|---|
| A | `REJECTED` | Historical development strength; formal `INCONCLUSIVE`; post-outcome `UNSUPPORTIVE` |
| B | `REJECTED` | No clear incremental edge |
| C | `PAUSED` | `EVIDENCE-C-COMPRESSION-001` and canonical `EDGE-EVIDENCE-C-COMPRESSION-001`, signal-level research only |
| D | `DATA_BLOCKED` | Intraday continuity below the frozen readiness threshold; not performance-evaluated |
| E | `REJECTED` | Negative pullback/reclaim development evidence |
| F | `SOURCE_BLOCKED` | Source/licensing blocker plus NSE timestamp/linkage feasibility evidence |
| G | `REJECTED` | `EDGE-NEGATIVE-G-SMA200-GATE-001` |

The mapping retains each source governance status in metadata. It creates no Strategy V2, Family H, validation candidate, or production candidate.

## Audit events

Every service-layer mutation appends a `RegistryEvent` containing deterministic event ID, entity type and ID, event type, previous and new state, actor, reason, timezone-aware timestamp, related artifact IDs, and metadata. Registration and lifecycle transitions are therefore independently inspectable.

Current seed counts and states are sealed in `data/platform/registry/current_research_snapshot_v1.json`. Both `production_candidate_count` and `validated_production_strategy_count` are zero.
