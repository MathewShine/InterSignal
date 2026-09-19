# Market live runbook v1

## Scope and safety

This runbook enables read-only Groww market data beneath InterSignal. It does not enable orders, execution, position sizing, or broker-account mutation. Never paste a token, API key, secret, or TOTP seed into source, frontend environment variables, logs, screenshots, browser storage, or this document.

Live operation requires an active Groww Trading API subscription and a supported authentication path described by the [official Groww authentication documentation](https://groww.in/trade-api/docs/curl). Code readiness is distinct from credential readiness.

## Required backend environment

Set `MARKET_DATA_PROVIDER=groww`, then configure one backend-only authentication method:

- `GROWW_API_ACCESS_TOKEN`; or
- `GROWW_API_KEY` and `GROWW_API_SECRET`; or
- the retained project-compatible TOTP method, `GROWW_TOTP_TOKEN` and `GROWW_TOTP_SECRET`.

Optionally set `MARKET_INSTRUMENT_CACHE` to a writable backend cache path. Keep all values in the ignored `backend/.env`; none use a `VITE_` prefix.

## Start and verify

1. Start the backend from `backend` with `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
2. Start the frontend from `frontend` with the existing Vite command and `VITE_API_BASE_URL=http://127.0.0.1:8000`.
3. Read `GET /api/market/provider/status`. Expect `provider=GROWW`, `configured=true`, the declared capabilities, and a sanitized stream state. `connected=false` before the first successful provider request/feed connection is valid.
4. Read `GET /api/market/instruments/search?q=RELIANCE`. Search is backed by the cached official [Groww instrument master](https://groww.in/trade-api/docs/curl/instruments).
5. Read `GET /api/market/instruments/RELIANCE/quote` and confirm the response contains only the normalized InterSignal contract.
6. Read `GET /api/market/instruments/RELIANCE/candles?range=1M`; the provider uses the official historical-candle boundary documented by [Groww Backtesting APIs](https://groww.in/trade-api/docs/curl/backtesting).
7. Open `/app/market/instruments/RELIANCE`. A visible active instrument may subscribe through `/api/market/stream`; the browser never receives the Groww socket URL or credentials.

## Monday exact checklist

1. Set `MARKET_DATA_PROVIDER=groww` in the ignored backend environment.
2. Start the backend with the repository-standard command.
3. Read `GET /api/market/provider/status`.
4. Confirm `configured=true` without printing any credential.
5. Confirm the sanitized stream and authentication state.
6. Open `/app/market`.
7. Search for `RELIANCE`.
8. Verify the normalized quote and its provider timestamp.
9. Verify the historical chart and last recorded candle timestamp.
10. Subscribe to the visible instrument through `/api/market/stream`.
11. When NSE opens, verify that the normalized quote timestamp changes without a page reload.
12. If aggregation is enabled and supported, verify breadth and sector updates; otherwise retain the explicit unavailable state.
13. Monitor sanitized rate-limit and provider errors; do not respond with aggressive retries.

## Closed and open sessions

Market closed is a valid state, not a failure. The UI should show the latest known quote, previous close, OHLC, recorded candle timestamp, and `Market closed`. A quiet stream is expected.

When the provider is connected and reports an open session, normalized ticks should update the active instrument or required index without a reload. The browser subscription cap is 25 instruments; the provider feed manager owns reference counts and respects the documented [Groww Feed](https://groww.in/trade-api/docs/python-sdk/feed) limit of 1,000 provider subscriptions.

## Rate limits and fallback

Live REST access is centralized in the backend with a two-second quote cache and a shared limiter for the officially documented 10 requests/second and 300 requests/minute live-data limits in [Groww API rate limits](https://groww.in/trade-api/docs/curl). A provider 429 becomes `PROVIDER_RATE_LIMITED`; the frontend must not start per-instrument one-second REST polling.

If streaming is unavailable, the current page may continue with REST quote/candle data. If candles are unavailable, the quote remains usable. If depth is absent, the UI states `Market depth unavailable`. If credentials are absent, provider status is `UNAVAILABLE / GROWW_NOT_CONFIGURED`; it does not silently fall back to seeded data.

## Troubleshooting

- `GROWW_NOT_CONFIGURED`: verify that a complete supported credential set is present only in the backend environment and restart the backend.
- `PROVIDER_RATE_LIMITED`: stop repeated clients, allow the provider window to recover, and verify no external caller is polling aggressively.
- instrument not found: refresh the backend instrument cache and verify the official CSV is reachable.
- stream `FAILED`: verify authentication, network access, active API subscription, instrument tokens, and bounded reconnect logs. Reconnect is exponential and capped; do not loop manually.
- quote available but depth/candles absent: treat it as feature-level partial availability, not a whole-workspace outage.

No successful live claim should be made until authentication, status, one read-only quote, one historical request, and one feed subscription have all succeeded in the target environment.

## Monday full-session observation

### Pre-open checklist

1. Confirm `backend/.env` is ignored and contains the intended Groww configuration without printing it.
2. Confirm `MARKET_TICK_RECORDING_MODE=SELECTED`, the seven monitored instruments, five-second sampling, 60-second summaries, and the frozen stale threshold.
3. Start the backend and frontend, then read `GET /api/market/provider/status`.
4. Confirm provider authentication succeeds, stream state can become `CONNECTED`, and `/app/market/session` contains no trading controls.
5. Confirm the local session root is writable and contains no evidence from an unrelated verification run.

### Start and opening checks

1. Before or during pre-open, use `POST /api/market/session/start` or **Start observation** in `/app/market/session`.
2. Confirm `SESSION_CREATED`, `PROVIDER_CONNECTED`, `STREAM_READY`, and `SUBSCRIBED` evidence appears.
3. Confirm the expected list contains NIFTY 50, NIFTY 500, BANK NIFTY, FINNIFTY, RELIANCE, TCS, and HDFCBANK (or their provider-resolved equivalents).
4. At market open, confirm `SESSION_OPEN`, the first normalized tick, and first updates for indices and equities.
5. Confirm `GET /api/market/session/current` reports provider heartbeat separately from `last_market_event_at`.

### Mid-session checks

1. Check `/app/market/session` periodically; do not create aggressive browser polling or per-instrument REST polling.
2. Confirm ticks, last-event time, observed coverage, and summary count continue to advance.
3. Confirm 60-second summaries record index state, subscriptions, coverage, breadth availability, sector availability, errors, and reconnects.
4. If breadth or sector aggregation is unavailable, confirm the limitation is recorded rather than synthesized.
5. If the feed disconnects, confirm explicit disconnect and reconnect events, retry number where available, and downtime duration.
6. If the provider throttles, confirm a sanitized `RATE_LIMITED` event without request headers or credentials.
7. If an open-session stream produces no normalized tick beyond the configured threshold, confirm `STALE_DATA_DETECTED`; after the next tick confirm `STALE_DATA_RECOVERED`.
8. Never use a closed-market quiet stream to test stale alarms; closed sessions must remain quiet without false degradation.

### Close and finalization

1. At exchange close, confirm `SESSION_CLOSED` followed by explicit finalization and `SESSION_COMPLETED`.
2. If controlled verification ends early, use `POST /api/market/session/stop`; do not infer completion from killing the API process.
3. Read `GET /api/market/sessions/{session_id}/summary` and confirm the deterministic `PASS`, `PASS_WITH_WARNINGS`, or `FAIL` criteria.
4. Confirm `market_session_<date>_<id>.json` exists beneath the configured reports directory.
5. Scan JSONL and the final report for API keys, secrets, tokens, TOTP values, authorization headers, cookies, and private provider endpoints. Required result: none.
6. Restart/reload the API and confirm the completed session, events, snapshots, and report remain readable.
7. Confirm no Research, Portfolio OS, Governance, strategy registry, signal, paper-order, position, fill, P&L, or broker-order state changed.
