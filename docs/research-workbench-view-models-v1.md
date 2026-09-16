# Research Workbench View Models V1

## Family and strategy views

`ResearchFamilySummary` powers the future family matrix with lifecycle,
validation, evidence counts, blocking state, activity time, and production
candidate status. `ResearchFamilyDetail` adds strategies, evidence, timeline,
artifacts, validation, limitations, conclusion, and lineage references.

`ResearchStrategyDetail` keeps the immutable strategy record and append-only
lifecycle history together with configuration hashes, evidence grouped by all
six classifications, artifacts, lineage summaries, limitations, and the
current conclusion.

## Evidence and validation

`EvidenceSummary` maintains separate counters for positive, negative, blocked,
formal validation, post-outcome, and data-infrastructure evidence.
`ResearchEvidenceDetail` retains strategy, artifact, and lineage links plus the
effective period, confidence, limitations, and source metadata.

Family A deliberately has two distinct validation projections:

- formal one-shot validation: `INCONCLUSIVE`;
- corrected post-outcome generalization evidence: `UNSUPPORTIVE` and not a
  pristine holdout.

The latter does not rewrite the formal result. Current advancement is
`CLOSED_NOT_ADVANCED`, with advancement disallowed for this cycle.

## Blocked research

`BlockedResearchSummary` distinguishes research feasibility from strategy
performance:

- Family D is `DATA_BLOCKED` because intraday continuity is below the frozen
  threshold.
- Family F is `SOURCE_BLOCKED` because an authorized historical catalyst
  source is unavailable.

Neither block is represented as a strategy failure. Resume requirements and
supporting evidence/artifact identifiers remain explicit.

## Conclusions

The current family conclusions are:

| Family | Conclusion |
| --- | --- |
| A | `CLOSED_NOT_ADVANCED` |
| B | `NO_INCREMENTAL_EDGE` |
| C | `REUSABLE_SIGNAL_ONLY` |
| D | `DATA_BLOCKED` |
| E | `NEGATIVE_DEVELOPMENT` |
| F | `SOURCE_BLOCKED` |
| G | `NEGATIVE_OVERLAY` |

Every conclusion includes its evidence basis, limitations, advancement flag,
and metadata. Family A also preserves the historical
`STRONG_DEVELOPMENT_NOT_GENERALIZED` characterization.

## Filtering, sorting, and pagination

Family queries support filters for conclusion/status, lifecycle, evidence
classification, evidence level, blocked state, validation state, and inclusive
activity-date range. Stable sort fields are family code, name, latest activity,
and status.

`ResearchFamilyQuery` and `ResearchFamilyPage` provide deterministic `limit`,
`offset`, and `total_count` pagination. Limits are bounded to 1-500 and offsets
must be non-negative.

## Timeline, artifacts, and lineage

Timeline projections come only from append-only `RegistryEvent` records and
sort by timestamp plus event ID. Artifact views expose immutable metadata and
references. Lineage traces return sorted nodes and edges, upstream/downstream
counts, roots, terminal evidence, relationship paths, and integrity status.

## Programme projection

The current programme summary remains: strategy research `PAUSED`, A-G
`COMPLETE_NO_VALIDATED_STRATEGY`, zero validated strategies, zero production
candidates, Strategy V2 `NOT_CREATED`, Family H `NOT_PLANNED`, paper and live
`NOT_READY`, primary `PRODUCT_PLATFORM_PROGRAM`, and secondary
`FORWARD_DATA_PROGRAM`.
