# Strategy Family B research closure V1

## Closure scope

`FAMILY_B_RESEARCH_CLOSURE_V1` implements the
`RELATIVE_ABSOLUTE_MOMENTUM_CLOSURE_V1` profile for
`STRATEGY_FAMILY_B_RELATIVE_ABSOLUTE_MOMENTUM_V1`. This is a governance-only
closure. It reads and verifies immutable artifacts from Family B Commands
01–05; it does not rerun CONTROL-B-000, MOM-B-001, MOM-B-002, or the clean
B002 reevaluation. It does not load validation data or create a new strategy.

Family B asked whether a simple absolute-momentum or trend condition adds
useful independent information to top-decile 6M relative momentum. The two
frozen definitions did not produce enough distinct filtering evidence to
justify validation or incremental parameter exploration.

## Frozen evidence

The input gate verified Family B config hash
`f98a16fcb0618a01c07242d5fe2ab3b063464d26b48c1f814200236315628076`,
success-criteria hash
`b7459cad23169a2cc2df9355e34141e852dc41648c64cc5215dfc04d62942d71`,
attribution-audit hash
`cdcef2b88766f501f6b7d21a2c1dd1cc93f79287f79c09d02dfef7f84142a0f1`,
and SMA-readiness hash
`7757839611d462b86cc09f3559e1664020a024795995744f50d6d5023ff46c5a`.
It also recomputed all frozen Command 02 result hashes and the clean Command 05
hashes:

- clean control result:
  `b0cac6bbdd31e4a2c6534fd7cc4b6eba9981693506444a20164df1246b0259ae`;
- clean B002 result:
  `48f70f4101175574968f2035afdb1534752a914889198d236cbd782bfe9dc6c2`;
- clean reevaluation:
  `a6a287f60c0a995d165279a5ddb7c666eefcb174b7a6e1c3788a5634c3834987`.

### MOM-B-001

The frozen `RELATIVE_6M_PLUS_ABSOLUTE_6M_POSITIVE_V1` rule evaluated 302
top-decile candidates. All 302 passed 6M >0, so the rule removed zero names.
Its aggregate DEVELOPMENT result remains immutable, but it supplied no distinct
filtering evidence. The final decision is:

`MOM_B_001_FINAL_STATUS = CLOSED_REDUNDANT_FILTER`

The reason is specific: strict 6M >0 was redundant inside this observed
top-decile 6M relative-momentum population.

### MOM-B-002

The original `RELATIVE_6M_PLUS_200DMA_TREND_V1` run appeared strong, but 30
candidate rows lacked SMA200 because the dataset did not contain adequate
prehistory. The attribution audit froze the findings
`B002_TREND_FILTER_EVIDENCE = CONFOUNDED_BY_HISTORY_AVAILABILITY` and
`B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION = PRIMARILY_HISTORY_AVAILABILITY`.
Those historical findings are preserved.

Command 04 extended causal daily history to 2020-01-01. SMA200 structural
coverage became 97.6821192053% and remediable coverage 99.3265993266%.
Command 05 then reevaluated the unchanged B002 rule on DEVELOPMENT. The clean
result was `SUPPORTED`, but only one of 302 candidates was a genuine
below-SMA200 exclusion. Its final evidence classifications were `WEAK` and
`EVIDENCE_TOO_SPARSE`; validation-design readiness was
`MORE_DEVELOPMENT_EVIDENCE_REQUIRED`.

Aggregate preservation is not treated as proof that the trend condition added
an incremental edge. The final B002 decision is:

`MOM_B_002_FINAL_STATUS = CLOSED_INSUFFICIENT_DISTINCT_EVIDENCE`

## Family decision and research lesson

The final family statuses are:

- `FAMILY_B_RESEARCH_STATUS = PAUSED_NO_VALIDATION_CANDIDATE`;
- `FAMILY_B_EVIDENCE_STATUS = NO_CLEAR_INCREMENTAL_EDGE_OVER_RELATIVE_MOMENTUM`;
- `FAMILY_B_VALIDATION_STATUS = NOT_ACCESSED`;
- `FAMILY_B_STRATEGY_V2_STATUS = NOT_CREATED`.

`FAMILY_B_RESEARCH_LESSON_V1` records that top-decile 6M relative momentum
strongly overlapped with the two tested simple absolute-momentum definitions in
DEVELOPMENT. B001 removed no candidates and clean B002 removed only one genuine
below-SMA200 candidate, so neither supplied sufficient independent
discrimination. This conclusion applies only to the two frozen definitions; it
must not be generalized to all absolute-momentum methods.

Family B V1 will not incrementally proceed to SMA100, SMA150, SMA250, a 50/200
crossover, positive-return buffers, a combined B001+B002 filter, or alternative
top-decile breadth. Any future reconsideration would require an independently
justified and preregistered research hypothesis rather than tuning this family.

## Data preservation and handoff

`DAILY_HISTORY_PREHISTORY_V2` is preserved as shared research infrastructure,
not disposable Family B data. Its official-source 2020+ history, causal
corporate-action layer, identity continuity, and exact-SMA readiness work can
support later independently governed families. The frozen remediation config,
raw-extension, adjusted-extension, SMA-readiness, and remediation-manifest
hashes remain unchanged.

The roadmap now marks Family A `PAUSED_PENDING_LATER_VALIDATION_DESIGN`, Family
B `PAUSED_NO_VALIDATION_CANDIDATE`, Family C `NEXT_PLANNED`, and Families D–G
`PLANNED_NOT_STARTED`.

The Family C handoff is a planning note only:

`NEXT_PLANNED_RESEARCH_FAMILY = FAMILY_C_BREAKOUT_CONTINUATION`

Its high-level concept is consolidation or compression, then breakout,
confirmation or continuation, and controlled holding. No parameters, numeric
thresholds, experiments, implementation, performance, or validation work has
been created. `RESEARCH_EXPERIMENT_GOVERNANCE_V2` remains active, so any later
Family C experiment must preregister exact numeric success criteria before
performance evaluation.

## Immutability and safety

The immutable closure manifest is stored at
`data/research/strategy_families/family_b/v1/closure/manifest/family_b_closure_manifest_v1.json`.
Its frozen `family_b_closure_hash` is
`32e510424551e01fd54aac4711fa90fa08c711856c80b812d797b3a2f8faf6b0`.

Baseline snapshots before and after closure cover Strategy V1, CAP4, Family A,
Family B Commands 01–05, every frozen Family B result hash, and
`DAILY_HISTORY_PREHISTORY_V2`. The closure produces governance records, reports,
and a planning-only handoff. It produces zero live signals, live orders, broker
calls, remote migrations, database writes, Supabase persistence, network calls,
or secrets.

Known limitations are that B001 tested only strict 6M >0; clean B002 contained
only one true below-SMA200 exclusion; seven legitimate unavailable candidate
rows remained; DEVELOPMENT evidence is not validation evidence; and the result
does not generalize beyond the two tested absolute-momentum definitions.
