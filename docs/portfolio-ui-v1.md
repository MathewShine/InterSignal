# Portfolio UI v1

## Purpose

Portfolio is the authenticated, read-only Portfolio Operating System view of ownership, allocation, exposure, performance, risk context, and recorded activity. It is not a broker terminal. The v1 surface contains no order entry, broker authentication, live pricing, portfolio mutation, or real user authentication.

## Routes

- `/app/portfolio` — integrated overview
- `/app/portfolio/holdings` — searchable, sortable holdings and lot detail
- `/app/portfolio/performance` — recorded P&L, benchmark comparison, and valuation history
- `/app/portfolio/activity` — Portfolio OS transactions and operational events

Home's `View portfolio →` link and the authenticated command palette use these routes. The command palette exposes Portfolio, Holdings, Portfolio activity, and Performance.

## HTTP contract

All Portfolio endpoints are GET-only, set `Cache-Control: no-store`, and return `INTERSIGNAL_PORTFOLIO_OS_V1`:

- `GET /api/portfolio/overview`
- `GET /api/portfolio/holdings`
- `GET /api/portfolio/activity`
- `GET /api/portfolio/performance`

Each endpoint accepts the optional `portfolio_id` query parameter. With no parameter, the shared deterministic primary selector chooses manual portfolios before research portfolios and then orders by portfolio ID. This is the same selector used by Intelligence Home.

The overview is the single-request first-view contract. It includes the selected portfolio, available portfolio options, summary valuation, holdings, allocation, concentration, benchmark, performance, recent activity, availability status, and per-section failure metadata. The frontend uses `VITE_API_BASE_URL`; it has no Portfolio-specific configuration path.

## View-model boundary

The backend presentation service maps explicit safe response models from `PortfolioOSService` read methods. It does not expose raw domain objects, provider account references, actors, paths, credentials, secrets, tokens, or environment state.

The frontend boundary is:

`PortfolioDataService → ApiPortfolioAdapter → Portfolio normalizers → component view models`

Components do not consume backend snake-case fields. The adapter validates the contract version and maps HTTP, timeout, cancellation, invalid-response, incompatibility, and not-found failures to sanitized errors. There is no runtime frontend fixture or fallback holdings path.

## Portfolio OS mapping

The API preserves canonical Portfolio OS values:

- portfolio value → `PortfolioValuation.net_liquidation_value`
- invested amount → `PortfolioValuation.gross_market_value`
- cash → `PortfolioValuation.cash`
- cost basis and realised/unrealised/total P&L → `PortfolioValuation`
- invested and cash weights → `ExposureSnapshot.gross_exposure` and `cash_pct`
- holding quantities, costs, prices, values, and unrealised P&L → `Holding`
- holding weights → `ExposureSnapshot.security_concentration`
- sector weights → `ExposureSnapshot.sector_exposure`
- top-one/top-five concentration and supported flags → `PortfolioRiskSnapshot`
- period, benchmark, and difference → `PortfolioBenchmarkComparison`
- benchmark name → `BenchmarkReference`
- recorded history → `PortfolioPerformancePoint`
- activity → `PortfolioTransaction` plus non-duplicated `PortfolioEvent` records
- lots → `PositionLot`

The API performs presentation mapping only. It does not recalculate portfolio valuation, exposure, weights, FIFO P&L, performance, or benchmark outputs. Adding read getters for security and benchmark references and sharing primary selection changes no Portfolio OS calculation semantics.

## Source semantics

Seeded records have `source_type = SYNTHETIC`. The customer label is `Demo portfolio`, with the tooltip: “This portfolio is generated from the platform’s seeded Portfolio OS data.” The UI does not call this a live, connected, or user portfolio.

The current store contains two first-class seeded portfolios, so the authenticated UI provides a compact selector. The default remains the manual investment portfolio already used by Home.

## Allocation, holdings, and lots

Allocation uses a segmented horizontal invested/cash band and compact sector bars. Percentages come from ExposureSnapshot; no pie or synthetic allocation is created. Concentration remains numeric unless Portfolio OS provides a risk flag.

Desktop holdings use a dense semantic table with search, sector filtering, sortable column announcements, and 48–56px rows. Mobile uses holding cards. Opening a row shows a keyboard-accessible read-only drawer containing security metadata, cost basis, value, weight, sector, unrealised P&L, and FIFO lot records. Lot status is a presentation label derived only from original and remaining Portfolio OS lot quantities.

## Performance and benchmark

Performance shows the Portfolio OS period return, benchmark return, difference, realised P&L, and unrealised P&L. Customer wording is `vs benchmark`; the UI makes no alpha claim. A line chart is shown only when at least three real performance points exist. With the current two-point seed, the UI explicitly reports two valuation dates and withholds the chart instead of inventing history.

## Activity

Activity displays real transaction and event records with date, type, security where applicable, quantity, amount where applicable, and a safe internal reference. Transaction-recorded events are omitted when their canonical transaction row is already present, avoiding duplicate activity. No activity control mutates state.

## Empty, partial, loading, and error states

- Empty: `has_portfolio = false` displays `No portfolio yet`, a disabled manual-holdings affordance, and `Connect broker — Coming later`; it never substitutes fake holdings.
- Partial: overview sections are isolated. Available holdings and allocation remain usable while an unavailable section states that its data is unavailable.
- Loading: summary, holding-row, and allocation-band skeletons preserve the page shape.
- Error: a compact retry surface states that Portfolio data could not be loaded and confirms no demo holdings were substituted.

## Responsive behavior

Desktop uses an integrated summary, holdings/allocation relationship, then performance/activity. The canvas is width-limited on wide screens. At tablet widths the summary wraps and the overview panels stack without page-level horizontal scrolling. Below 768px, the order is value, invested/cash, allocation, holding cards, performance, and activity; the authenticated bottom navigation remains available. Secondary table columns condense before the mobile card transition.

## Accessibility

The UI uses semantic tables and captions, `aria-sort`, live sort announcements, text plus color for P&L, text summaries for chart availability, visible focus inherited from the product shell, descriptive source tooltips, and a modal drawer that focuses its close control and supports Escape.

## Read-only and integration boundary

Today:

`Portfolio OS seeded/synthetic source → Portfolio API → PortfolioDataService → same Portfolio UI`

Future:

`Broker Adapter → normalized broker holdings → Portfolio OS → same Portfolio API → same Portfolio UI`

A future broker adapter belongs upstream of Portfolio OS. It must normalize broker records into the existing domain and preserve the API contract. The UI should not require a redesign when an authorized real source replaces the seed. Broker credentials, authentication, syncing, order execution, and live market data remain explicitly outside this step.
