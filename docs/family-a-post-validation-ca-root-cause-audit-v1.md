# Family A post-validation corporate-action root-cause audit V1

## Scope and immutable governance state

This document records `FAMILY_A_POST_VALIDATION_CA_ELIGIBILITY_AUDIT_V1` under profile `CORPORATE_ACTION_ELIGIBILITY_ROOT_CAUSE_V1`. It is a lineage, identity, date-boundary, and code-path audit only. It neither reruns nor replaces `FAMILY_A_ONE_SHOT_VALIDATION_V1`.

The sealed formal record remains:

- validation result: `INCONCLUSIVE`
- Family A generalization result: `INCONCLUSIVE`
- Strategy V2 advancement: `NO_DECISION`
- completed valid formal runs: `1 / 1`
- remaining formal runs: `0`
- formal validation manifest hash: `e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8`
- formal validation result hash: `be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9`

No validation return, ending equity, CAGR, drawdown, or positive/negative interval result was used to classify this defect.

## Finding

`FAMILY_A_CA_VALIDATION_ROOT_CAUSE = IMPLEMENTATION_LOGIC_DEFECT`.

The first three validation formations failed because validation orchestration removed all sessions before `2025-01-01` before asking the six-month momentum calculator for its 126-session start date. The `2024-12-31` formation was not in that truncated session set; `2025-03-28` and `2025-06-30` did not yet have 126 retained prior sessions. In all three cases the signal calculator returned no lookback start. The strategy-facing corporate-action safety helper treats a missing start as unsafe and returns `NO_LOOKBACK_START`. One global calendar-boundary error therefore propagated to every member; it was not 500 independent corporate-action failures.

The corporate-action source and derived datasets cover the affected dates. Identity resolution also succeeds for all 500 members on every audited validation formation. The failure is consequently not a source gap, derived-layer gap, dataset-end boundary, or identity-mapping defect.

Classification:

- `CA_FAILURE_SCOPE = GLOBAL_INFRASTRUCTURE_FAILURE`
- `CA_VALIDATION_DEFECT_SEVERITY = FATAL_TO_VALIDATION_INTEGRITY`
- `CA_ROOT_CAUSE_FIXABILITY = CODE_FIX_ONLY`
- missing-data policy: `PARTIAL`
- development/validation consistency: `POLICY_INCONSISTENCY`
- `REPLACEMENT_VALIDATION_GOVERNANCE_STATUS = NOT_AUTHORIZED`

The severity is fatal to validation integrity because the global boundary defect forced the first three scheduled primary formations to retain no newly selected portfolio. It does not change the already sealed result; `INCONCLUSIVE` remains the formal result.

## Eligibility funnel and exact first-three issue

The counts below are diagnostic gates, not performance results. Price, liquidity, and CA counts are independent gate counts; the final candidate count requires every frozen gate.

| Period | Formation | PTIT members | Identity resolved | Price eligible | Liquidity eligible | CA eligible | Final candidates | Genuine CA exclusions with full history |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Validation | 2024-12-31 | 500 | 500 | 468 | 0 | 0 | 0 | 13 |
| Validation | 2025-03-28 | 500 | 500 | 459 | 479 | 0 | 0 | 7 |
| Validation | 2025-06-30 | 500 | 500 | 469 | 476 | 0 | 0 | 14 |
| Validation | 2025-09-30 | 500 | 500 | 469 | 458 | 481 | 340 | 19 |

For the first three rows, all 500 observed CA exclusions have exact reason `NO_LOOKBACK_START`, classified as `OTHER` in the required exclusion taxonomy. This reason is intentionally not relabeled as a corporate-action event. The per-security audit also records whether each name would have encountered a genuine finite CA blocker under the available full-history calendar, preserving the distinction between the global defect and ordinary symbol-level exclusions.

At `2025-09-30`, the truncated validation calendar had accumulated 126 prior sessions. Its computed start was `2025-03-27`; the global boundary condition therefore disappeared without any change to source data, derived artifacts, version, identity mapping, or CA rule. The remaining 19 ordinary CA exclusions were 14 special-dividend, two rights, and three complex-restructuring exclusions. This is the exact recovery mechanism.

## Corporate-action lineage and coverage

| Layer | Version | Earliest | Latest | Rows | SHA-256 |
|---|---|---:|---:|---:|---|
| Raw official CA records | `official_nse_corporate_actions` | 2021-09-07 | 2026-09-07 | 12,257 | `bac82fff5263703e857e2426d3c3e2c88f1d2dedcc6d903577a4c93df758f46a` |
| Normalized CA records | `NORMALIZED_CA_EVENTS_V1` | 2021-09-07 | 2026-09-07 | 12,257 | `4b4184f579bdf3c724d594b0c1e94410e40cc077a44871fdeb65cf0eaa45e1e5` |
| Price-adjustment factors | `PRICE_ADJUSTED_STRUCTURAL_V1` | 2021-09-08 | 2026-09-04 | 522 | `b5682cc151bc6e1c41f86821d1b66caeb7ad84c4942c3375ac88243d2076ab5c` |
| Research eligibility | `CORPORATE_ACTION_EXCLUSIONS_V1` | 2021-09-24 | 2026-09-27 | 890 | `da1b1f3470b8199d62f4b3636fd93afd86185eb20bf229c75a94cd181c2d4e03` |

The adjusted daily dataset contains 1,240 partitions and 3,246,754 records from `2021-09-07` through `2026-09-07`, using `PRICE_ADJUSTED_STRUCTURAL_V1`. Therefore:

- source-data check: `RAW_DATA_PRESENT`
- derived-layer check: `SOURCE_PRESENT_DERIVED_PRESENT`
- `SOURCE_PRESENT_DERIVED_MISSING` does not apply
- no artifact ends at `2024-12-31` or another pre-validation cutoff
- no “date beyond latest known CA date” coverage check caused the failure

## Identity audit

Identity resolution was complete on all four audited validation dates:

| Formation | Exact ISIN | Symbol-date | Alias | Unresolved |
|---|---:|---:|---:|---:|
| 2024-12-31 | 427 | 73 | 0 | 0 |
| 2025-03-28 | 453 | 47 | 0 | 0 |
| 2025-06-30 | 453 | 47 | 0 | 0 |
| 2025-09-30 | 466 | 34 | 0 | 0 |

The strategy path uses alias-normalized symbols for CA exclusion lookup. The membership and eligibility records resolve every audited name. There is no evidence that 2025 ISIN or symbol changes caused the all-member failure.

## Development versus validation

Representative development funnels show ordinary finite CA exclusion behavior:

| Formation | PTIT members | CA eligible | Final candidates | Full-history lookback start |
|---|---:|---:|---:|---:|
| 2023-03-31 | 499 | 489 | 213 | 2022-09-28 |
| 2024-03-28 | 499 | 490 | 325 | 2023-09-26 |
| 2024-09-30 | 500 | 483 | 344 | 2024-03-27 |

Development and validation use the same `_corporate_action_exclusions` and `_corporate_action_safe` helpers, the same `CORPORATE_ACTION_EXCLUSIONS_V1` configuration, the same structural-adjustment semantics, and the same alias-normalized identity lookup. Their orchestration differs: development preserves sessions from `2021-09-07` before forming its 2022–2024 schedules, while validation filters the calendar to its portfolio window before signal construction. Thus the helper-level rule is unchanged but the effective missing-history policy differs at the caller boundary. This is `POLICY_INCONSISTENCY`.

Frozen relevant source hashes are:

- Family A momentum: `1976c9e98ab5ec3a5a2d2b05dcbe51a40180d6745f5c7ec7c8755a9eb6ac9901`
- Family A one-shot validation: `ef3a7ac4b9c143a3c6f3690565866743d54fa5555708778a50a7001ab38f709a`
- final CA readiness service: `7201dbab612ba997ad2a00bf16958e653f94fd3475341654a938f22cb106e3e0`

## Code path and missing-data behavior

The exact chain is:

1. `execute_one_shot_validation` filters calendar sessions to `VALIDATION_START <= session <= VALIDATION_END` before calling schedule construction.
2. `build_validation_schedules` calls `compounded_return` for every formation/member using that truncated calendar.
3. `compounded_return` returns no start date when the formation is absent or fewer than 126 prior sessions exist.
4. `_corporate_action_safe` receives that null start date and returns `(False, ("NO_LOOKBACK_START",))`.
5. The candidate row therefore fails the CA safety gate, alongside any other gate that also depends on unavailable history.

The frozen policy is `PARTIAL`: a missing lookback boundary fails closed, while a valid boundary with no matching finite exclusion row is treated as safe. No exception is raised for the insufficient-history case; it is represented as an unsafe flag and reason. Given the bad calendar input, all-member exclusion was deterministic and expected from this fail-closed branch, but the bad input itself was not the intended data semantics.

## Required exclusion taxonomy

All required categories are emitted for every audited date, including zero-count categories:

- `CORPORATE_ACTION_EVENT`
- `CA_COVERAGE_UNAVAILABLE`
- `ADJUSTMENT_FACTOR_UNAVAILABLE`
- `IDENTITY_UNRESOLVED`
- `INTERVAL_UNCOVERED`
- `DATE_OUTSIDE_SOURCE_RANGE`
- `STRUCTURAL_EXCLUSION`
- `MANUAL_REVIEW_REQUIRED`
- `OTHER`
- `UNEXPLAINED`

The detailed exclusion report retains each symbol, ISIN, exact raw reason, mapped category, global-boundary flag, observed and full-history boundaries, and genuine full-history blocker reasons. No excluded row remains unexplained.

## Replacement-validation governance

No replacement validation is authorized by this audit. The preliminary criteria assessment is:

| Criterion | Status | Basis |
|---|---|---|
| A. Root cause existed before outcomes | PASS | The calendar truncation is in the frozen validation code. |
| B. Independently reproducible | PASS | Frozen dates and inputs reproduce the same null-boundary chain. |
| C. Fix does not alter strategy | PASS | A calendar-input correction can preserve the frozen candidate and rules. |
| D. Fix does not alter success criteria | PASS | No criterion needs to change. |
| E. Restores intended frozen semantics | PASS | Pre-window sessions are signal history, not additional evaluated portfolio dates. |
| F. No outcome-guided choices | PASS | The required distinction follows from lineage and function contracts, not returns. |

These PASS assessments establish only that a future proposal could be considered. They do not authorize a rerun. A separate, explicit governance command would have to approve any remediation and replacement exercise.

Validation outcomes are now known. Therefore any future replacement validation would be `POST_OUTCOME_REMEDIATED_VALIDATION` and cannot be described as pristine one-shot holdout evidence. This disclosure is permanent.

## Audit hashes and artifacts

- configuration: `5fe5703a9f96fc5d6e4a6595f4c1fe4b2e44b3bc1b86e255897ab7b0ccdfa951`
- source coverage: `ab36f7be9fda9414f759d8b76ab5fa76a67b680b078bb0651f367c517bb464d9`
- derived coverage: `775f642eaa4eafeae7eff3762de255559a72aa340b4b81b0606f3afd46cce6bc`
- exclusion breakdown: `bd45a21a05815711e186024bf14c095626bdb5722452c75650a0cf056d7968d1`
- root cause: `66c5beecae4b6e500b2f9f9f23adabbb86056ddca70f7a6f192008b7a5383a24`
- governance assessment: `a6d99e8b1b5a079ccd79d42a331550a066e5628ac0e52fa654a959f657bb9192`
- immutable audit manifest: `a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793`

The canonical artifacts are under `data/research/validation/family_a/v1/post_validation_ca_audit/`; report copies are under `data/reports/`. The command made no CA rule or data changes, did not rebuild the derived layer, did not alter Family A or its criteria, did not create Strategy V2, and produced no live signals, orders, broker calls, migrations, Supabase writes, or external writes.

## Governance options

The only recommended next action is a separate governance review deciding whether to authorize a narrowly specified code-only remediation and a permanently labeled `POST_OUTCOME_REMEDIATED_VALIDATION`. This audit must not be interpreted as that authorization, and remediation must not begin automatically.
