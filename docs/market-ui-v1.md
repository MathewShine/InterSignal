# Market Intelligence UI V1

## Scope

Step 04.11 replaces the authenticated `/app/market` placeholder with a read-only Market Intelligence overview backed by `GET /api/market/snapshot`. The page consumes only `INTERSIGNAL_MARKET_SNAPSHOT_V1`. It does not connect a broker or Groww, place orders, expose an Alerts workflow, generate strategy signals, infer a market regime, or change any Research, Portfolio, Data, or Governance conclusion.

## Data path

The frontend dependency direction is:

`MarketDataService -> ApiMarketAdapter -> normalizeMarketSnapshot -> selectors -> MarketPage`

- `MarketDataService` defines the frontend read boundary.
- `ApiMarketAdapter` performs exactly one cache-free `GET /api/market/snapshot` request, validates the contract version, applies cancellation and timeout handling, and returns sanitized errors.
- `normalizeMarketSnapshot` converts API snake-case fields and decimal strings into a stable frontend model. It preserves nullable fields as `null`.
- selectors identify primary/reference indices, sort sector rows, and derive deterministic descriptive summaries from returned values.
- components receive normalized data and do not call `fetch` directly.

The production UI contains no hardcoded snapshot metrics. Test values live only in `src/test/marketApiFixture.js`.

## Truthful customer wording

The recorded provider mode is presented as **Recorded market data**. Its technical mode remains available through the source label tooltip as **Provider mode: Seeded**. A stale recorded observation is presented as **Historical snapshot** and the visible date is **Recorded 7 Sep 2026**. These labels prevent a recorded end-of-day observation from appearing live or current.

The aggregate `PARTIAL` response remains visible as **Partial** in Snapshot quality. Per-section states determine whether a panel renders data or an explicit unavailable message. An HTTP/transport or incompatible-contract failure renders a compact error with Retry and states that Research and Portfolio remain accessible. No demo or sample values are substituted. An aggregate/provider `UNAVAILABLE` response renders the same honest boundary without the recorded metrics.

## Page hierarchy

The first desktop viewport contains:

1. compact Market Intelligence header with recorded source, closed session and recorded date;
2. dominant NIFTY 500 canvas using only the returned point observation and change;
3. NIFTY 50 reference index plus source, freshness and 498/501 coverage;
4. recorded breadth with 171 advancers, 325 decliners and 2 unchanged;
5. leading and lagging sector context based only on recorded one-session return;
6. volume context with aggregate traded value, median relative volume and members above their 20-session baseline.

The zero-centred index mark, breadth segments, sector return bars and volume bar are direct visual encodings of returned point/session values. No historical path, sparkline, trajectory or missing time series is invented.

The full Sector context table renders all 23 returned sector rows. Its accessible select sorts by Performance, Breadth or Name. Nullable member breadth, volume and mapping fields render as **Unavailable** or **Not mapped**, never as zero. Relative strength remains the backend-defined one-session sector return minus NIFTY 500 return and is not described as a recommendation.

Snapshot quality exposes coverage, missing members, recorded date, current-effective-only membership and disconnected broker state. Known limitations are rendered from the API summaries without changing their meaning. In particular, Above VWAP remains **Unavailable** because no trusted recorded session VWAP exists.

## Responsive behaviour

Desktop keeps the summary hierarchy dense enough for the first viewport while the expandable rail continues to reflow, rather than overlay, content. Tablet reduces the three context columns to two and then one. Mobile follows this semantic order:

1. header;
2. NIFTY 500;
3. NIFTY 50;
4. breadth;
5. volume;
6. sector leadership;
7. full sector context;
8. quality and limitations.

The existing authenticated bottom navigation remains active at mobile widths. Wide semantic tables use a local horizontal scroll container, while the document itself is verified not to overflow at 1920×1080, 1536×960, 1440×900, 1366×768, 1280×800, 1024×768, 768×1024 and 390×844. Loading shimmer is disabled when reduced motion is requested.

## Shell and Home integration

The global rail already contained Market and its active routing semantics are retained. The Market command palette adds **Market breadth** and **Sector context** destinations on the single overview route, using section fragments instead of proliferating pages.

Home now exposes **Market context →** to `/app/market`. Home’s market canvas remains explicitly tagged **Sample market data** and was not wired to `MarketSnapshot`. That canvas requires illustrative multi-horizon trajectory and participation arrays that the point-in-time V1 snapshot deliberately does not provide. Replacing it with inferred history would violate the contract. A future Home integration should use a dedicated truthful summary model or a backend contract that explicitly supplies the required series.

## Verification

Focused and full verification commands are:

```text
cd frontend
node_modules\.bin\vitest.cmd run src/features/market
node_modules\.bin\vitest.cmd run
node_modules\.bin\vite.cmd build
node_modules\.bin\playwright.cmd test e2e/market-flow.spec.js
node_modules\.bin\playwright.cmd test e2e/market-screenshots.spec.js
node_modules\.bin\playwright.cmd test

cd backend
.venv\Scripts\python.exe -m pytest -q
```

The Market browser suite covers the real backend contract and request method/count, Home entry, recorded semantics, full sector count and sorting, command destinations, partial/unavailable modes, retry without fallback, rail reflow, keyboard/table semantics, reduced motion, first-viewport content and all required viewport widths. Screenshot artifacts are written beneath ignored `frontend/test-results/market-qa/` and are not product source files.

## Future boundaries

A future live-provider adapter may implement the existing backend provider interface only after read-only live access is explicitly approved and its timestamps, rate limits, normalization and failure behaviour are verified. The UI should continue to consume the versioned Market Snapshot contract and must never call a provider directly.

The market-regime engine remains a separate locked capability. If it is implemented later, its classified outputs need an independent versioned service and explicit product semantics; this V1 page must remain descriptive market context and must not infer regime or strategy output from raw snapshot values.
