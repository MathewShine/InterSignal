# Data UI v1

Step 04.09 exposes a read-only Data Health experience backed by the persisted InterSignal platform foundation. It does not acquire data, change research gates, mutate lineage, or substitute runtime demo fixtures.

## Routes and contract

Frontend routes are `/app/data`, `/app/data/sources`, `/app/data/lineage`, and `/app/data/limitations`. They use `DataHealthService` through `ApiDataAdapter`, which reads `VITE_API_BASE_URL`, performs GET-only requests, validates `INTERSIGNAL_DATA_HEALTH_V1`, and normalizes API fields into component view models.

Backend routes are `GET /api/data/overview`, `/sources`, `/lineage`, and `/limitations`. Overview is the single aggregate request used by the overview page. Responses are `Cache-Control: no-store`, contain safe identifiers only, and explicitly report `read_only`, unavailable sections, and whether runtime fixtures are present.

## Source mapping and status semantics

- Daily history is `AVAILABLE` from the canonical platform state.
- Corporate actions are `AVAILABLE_WITH_CAVEATS`; consumers must preserve recorded adjustment and continuity semantics.
- Intraday continuity reads the frozen Family D post-recovery record: 77.826177% with 217 unresolved gaps. It is `BLOCKED_FOR_RESEARCH_USE` and insufficient for trustworthy formal evaluation; this is not a strategy failure.
- Catalyst history is `SOURCE_BLOCKED`. The governance repository has one requested data-acquisition authorization, so it is not authorized for full research use.
- Lineage combines canonical node, edge and artifact registers with the same research, Portfolio OS and governance integrity calculations used by Home. Current integrity is `HEALTHY` with zero broken references.

Home and Data intentionally share the `PlatformDataHealthHomeSource` projection. Home deep-links blocking states to Data limitations.

## Experience states and responsive behavior

The UI includes shaped loading skeletons, sanitized retryable errors with no fallback records, partial-section notices, empty lineage/source/limitation states, semantic tables, labelled navigation, visible focus behavior inherited from the authenticated shell, and reduced-motion support. Dense source cards collapse from four columns to two and then one; tables scroll inside their own surface; mobile retains the established bottom navigation. Responsive QA covers 1920, 1536, 1440, 1366, 1024, 768, and 390 pixels.

Future data connectors may implement the same service contract, but they must retain point-in-time provenance, licensing status, explicit freshness, and the frozen research-use gates.
