# InterSignal persistence roadmap v1

## Current Step 04.12 boundary

Market-session evidence is persisted locally beneath the configured `MARKET_SESSION_DATA_ROOT` using append-only JSONL files and immutable JSON evidence reports. The default path is `backend/tmp/market-observations`, which is repository-standard ignored runtime storage and survives API process restarts.

The application depends on the `MarketSessionRepository` and `MarketObservationRepository` protocols. Domain and session-management code does not depend on JSONL, Supabase, a vendor SDK, or a provider packet format.

Current local records:

- `market_sessions.jsonl`: successive durable versions of each session record; the latest version reconstructs current state.
- `market_observation_events.jsonl`: append-only sanitized operational events.
- `market_session_snapshots.jsonl`: periodic health, freshness, coverage, breadth, and sector-availability summaries.
- `reports/market_session_<date>_<id>.json`: final machine-readable criteria, result, metrics, warnings, failures, timeline, and limitations.

Raw provider packets and credentials are never part of this persistence boundary. Normalized ticks are recorded according to `NONE`, `SAMPLED`, `SELECTED`, or `ALL` policy; Monday defaults to `SELECTED` at a controlled five-second cadence.

## Future Supabase adapters

Future adapters may implement the existing protocols as:

- `SupabaseMarketSessionRepository`
- `SupabaseObservationRepository`

Conceptual tables:

### `market_sessions`

One row per observation session with lifecycle state, provider/mode, exchange state, start/end timestamps, tick/health counters, coverage, deterministic verdict, warnings, and failures.

### `market_observation_events`

Append-only sanitized lifecycle, provider-health, subscription, selected observation, stale/recovery, reconnect, rate-limit, breadth, sector, and completion events. Index on `(session_id, timestamp)`.

### `market_session_snapshots`

Periodic operational summaries with provider state, stream state, last-tick age, monitored-index state, subscriptions, coverage, breadth/sector availability, errors, and reconnect count.

Remote credentials, row-level-security policy, migrations, and live schema creation are deliberately deferred. No Supabase schema is introduced in Step 04.12.

## Later paper/shadow persistence

Only after the live-session infrastructure passes should separate schemas be considered for:

- `strategy_configs`
- `signal_candidates`
- `rejected_signals`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_outcomes`
- `alerts`

These are not part of the observation repositories and must not be inferred or written by market-session evidence.

The intended future flow is:

`Market Session → normalized observations → Shadow Observation Engine → Candidate / Rejected Candidate → evidence`

The Shadow Observation Engine, candidates, signals, orders, fills, positions, and P&L are not implemented in this step.

## Railway deployment design

The future deployment topology is:

1. Railway API service: serves normalized read APIs and the operational session controls.
2. Railway market worker / stream worker: maintains the provider connection, records heartbeats and normalized observations, runs stale/reconnect monitoring, and finalizes exchange sessions.
3. Supabase Postgres: implements the repository protocols and durable report metadata after the local verification boundary is proven.
4. Frontend: consumes API/WebSocket contracts only and never receives provider credentials or private provider endpoints.

The API and worker must share one session lease/ownership rule before horizontal scaling. Worker restarts must recover incomplete sessions without marking them completed merely because a process stopped. Deployment, remote credentials, leases, and distributed scheduling are explicitly deferred.

## Security and ownership rules

- Sanitize authorization, cookie, API-key, secret, token, password, and TOTP fields before persistence.
- Persist summaries of normalized observations, never raw provider packets.
- Keep provider credentials server-side and outside evidence artifacts.
- Observation repositories own only market-session operational evidence.
- Observation cannot mutate Research, Portfolio OS, Governance, strategy configuration, broker orders, or future paper-trading domains.
