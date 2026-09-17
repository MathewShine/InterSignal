# InterSignal Intelligence Home V1

## Command profile

- Version: `INTERSIGNAL_INTELLIGENCE_HOME_V1`
- Profile: `ATTENTION_CONTEXT_PORTFOLIO_RESEARCH_HOME_V1`
- Route: `/app`
- Runtime mode: deterministic frontend prototype data

## Information architecture

The Home is an attention-and-context surface rather than a dashboard. A shared authenticated shell contains the compact application rail, contextual top bar, mobile navigation, command palette, and an optional right-edge context drawer. Inside the Home, one dominant Today market canvas leads into an editorial Attention Stream. Portfolio exposure, Research pulse, Data health, Governance, recent activity, and next destinations progressively support that primary relationship.

The first-view reading order is:

1. What changed in the illustrative market context.
2. What deserves attention.
3. How the selected context maps to portfolio exposure.
4. Which preserved research evidence or limitation is relevant.
5. Where the user can continue.

## Backend-domain mapping

| Home concern | Intended future source |
| --- | --- |
| Research pulse and evidence | Research Workbench service/API |
| Portfolio state and exposure | Portfolio OS service/API |
| Governance readiness | Governance/Audit service/API |
| Data health and integrity | Platform lineage/API |
| Market context | Future real-time market service |
| Broker connectivity | Future broker adapter |

No browser code reads backend files or research JSON directly. No HTTP endpoint, database, credential, token, broker connection, or server session is implemented in this version.

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

`DemoHomeAdapter` currently implements that boundary with a cloned, deterministic fixture from `homeDemoData.js`. Home components receive service output through `HomePage`; they never import the fixture. A future `ApiHomeAdapter` can replace the implementation without changing the component interfaces.

## Truthfulness policy

The shell shows one global `DEMO / LOCAL DATA` label. Illustrative market and portfolio values are centralized in the fixture. Preserved project status remains explicit: research is paused, A–G is `COMPLETE_NO_VALIDATED_STRATEGY`, production candidates and validated strategies are zero, Strategy V2 is not created, Paper and Live are not ready, and the broker is not connected. Research evidence is labelled as evidence and not as a production strategy.

## Component hierarchy

`AuthenticatedShell` owns `AppRail`, `HomeContextBar`, `MobileAppNav`, `CommandPalette`, and the contextual-drawer slot. `HomePage` loads the service and coordinates the selected Attention Item. `MarketContextCanvas` and `PortfolioContextStrip` derive their highlighted context from that selection. Supporting areas are `ResearchPulse`, `DataHealthPulse`, `GovernancePulse`, `RecentActivity`, and `ExploreNext`.

Future application routes reuse `AuthenticatedShell` and intentionally render lightweight “Coming next” surfaces until separately authorized.

## Interaction model

Selecting an Attention row updates the market marker and relevant portfolio allocation segments without opening a modal. The context drawer exposes supporting Research, Data, Governance, and Alerts detail for the current selection. The command palette opens from the search trigger or `Ctrl+K` / `⌘K`, supports arrow-key selection, Enter, and Escape, and searches only local route and fixture metadata.

## Loading, empty, partial, and error behavior

The Home supports a compact loading skeleton, empty portfolio state, unavailable market state, unavailable research state, partial data health, and a retryable inline generic error. Market or research unavailability does not make unrelated Home context unusable. Broker connection remains disabled and labelled “Coming later.”

## Responsive behavior

- At 1440px and above, the market/portfolio canvas and attention/research context use an asymmetric desktop composition.
- From 1024px through smaller desktop widths, the compact rail remains and supporting context can move into the main stream.
- Tablet retains the slim icon rail and full-width market canvas; the context drawer overlays.
- Below 768px, the rail is replaced by bottom navigation and the reading order becomes Greeting, Today, Portfolio, Attention, Research, Data, Governance, Activity, and Explore next.

Authenticated motion is local and restrained: shell materialization, fast section arrival, linked context focus, and small data transitions. Reduced-motion preferences remove or shorten those effects. There is no landing-style scroll choreography.
