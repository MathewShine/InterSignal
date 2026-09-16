# Family A corporate-action lookback remediation V1

## Scope

`FAMILY_A_CA_LOOKBACK_REMEDIATION_V1` implements one code-only correction under profile `VALIDATION_PREHISTORY_SEMANTICS_FIX_V1`. It separates causal feature and eligibility history from the formal validation performance window. It does not rerun validation, calculate validation performance, generate holdings, change Family A, change corporate-action rules, change validation criteria, authorize replacement validation, or create Strategy V2.

The remediation began from checkpoint `f41801acf01b69fa55353ebb07ae01ae86fc02b0`. The sealed formal validation remains `INCONCLUSIVE`, Family A generalization remains `INCONCLUSIVE`, Strategy V2 advancement remains `NO_DECISION`, lifecycle remains `EVALUATED`, completed valid formal runs remain `1 / 1`, and remaining runs remain zero.

## Original defect

Validation previously filtered exchange sessions to `2025-01-01…2026-08-13` before constructing frozen six-month history. The `2024-12-31` formation was absent from that truncated calendar, while `2025-03-28` and `2025-06-30` had fewer than 126 prior retained sessions. The signal-boundary calculator returned no start date, and the unchanged `_corporate_action_safe` fail-closed branch returned `NO_LOOKBACK_START` for all 500 members.

This was a global implementation defect, not 500 independent security failures. The frozen root-cause audit classified it as:

- `FAMILY_A_CA_VALIDATION_ROOT_CAUSE = IMPLEMENTATION_LOGIC_DEFECT`
- `CA_VALIDATION_DEFECT_SEVERITY = FATAL_TO_VALIDATION_INTEGRITY`
- `CA_ROOT_CAUSE_FIXABILITY = CODE_FIX_ONLY`

The root-cause audit manifest remains `a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793`.

## Why source data was not the problem

The existing raw, normalized, adjustment-factor, adjusted-price, and eligibility artifacts already cover the affected validation dates. This command does not ingest, extend, or rebuild corporate-action data. It continues to use `PRICE_ADJUSTED_STRUCTURAL_V1` and `CORPORATE_ACTION_EXCLUSIONS_V1` exactly as frozen.

The corporate-action rule source hash remains `1976c9e98ab5ec3a5a2d2b05dcbe51a40180d6745f5c7ec7c8755a9eb6ac9901`. The `_corporate_action_safe` function hash remains `bd971c109b8e488c719b8ed8d491c50c3dfcb954620b2b30d5fabc115d6ebcab`.

## Corrected boundary separation

`prepare_validation_session_windows` now creates two explicit calendars:

1. Causal history sessions: `2021-09-07…2026-08-13`. These may support frozen feature history, CA eligibility, and causal identity context.
2. Performance sessions: exactly `2025-01-01…2026-08-13`. These remain the only sessions supplied to portfolio simulation.

The schedule/eligibility preparation path receives causal history. The performance engine receives only performance-window sessions. Assertions reject a causal calendar that lacks prehistory, a performance calendar outside the sealed bounds, or any formation without the frozen 126-session history. No date-specific special case was added.

The earliest session required for the earliest formation is `2024-06-28`, exactly 126 valid NSE market sessions before `2024-12-31`. No calendar-day approximation is used. No post-holdout session is loaded.

## Deterministic before/after fixture

| State | Formation | Calendar start | Lookback start | Count | CA result |
|---|---:|---:|---:|---:|---|
| Before: validation-truncated | 2024-12-31 | 2025-01-01 | none | 0 | unsafe: `NO_LOOKBACK_START` |
| After: full causal history | 2024-12-31 | 2021-09-07 | 2024-06-28 | 126 | normal eligibility evaluation |

The fixture calculates no signal rank, portfolio weight, holding, return, or performance metric.

## Structural validation formations

| Formation | Members | Lookback start | Sessions | CA eligible | CA excluded | NO_LOOKBACK_START | Structurally selectable |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-12-31 | 500 | 2024-06-28 | 126 | 487 | 13 | 0 | 339 |
| 2025-03-28 | 500 | 2024-09-26 | 126 | 493 | 7 | 0 | 338 |
| 2025-06-30 | 500 | 2024-12-26 | 126 | 486 | 14 | 0 | 356 |
| 2025-09-30 | 500 | 2025-03-27 | 126 | 481 | 19 | 0 | 340 |
| 2025-12-31 | 500 | 2025-06-30 | 126 | 485 | 15 | 0 | 326 |
| 2026-03-30 | 500 | 2025-09-24 | 126 | 494 | 6 | 0 | 349 |
| 2026-06-30 | 500 | 2025-12-22 | 126 | 492 | 8 | 0 | 366 |

The `2025-09-30` exclusions remain exactly 14 special-dividend, two rights, and three complex-restructuring exclusions. `POST_REMEDIATION_CA_FAILURE_SCOPE = NORMAL_SYMBOL_LEVEL_ELIGIBILITY`.

“Structurally selectable” means the frozen price, liquidity, CA, adjusted-endpoint-history, and next-open availability gates are present. It does not rank momentum, select a top decile, generate holdings, or calculate results.

## Development regression

Representative development behavior is unchanged:

| Formation | CA eligible | Structurally selectable | Lookback start | Regression |
|---|---:|---:|---:|---|
| 2023-03-31 | 489 | 213 | 2022-09-28 | unchanged |
| 2024-03-28 | 490 | 325 | 2023-09-26 | unchanged |
| 2024-09-30 | 483 | 344 | 2024-03-27 | unchanged |

## Semantic scope guard

Every changed functional block is classified as one of `CA_PREHISTORY_BOUNDARY_FIX`, `ASSERTION`, `TEST`, `REPORTING`, or `DOCUMENTATION`. No block is classified as `STRATEGY_CHANGE`, `PERFORMANCE_CHANGE`, `CRITERIA_CHANGE`, or `RESULT_CHANGE`.

The frozen functions for schedule construction, simulation, metric calculation, and criteria evaluation retain their pre-remediation source hashes. The candidate identity, family configuration, validation design, validation criteria, CA rules, alias policy, ranking, weighting, cost model, rebalance schedule, and result classifier are unchanged.

## Formal result immutability

The formal validation manifest remains canonically verified at `e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8`. The result remains canonically verified at `be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9`. Their file SHA-256 values were captured before and after structural verification and are byte-identical.

No evaluation artifact was overwritten. No validation execution function was called.

## Remediation result and governance

- `FAMILY_A_CA_REMEDIATION_RESULT = FIX_VERIFIED_STRUCTURALLY`
- `POST_OUTCOME_REMEDIATED_VALIDATION_TECHNICAL_READINESS = YES`
- `REPLACEMENT_VALIDATION_GOVERNANCE_STATUS = NOT_AUTHORIZED`

Technical readiness means the proven implementation defect is structurally corrected and required invariants pass. It is not authorization to run validation. A future run requires a separate explicit governance decision.

Any future validation performed after this remediation is `POST_OUTCOME_REMEDIATED_VALIDATION` because prior validation outcomes are known. It cannot be treated as pristine holdout evidence. This disclosure is permanent.

## Hashes and artifacts

- configuration: `eea54556b182cd328229b6b79781698d6abb09dd8c0ab2358074ab6ba0be246a`
- calendar fix: `e982cc223ad337b72c2e168d301ea6cf987be17a555bd21ef71d3cb7842800f0`
- structural eligibility: `4a76e7a52156f413d1f2bcf14fec0dd8ec3ea9799f1f95d4609a71b14e789a3b`
- development regression: `113bdd0d0f121b379e18e901a445ab0a18ad96f26e98e1e8a1b35d788273a2e9`
- scope guard: `94de2801d6a52bcfabe1018ff802f1448ed8a4b9cad2b3a82f93aae5fa30d757`
- technical readiness: `4d00dbdd5fca58452a3b419d52e262c3b2407968b2e69806608b6f9b642dd65f`
- immutable manifest: `ecdacd4dc4c348fe9002928fe37f78381e8833d2c5fb3cfa611e62237161db00`

Canonical artifacts are stored under `data/research/validation/family_a/v1/ca_remediation/`, with report copies under `data/reports/`. The command produced zero live signals, orders, broker calls, migrations, Supabase writes, credentials, or external writes.

## Next action

Stop after review. If desired, a separate governance command may consider whether to authorize a permanently labeled post-outcome remediated validation. This remediation itself grants no such authorization.
