# InterSignal Home API Integration V1

## Purpose

Step 04.06B connects the authenticated Intelligence Home to the read-only backend aggregation contract through this runtime flow:

`HomePage → HomeDataService → ApiHomeAdapter → GET /api/home/snapshot → HomeApplicationService`

Home components never call `fetch` directly. The backend response is not passed through React as a raw snake-case DTO.

## Runtime configuration

Frontend settings are centralized in `frontend/src/config/runtimeConfig.js`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend origin |
| `VITE_HOME_DATA_MODE` | `api` | `api` for normal runtime; `demo` only for explicit offline/visual scenarios |
| `VITE_HOME_REQUEST_TIMEOUT_MS` | `7000` | Home request timeout |

`ApiHomeAdapter` requests exactly `GET /api/home/snapshot`, sends no credentials or fake bearer token, requests `no-store`, and validates `INTERSIGNAL_HOME_SNAPSHOT_V1`. Unknown versions fail with a controlled compatibility error.

## Normalization boundary

`normalizeHomeSnapshot()` maps the backend DTO into the existing frontend Home view model:

- snake-case API names become frontend camel-case names;
- meaningful raw states such as `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `PAUSED`, and `NOT_READY` remain explicit in view-model metadata while separate display labels keep the Home customer-facing;
- the Portfolio OS source becomes one of `REAL`, `SYNTHETIC`, `EMPTY`, or `UNAVAILABLE`;
- backend attention retains its source domain, source reference, context, action target, metadata, and operational severity;
- backend activity is displayed without frontend milestone padding;
- API DTOs remain isolated from components.

Research, Portfolio, Governance, Data Health, Recent Activity, and Platform Attention are backend-derived in API mode. `DemoHomeAdapter` remains only for explicitly selected demo mode, unit tests, and deterministic visual QA.

## Sample market exception

The backend truth remains:

```text
market.status = UNAVAILABLE
market.reason = LIVE_MARKET_SERVICE_NOT_CONFIGURED
```

The existing local market trajectory remains visible only as `Sample market data`, with a tooltip explaining that live market connection is not enabled. It never replaces backend availability and never claims to be live, real-time, or streaming. Market preview examples stay within Market overview and are excluded from the backend-derived Important today list.

## Availability and failure behavior

The connection model is `CONNECTING`, `CONNECTED`, `PARTIAL`, `DISCONNECTED`, or `ERROR`. A successful partial response renders each domain independently. A portfolio with `has_portfolio=false` renders the existing empty state and receives no synthetic fallback.

Network, timeout, HTTP, invalid-response, and unsupported-contract failures are sanitized. The Home does not show stack traces, Python exception names, filesystem paths, response dumps, credentials, or prominent implementation-state labels. Backend domains become unavailable without collapsing their layout, the sample market canvas remains clearly labelled, and Retry issues a new Home request without reloading the browser.

The request uses `AbortController`; unmounting Home cancels the in-flight request. No client-side domain calls or artificial delay are added.

## Local full-stack startup

Use the repository’s existing environments in two terminals.

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

Then open `http://localhost:5173/app`. The backend CORS configuration defaults to that development origin. To use another origin, set the backend `FRONTEND_URL` explicitly; wildcard CORS is not enabled.

## Deliberate non-goals

This integration adds no real authentication, broker connection, execution path, live market feed, write API, or Strategy V2. A future market service can replace only the illustrative market projection while preserving the normalized Home component contract.
