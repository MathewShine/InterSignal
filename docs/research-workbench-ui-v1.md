# Research Workbench UI V1

## Purpose

`INTERSIGNAL_RESEARCH_WORKBENCH_V1` is the read-only product projection of the existing Research Workbench, platform strategy registry, evidence registry, artifact registry, event registry and lineage graph. It presents hypotheses, evidence, validation integrity, negative findings, blockers and decision history. It is not a strategy leaderboard and does not make investment or production recommendations.

The browser runtime uses `VITE_API_BASE_URL` through `ApiResearchAdapter`. Components do not fetch directly, and no demonstration fixture is available as an active Research runtime fallback.

## Authenticated routes

- `/app/research` — programme overview, A–G matrix, retained evidence, blockers and recent activity.
- `/app/research/families` — searchable and filterable family registry.
- `/app/research/families/:familyId` — chronological family detail with evidence, validation, timeline, artifacts and lineage.
- `/app/research/evidence` — searchable and filterable evidence registry.
- `/app/research/evidence/:evidenceId` — evidence context, disposition, artifacts and lineage.
- `/app/research/validation` — formal, post-remediation, development and readiness records with integrity state.
- `/app/research/blocked` — data and source blockers with impact and required resolution.
- `/app/research/timeline` — chronological registry activity.

The shared authenticated rail links back to Home. The Research sub-navigation is intentionally compact and is not a second application rail.

## Read-only backend API

All responses declare `INTERSIGNAL_RESEARCH_WORKBENCH_V1`, set `Cache-Control: no-store`, expose explicit DTOs rather than internal domain objects, and mark the contract read-only.

- `GET /api/research/overview`
- `GET /api/research/families`
- `GET /api/research/families/{family_id}`
- `GET /api/research/evidence`
- `GET /api/research/evidence/{evidence_id}`
- `GET /api/research/validation`
- `GET /api/research/blocked`
- `GET /api/research/timeline`

`ResearchApplicationService` projects the canonical `ResearchWorkbenchService`; it does not duplicate the Home snapshot. `ResearchDataService` is the frontend interface, `ApiResearchAdapter` owns transport and cancellation, and the normalizers validate the contract before adapting snake-case DTOs for components. An unknown version becomes a controlled compatibility error. Overview reads are failure-isolated and may return `PARTIAL`; an unavailable request produces a compact Retry state without substituting demo data.

Artifact DTOs expose only registered identifiers, names, type, version, creation timestamp, immutability status and lineage node identifier. Internal paths, environment values, credentials and content bodies are excluded. Lineage is collapsed by default and exposes safe source/stage/relationship metadata only.

## Information architecture

The overview begins with five compact metrics: seven families, one canonical reusable evidence record, two blocked studies, zero production-ready candidates and a Paused programme. The primary surface is the A–G family matrix in family-code order. Secondary surfaces show the canonical retained evidence, blocked work and recent immutable registry activity.

The programme state remains:

- A–G cycle complete with no validated strategy.
- Research programme Paused.
- Primary programme `PRODUCT_PLATFORM_PROGRAM`.
- Secondary programme `FORWARD_DATA_PROGRAM`.
- Family H not planned.
- Strategy V2 not created.
- Paper and live readiness not ready.

## Family semantics

- Family A — `CLOSED_NOT_ADVANCED` and `REJECTED_FOR_CURRENT_CYCLE`. Formal validation is `INCONCLUSIVE` because an implementation logic defect invalidated the pristine one-shot evaluation. The separately classified, non-pristine post-remediation evaluation is `FAIL / UNSUPPORTIVE`. The 2025–26 holdout is contaminated and is not fresh validation evidence.
- Family B — relative plus absolute momentum filters. B001 was redundant. B002's apparent initial strength was traced to a history-availability artifact; clean incremental evidence was sparse and weak. It closed without a validation candidate.
- Family C — breakout continuation. Compression no greater than 8% improved event-level quality. Capacity and ranking implementation failed to produce a portfolio-ready candidate. `EDGE-EVIDENCE-C-COMPRESSION-001` is reusable signal-level evidence, not a production strategy.
- Family D — opening range / stocks-in-play. Exact prior-20 continuity is 77.826%, with 217 defective required symbol-sessions unresolved. It is `PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE`: blocked by data quality, not a strategy failure.
- Family E — pullback / reclaim. The control was negative and the treatment was worse. The family is `PAUSED_NO_VALIDATION_CANDIDATE`, with negative evidence retained.
- Family F — catalyst momentum feasibility. Timestamp feasibility was promising in the bounded pilot, but historical automation, authorization and licensing remain unresolved. It is `PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE`; no performance claim exists.
- Family G — quarterly six-month momentum with a Nifty 500 SMA200 participation gate. Control CAGR was 24.11% versus 11.95% for treatment; maximum drawdown worsened from 22.92% to 30.73%; the gate missed two large positive quarters. `EDGE-NEGATIVE-G-SMA200-GATE-001` is retained negative evidence.

## Evidence and validation

Evidence remains first-class whether positive, negative, validation, post-outcome, blocked or data-infrastructure evidence. The evidence registry supports Family, status, type and production-relevance filters plus ID/title/family search. Detail views show research context, classification, current disposition, safe supporting artifacts, limitations and lineage rather than a raw JSON dump.

Validation integrity is visible and not inferred from colour. Family A occupies two records: the formal one-shot `INCONCLUSIVE / IMPLEMENTATION_DEFECT` record with pristine intent, and the separate `FAIL / UNSUPPORTIVE / NON_PRISTINE` post-remediation record. They are never merged into “Family A validation failed.” Families D and F show readiness gates as not accessed rather than performance failures.

## Blocked research

Family D is a data blocker: continuity below the frozen threshold prevents trustworthy formal evaluation and requires a better intraday source. Family F is a source authorization blocker: unresolved historical acquisition/licensing prevents a robust catalyst study and requires an authorized historical announcement source. Neither is represented as a failed strategy.

## Interaction, search and accessibility

Family, evidence and blocked registries provide labelled compact filters and local search. The application command palette includes Research overview, Families A–G, Evidence, Validation, Blocked Research and Timeline. Home attention links route Family D and Family F directly to their Research detail pages, while the Home Research pulse routes to the overview.

Tables use captions, column headers and row headers. Mobile family records become linked cards. Statuses include text and a restrained marker, so meaning is not colour-only. Tabs/sub-navigation, filters, links, disclosure controls, Retry and the command palette are keyboard accessible. Loading uses layout-matched skeletons; empty results are distinct from failures; reduced-motion preferences disable skeleton animation.

## Responsive design

At desktop widths, the first viewport prioritizes the title, five summary metrics, all or most of the A–G matrix and the beginning of secondary context. The matrix uses compact fixed columns and no page-level horizontal overflow. At 768–1050 px, families become stacked rows while retaining the desktop rail. Below 768 px, the compact mobile shell and bottom navigation remain, the metrics become a two-column grid, and each family becomes an intentional card with status, one-line setup/evidence context and an open action.

The required visual QA set is 1920×1080, 1536×960, 1440×900, 1366×768, 1280×800, 1024×768, 768×1024 and 390×844.

## Scope policy

The entire surface is read-only. It has no hypothesis editing, approval, promotion, production mutation or manual registry write. Step 04.07 adds no Strategy V2, broker connection, live-market feed, real authentication, Portfolio UI, Data UI or Governance UI. It does not alter research conclusions, validation results or registry semantics.
