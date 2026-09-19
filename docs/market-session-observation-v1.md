# Market session observation v1

## Purpose

`INTERSIGNAL_MARKET_SESSION_V1` and `INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1` provide operational evidence for a continuous NSE session. They do not produce strategy, signal, execution, portfolio, or governance evidence.

The normalized flow is:

`Groww → MarketTickObservation → MarketLiveCache / MarketStreamHub → MarketSessionManager → repository protocols`

The recorder never parses raw Groww packets.

## Frozen Monday defaults

- Recording mode: `SELECTED`
- Observation cadence: five seconds per selected instrument
- Summary cadence: 60 seconds
- Open-session stale threshold: 30 seconds
- Monitored indices: NIFTY 50, NIFTY 500, BANK NIFTY, FINNIFTY
- Monitored equities: RELIANCE, TCS, HDFCBANK
- Closed sessions: stale detection disabled
- Manual start/stop: enabled through observation-only API routes

## Lifecycle and evidence

Session states are `CREATED`, `PRE_OPEN`, `RUNNING`, `DEGRADED`, `CLOSED`, `FAILED`, and `COMPLETED`. Completion requires explicit finalization or a reliably observed exchange close after the session was open; process termination alone does not imply completion.

Lifecycle, provider health, subscription, sampled tick/index, summary, stale/recovery, rate-limit, error, exchange-open/close, and finalization events are append-only. Disconnect/reconnect evidence carries reason, retry, and measured downtime where available.

## Deterministic result

The frozen operational criteria require provider connection, stream readiness, required subscriptions, an open-session first tick, no stale interval beyond the configured limit, successful recovery where a disconnect occurred, explicit finalization, and the read-only domain boundary.

- `FAIL`: any required criterion fails, including provider never connected or no tick during an observed open session.
- `PASS_WITH_WARNINGS`: all criteria pass, but a recoverable reconnect, operational error, or no-open-session limitation is recorded.
- `PASS`: all criteria pass without warnings.

The result is computed from the recorded contract and event stream. It is not chosen after inspecting the session.

## Evidence volume and safety

The manager counts all normalized ticks in memory but persists only the configured subset/cadence unless `ALL` is explicitly selected. Periodic summaries capture coverage and breadth/sector availability without fabricating missing aggregates. Evidence sanitization redacts credential-bearing keys and authorization/cookie-like strings before disk writes.
