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
