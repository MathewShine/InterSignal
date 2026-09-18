# InterSignal Intelligence Home V1

## Command profile

- Version: `INTERSIGNAL_INTELLIGENCE_HOME_V1`
- Profile: `ATTENTION_CONTEXT_PORTFOLIO_RESEARCH_HOME_V1`
- Route: `/app`
- Runtime mode: backend read API by default, deterministic demo mode by explicit selection

## Information architecture

The Home is a compact investment-intelligence dashboard. A shared authenticated shell contains the reflowing application rail, white contextual top bar, mobile navigation, command palette, and an optional notification-driven context drawer. The workspace uses a bright neutral canvas and a disciplined 12-column hierarchy instead of a uniform wall of cards.

The desktop reading order is:

1. Market overview and portfolio position in a 7/5 relationship.
2. Important platform changes and the research programme summary in a 7/5 relationship.
3. Recent activity, Data health, and Governance readiness as smaller operational support panels.

At 1440×900 and 1366×768, the compact Overview header, both primary cards, at least the first two attention rows, and the Research summary are visible without overlap. Wide screens retain the relationships inside a large 1800px maximum workspace rather than stretching a single card indefinitely.

## Backend-domain mapping

| Home concern | Current source |
| --- | --- |
| Research pulse and evidence | `GET /api/home/snapshot` → Research Workbench |
| Portfolio state and exposure | `GET /api/home/snapshot` → Portfolio OS |
| Governance readiness | `GET /api/home/snapshot` → Governance/Audit |
| Data health and integrity | `GET /api/home/snapshot` → platform integrity projections |
| Recent activity and platform attention | `GET /api/home/snapshot` → backend audit timeline/state |
| Market context | Explicitly illustrative local visualization; backend market is unavailable |
| Broker connectivity | Future broker adapter |

No browser code reads backend files or research JSON directly. The browser consumes the read-only, versioned Home endpoint through `ApiHomeAdapter`. No credential, token, broker connection, live market service, write API, or real server session is implemented in this version.

## Data boundary

`HomeDataService` defines the public frontend contract:

- `getHomeSnapshot()`
- `getAttentionItems()`
- `getMarketContext()`
- `getPortfolioContext()`
- `getResearchPulse()`
- `getDataHealth()`
- `getGovernancePulse()`
- `getRecentActivity()`

`ApiHomeAdapter` is the default implementation. It validates `INTERSIGNAL_HOME_SNAPSHOT_V1`, performs one request, and passes the API DTO through `normalizeHomeSnapshot()` before Home components receive it. `DemoHomeAdapter` remains available for isolated tests, deterministic visual QA, and explicitly selected demo mode; it is never an automatic network-failure fallback.

## Truthfulness policy

Research, Portfolio, Governance, Data Health, Recent Activity, and Platform Attention come from the backend. The market canvas alone retains local preview values and carries one discreet `Sample market data` tag whose tooltip explains that live market connection has not been enabled. The seeded Portfolio OS projection carries a `Demo portfolio` tag whose tooltip explains its seeded source. Raw values such as `SYNTHETIC`, `PAUSED`, and `NOT_READY` remain available as view-model metadata while the visible UI uses customer-facing labels. Research evidence remains evidence and is never described as a production strategy.

No connected-state backend label appears in the top bar. Partial connection state is a small system indicator; an offline or failed refresh adds a compact inline notice while retaining the dashboard composition and the market preview.

## Component hierarchy

`AuthenticatedShell` owns `AppRail`, `HomeContextBar`, `MobileAppNav`, `CommandPalette`, and the contextual-drawer slot. Its grid transitions from a 72px collapsed rail to a 210px expanded rail, so the workspace moves and resizes rather than being covered. `HomePage` loads the service and coordinates the selected Attention Item. `MarketContextCanvas` contains its own preview interaction; `AttentionStream` contains backend platform items only. Supporting areas are `PortfolioContextStrip`, `ResearchPulse`, `RecentActivity`, `DataHealthPulse`, and `GovernancePulse`.

Future application routes reuse `AuthenticatedShell` and intentionally render lightweight “Coming next” surfaces until separately authorized.

## Interaction model

Important today includes backend Research, Portfolio, Governance, and Data items only; preview-market examples remain inside Market overview. Selecting a platform item focuses its corresponding section without creating a market-chart implication. The context drawer opens from the notification control and presents supporting context without an edge-mounted debug trigger. The command palette opens from the compact search trigger or `Ctrl+K` / `⌘K`, supports arrow-key selection, Enter, and Escape, and searches normalized backend context plus local route metadata.

## Loading, empty, partial, and error behavior

The Home starts in `CONNECTING`, cancels the request on unmount, and applies the centralized seven-second timeout. Its skeleton preserves the final two-row dashboard geometry. Successful responses render each domain according to its own `AVAILABLE`, `PARTIAL`, or `UNAVAILABLE` status. An explicit empty portfolio produces the compact “No portfolio yet” state with manual holdings and a disabled “Connect broker — Coming later” action; it receives no synthetic fallback. Network, timeout, or compatibility failures produce sanitized `DISCONNECTED`/`ERROR` context, retry without a page reload, and retain stable section footprints. The compact notice says that some data could not be refreshed instead of exposing backend vocabulary.

## Responsive behavior

- At 1200px and above, Market/Portfolio and Important today/Research use asymmetric 7/5 rows; Activity/Data/Readiness form a lower support row.
- From 768px through 1199px, the slim icon rail remains while Market, Portfolio, Important today, and Research stack in priority order.
- Below 768px, the rail is replaced by bottom navigation and the reading order becomes Overview, Market, Portfolio, Important today, Research, Activity, Data, and Readiness.
- Mobile card controls and metrics wrap without horizontal overflow, while the bottom navigation remains fixed and keyboard focus remains visible.

Authenticated motion is local and restrained: shell materialization, fast section arrival, linked context focus, and small data transitions. Reduced-motion preferences remove or shorten those effects. There is no landing-style scroll choreography.
