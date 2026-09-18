# Market Data Foundation V1

## Purpose

Step 04.10 introduces a provider-neutral, read-only Market Intelligence backend for India/NSE. It normalizes recorded provider observations into `INTERSIGNAL_MARKET_SNAPSHOT_V1` and exposes them through `GET /api/market/snapshot`. It does not add a Market UI, trading execution, alerts, strategy decisions, or a market-regime engine.

## Architecture

The dependency direction is:

`MarketDataProvider -> normalized observations -> MarketIntelligenceService -> MarketSnapshot -> GET /api/market/snapshot`

- `app.providers.market_data.MarketDataProvider` defines the vendor-neutral provider boundary.
- `app.providers.market_seeded.SeededMarketDataProvider` reads recorded NSE project data and emits normalized observations.
- `app.market_api.service.MarketIntelligenceService` applies freshness, availability, failure isolation, quality metadata, and API DTO mapping.
- `app.market_api.models.MarketSnapshot` is the frozen, versioned response contract.
- `app.api.routes.market` contains only HTTP concerns and never reads provider internals.

Provider-specific response names and private source paths are not part of the API contract.

## Provider selection and modes

`MARKET_DATA_PROVIDER` is the single provider selector. Supported selections are:

| Selection | Exposed mode | Behaviour |
| --- | --- | --- |
| `seeded` | `SEEDED` | Reads deterministic recorded NSE end-of-day inputs. This is the default. |
| `groww` | `UNAVAILABLE` | Controlled unavailable response because a live Market adapter is not implemented. |
| `none` | `UNAVAILABLE` | Controlled unavailable response. |
| any unknown value | `UNAVAILABLE` | Controlled unsupported-selection response. |

The contract recognizes the explicit modes `LIVE`, `DELAYED`, `SEEDED`, and `UNAVAILABLE`. V1 never reports `LIVE`. Existing Groww credentials and historical-research integration are not treated as approval for a live snapshot adapter.

## India-first scope

The market is `INDIA_NSE`. `NIFTY_500` is the primary index and current-session universe; `NIFTY_50` is the reference index. V1 does not expand to US or UK markets.

The seeded provider uses these recorded sources when present:

- official NIFTY 500 and NIFTY 50 history from `data/reference/nse/indices/normalized/benchmark_daily.csv`;
- the current official NIFTY 500 constituent snapshot under `data/reference/nifty500/current/`;
- official sector-index history and the current sector mapping under `data/reference/nse/indices/normalized/`;
- the recorded NSE cash-market calendar under `data/reference/nse/calendar/`;
- the local recorded NSE daily archive under `data/historical/daily/nse/`, when available, for member breadth and volume context.

The ignored local daily archive is optional. Its absence degrades breadth and volume to explicit `UNAVAILABLE` sections while the tracked index, universe, sector-index, and session context remain usable. No runtime download occurs.

## Contract

`INTERSIGNAL_MARKET_SNAPSHOT_V1` contains:

- `generated_at`: UTC response-generation time;
- `status`: aggregate `AVAILABLE`, `PARTIAL`, or `UNAVAILABLE` state;
- `market`: country, exchange, primary index, and reference indices;
- `provider`: safe provider name, explicit mode, market, and capabilities;
- `freshness`: source time, API receipt time, age, and freshness state;
- `indices`: normalized NIFTY 500 and NIFTY 50 observations where present;
- `universe`: current effective NIFTY 500 membership metadata;
- `breadth`: current recorded-session participation metrics where supported;
- `sectors`: official sector-index returns plus member breadth/volume where supported;
- `volume`: aggregate traded value and 20-session relative-volume context where supported;
- `session`: exchange-calendar-backed state for the recorded observation;
- `availability`: per-section status and machine-readable reason;
- `limitations`: explicit caveats;
- `meta`: read-only and integration-boundary declarations.

Every index observation uses normalized fields: `symbol`, `name`, `value`, `change`, `change_pct`, `previous_close`, `timestamp`, `source`, and `freshness`. Unsupported values are `null`; they are never fabricated.

## Breadth and universe semantics

Breadth uses current effective NIFTY 500 membership and paired member closes from the latest two recorded NSE sessions. It returns advancers, decliners, unchanged, positive/negative percentages, and above-prior-close percentage. Above-VWAP percentage is `null` because the recorded daily source does not provide a trusted session VWAP.

Quality contains `coverage_count`, `expected_count`, `coverage_pct`, and `missing_count`. Current membership is valid for this current recorded-session projection only. It must not be silently substituted into historical research; historical logic continues to use point-in-time membership reconstruction.

## Sector context

Sector returns come from recorded official NSE sector-index closes. Relative strength is the one-session sector-index return minus the corresponding NIFTY 500 return. Member advancers, decliners, breadth, and median relative volume are added only when the current mapping and daily archive support them. A sector row remains valid with nullable unsupported fields and explicit partial availability.

## Volume context

When the local recorded daily archive supplies 21 sessions, V1 returns:

- aggregate current-session traded value in `INR_LAKH`, matching the recorded legacy bhavcopy unit;
- median member relative volume versus the median of the prior 20 sessions;
- count and percentage of covered members above their 20-session baseline;
- coverage quality.

V1 does not represent these end-of-day measures as intraday volume expansion. If the baseline is unavailable, the volume section is `UNAVAILABLE` rather than estimated.

## Session and freshness

Session values are `PRE_OPEN`, `OPEN`, `CLOSED`, or `UNKNOWN`. The seeded provider verifies the recorded market date against the recorded NSE calendar. A completed official end-of-day observation is `CLOSED`; it does not infer the current exchange state from the machine clock.

Freshness values are `FRESH`, `AGING`, `STALE`, or `UNKNOWN`. Thresholds are centralized in `MarketIntelligenceService`:

- `FRESH`: age up to 15 minutes;
- `AGING`: over 15 minutes and up to 24 hours;
- `STALE`: over 24 hours;
- `UNKNOWN`: no trustworthy source timestamp.

`age_seconds` is measured from the source observation timestamp to the API receipt/generation time. The explicit `SEEDED` mode remains authoritative even if a newly recorded fixture falls inside a freshness threshold.

## Failure isolation and availability

Indices, universe, breadth, sectors, volume, session, and freshness are read independently. A provider error in one section is converted to a controlled limitation without exposing exception text or a stack trace. Available sections remain in the response. If every data section is unavailable, the endpoint still returns HTTP 200 with aggregate `UNAVAILABLE` state.

## Security and read-only boundary

The route is GET-only and sends `Cache-Control: no-store`. It does not write registry, research, portfolio, governance, strategy, or source files. Provider metadata cannot include credentials, tokens, TOTP secrets, private URLs, environment values, or filesystem paths.

The API does not emit `BUY`, `SELL`, `LONG`, `SHORT`, `ENTRY`, `EXIT`, `TARGET`, or `STOP` decisions. It has no broker or order dependency.

## Known limitations

- No approved live Market provider is implemented.
- The seeded snapshot is recorded end-of-day context, not streaming or delayed-live data.
- Current effective membership is not valid for historical universe substitution.
- Above-VWAP breadth is unavailable.
- Member breadth and volume depend on the optional recorded local daily archive.
- Sector member coverage uses current-only mappings and is partial for sector indexes without a direct mapping.
- The legacy recorded traded-value unit is explicitly retained as `INR_LAKH`.

## Future boundaries

A future `GrowwMarketDataProvider` may implement the same interface after read-only live access is explicitly approved and its normalization, rate limits, timestamps, and failure semantics are verified. The Market UI should consume only the versioned API and must not call a provider directly. The locked market-regime engine remains a separate service and is not part of this raw/normalized foundation. Broker execution must remain independent from market-data providers.
