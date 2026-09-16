# InterSignal Governance / Audit domain v1

## Purpose and boundary

`INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_V1` provides the shared backend domain for observing state, validating rules, authorizing controlled actions, and recording immutable history. It does not replace the Strategy Registry, Evidence Registry, Lineage Registry, Research Workbench, or Portfolio OS as a source of truth. Governance records approval state and projections; any permitted business mutation must still be submitted through the owning domain service.

There is no UI, broker adapter, market feed, execution path, shadow mode, paper trading, live trading, strategy creation, migration, or Supabase persistence in this foundation.

## Governance subjects

`GovernanceSubject` projects an existing or planned entity through a stable subject type and ID. It records domain, current state, readiness state, optional artifact and lineage references, and descriptive metadata. Supported types cover strategies, evidence, validations, portfolios, accounts, broker connections, data sources, research programs, and platform modules.

The initial state projects the paused A–G research programme, Family A’s closed status, Family D’s data blocker, Family F’s source/licensing blocker, the two synthetic Portfolio OS portfolios, a disconnected broker capability, paper/live/production capabilities, and platform modules 04.01 through 04.05.

## Violations and overrides

Violations are append-only state histories: `OPEN`, `ACKNOWLEDGED`, `RESOLVED`, or `WAIVED`. Waiver is not a synonym for resolution and requires a currently approved, correctly scoped `MANUAL_OVERRIDE` authorization. A manual override also requires explicit authorization, an approver matching that authorization, a reason, before/after state, and optional expiry.

Recording an override does not apply the described state change. The owner must use the relevant domain service. This prevents governance from silently changing strategy lifecycle, holdings, transactions, evidence, or lineage.

## Append-only audit

Every governed write emits an immutable `AuditEvent`; direct audit append is itself the audit write. Local JSONL records are stored in hash envelopes using `INTERSIGNAL_CANONICAL_SHA256_V1`. Authorization and violation transitions append new versions instead of replacing prior versions. There is no destructive delete.

The combined audit timeline projects existing `RegistryEvent` and `PortfolioEvent` records read-only, then merges them with governance audit events using UTC timestamp, source priority, and source event ID. Source transaction and research records are not copied or mutated.

## Integrity

Integrity checks cover subject references, authorization transitions, expired approval usage, overrides and waivers without authorization, duplicate IDs, audit ordering, simultaneous enabled policy versions, JSONL hash mismatches, and referenced artifacts/evidence/lineage. Initial exported integrity must be `HEALTHY` with zero failures.
