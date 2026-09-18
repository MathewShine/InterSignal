# InterSignal Home Read API V1

## Purpose

`GET /api/home/snapshot` is the read-only backend contract for the authenticated Intelligence Home. It collects concise projections from existing backend domains into one versioned response without exposing their internal models or mutating their repositories.

Contract version: `INTERSIGNAL_HOME_SNAPSHOT_V1`

Step 04.06A introduced this backend contract without changing the frontend. Step 04.06B now consumes it through `ApiHomeAdapter`; `DemoHomeAdapter` remains only for explicitly selected demo and test scenarios.

## Contract

The response is a `HomeSnapshot` DTO with these top-level fields:

- `version`
- `generated_at`
- `mode`
- `availability`
- `market`
- `portfolio`
- `research`
- `data_health`
- `governance`
- `attention`
- `recent_activity`
- `meta`

`generated_at` is the only intentionally non-deterministic field. Attention and activity use stable deterministic ordering for identical source state.

## Source domains

| Home section | Backend source |
| --- | --- |
| Research | `ResearchWorkbenchService` over the platform registry |
| Portfolio | `PortfolioOSService` over seeded Portfolio OS repositories |
| Governance | `GovernanceService` readiness, policy, violation, and authorization projections |
| Data health | Research, Portfolio OS, and Governance integrity summaries plus canonical blocked-research state |
| Recent activity | Combined registry, Portfolio OS, and Governance audit timeline |
| Market | No backend source is configured |

The `HomeApplicationService` coordinates application-specific source adapters. The HTTP route does not assemble domain objects directly.

## Availability and partial failures

Each major domain reports `AVAILABLE`, `PARTIAL`, or `UNAVAILABLE` independently under `availability`. Section DTOs repeat their own status for convenient consumers.

One failed source is converted to an unavailable section with a stable sanitized reason code. Other sections still return, and the endpoint responds with HTTP 200. Stack traces, exception messages, internal paths, and credentials are never copied into the response. Endpoint-level failure is reserved for failure of the aggregation layer itself.

The current data-health section is `PARTIAL` because corporate-action caveats, the Family D intraday continuity blocker, and the Family F authorized-source blocker remain truthful platform limitations. Lineage integrity is reported semantically as `HEALTHY`; raw hashes are not exposed.

## Market limitation

The backend does not emit illustrative or live prices. Until a separately implemented market service exists, the response is:

```json
{
  "status": "UNAVAILABLE",
  "reason": "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
  "source": "NOT_CONFIGURED"
}
```

No market-derived attention alerts are generated.

## Portfolio truthfulness

The current Portfolio OS contains deterministic synthetic seeded portfolios. The Home response labels the selected context with `source_type: SYNTHETIC`; it must not be interpreted as a live user account. An empty repository returns an available empty state with `has_portfolio: false` instead of failing the endpoint.

## Research and attention truthfulness

Research is projected from the canonical Workbench state: the programme is paused, seven families exist, production and validated-production counts are zero, Strategy V2 is not created, Family C compression is research-only signal evidence, Family D is data-blocked, and Family F is source-blocked.

Attention items are operational context, never investment recommendations. Severity is limited to `INFO`, `NOTICE`, and `WARNING`; BUY/SELL semantics are not present.

## Read-only and cache behavior

The route calls only existing read methods. It creates no registry, portfolio, or audit events and performs no repository writes. Responses use:

`Cache-Control: no-store`

No stale application cache is introduced; repositories are projected from current local platform state per request.

## Authentication and CORS

`AUTH_ENFORCEMENT = NOT_IMPLEMENTED`

The endpoint is not represented as protected. No bearer-token validation, session persistence, or fake authentication has been added. The existing configured development-origin CORS policy remains unchanged; unrestricted wildcard CORS is not used.

## OpenAPI and future integration

FastAPI publishes the route and `HomeSnapshot` schema through the existing `/openapi.json` document. No separate schema system is introduced.

Future work, only when separately authorized, may add real authentication/session scope, a live market service, and user-specific Portfolio OS repositories. Neither Step 04.06A nor its 04.06B frontend integration adds those capabilities.
