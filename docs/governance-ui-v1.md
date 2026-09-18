# Governance UI v1

Step 04.09 exposes the existing governance and audit foundation as a read-only product experience. It does not authorize actions, add broker connectivity, enable live markets, implement authentication enforcement, or mutate policy/readiness state.

## Routes and contract

Frontend routes are `/app/governance`, `/app/governance/readiness`, `/app/governance/policies`, `/app/governance/authorizations`, and `/app/governance/audit`. They use `GovernanceDataService` through `ApiGovernanceAdapter`, reuse `VITE_API_BASE_URL`, validate `INTERSIGNAL_GOVERNANCE_V1`, and normalize records before rendering.

Backend routes are `GET /api/governance/overview`, `/readiness`, `/policies`, `/authorizations`, and `/audit`. The overview is one aggregate request. All endpoints are GET-only, `Cache-Control: no-store`, failure-isolated at overview-section level, and use safe presentation DTOs rather than exposing arbitrary metadata or internal paths.

## Canonical state and semantics

- Paper, live, broker, and production readiness are independently `NOT_READY`; broker connection state is `NOT_CONNECTED`.
- Blocking violations are zero and one data-acquisition authorization remains requested.
- Eight of eight latest policy evaluations pass. This means current restrictions are being respected; it does not imply readiness.
- Audit renders real governance, registry and Portfolio OS events in reverse chronological order.
- Manual overrides are shown when present. The current repository contains none, so the UI shows an honest empty state.

Home and Governance read the same canonical `GovernanceService` summary. Home links directly to readiness detail.

## Experience states and responsive behavior

The UI provides loading skeletons, sanitized retry/error behavior without fixture fallback, partial-section notices, honest empty states, semantic readiness/policy/authorization/audit structures, authenticated-shell keyboard navigation, and reduced-motion support. Summary metrics, readiness cards, and audit rows progressively reflow while preserving mobile bottom navigation. Responsive QA covers 1920, 1536, 1440, 1366, 1024, 768, and 390 pixels.

Future operational integrations must remain downstream of recorded authorization and readiness decisions. A passing policy evaluation must never be treated as automatic permission, readiness, broker connection, or production approval.
