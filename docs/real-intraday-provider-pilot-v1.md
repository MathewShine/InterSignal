# Real Intraday Provider Pilot V1

STATUS: PASS_WITH_LIMITATIONS — READY_FOR_BOUNDED_REAL_RESEARCH

This document records Step 02.14 / Command 04. The command is a data, provenance, and quality exercise only. It does not create or test Strategy V2, change Strategy V1 or its frozen outcomes, expose validation-period performance, rerun the portfolio, emit a trading signal, or call an order endpoint.

## Identity and scope

- Command: `REAL_INTRADAY_PROVIDER_PILOT_V1`
- Profile: `NSE_CASH_5M_PROVIDER_PILOT_V1`
- Capability audit: `INTRADAY_PROVIDER_CAPABILITY_AUDIT_V1`
- Canonical target: `NSE_CASH_INTRADAY_5M_V1`
- Sessions: 3–7 January 2022, five normal NSE cash sessions
- Symbols: ABCAPITAL, ALKYLAMINE, BALRAMCHIN, COALINDIA, TITAN
- Hard bounds: five symbols, five sessions each, 10,000 normalized-row ceiling, seven external-request ceiling
- Result: 25 of 25 regular symbol-sessions were strictly usable after deterministic session-boundary filtering

All selected dates are in the frozen DEVELOPMENT interval, 2022-01-01 through 2024-12-31. Validation remains SEALED with run count zero. The pilot used frozen development opportunities only to choose representative symbols and to exercise execution-order reconstruction. It did not calculate return, hit-rate, Sharpe, CAGR, or any other performance statistic.

## Provider capability audit

Groww was audited first. Its official backtesting API documents NSE CASH support, native 1/2/3/5-minute candles, OHLC and volume for equities, data from 2020, and a maximum 30-day request window for 5-minute bars. The official instrument master supplies exchange, trading symbol, Groww symbol, exchange token, and ISIN. The repository already had the official `growwapi` 1.5.0 SDK and ignored TOTP configuration. Sources: [Groww backtesting API](https://groww.in/trade-api/docs/curl/backtesting), [Groww instrument master](https://groww.in/trade-api/docs/curl/instruments), and [Groww Python SDK changelog](https://groww.in/trade-api/docs/python-sdk/changelog).

Groww explicitly presents this API as historical data for backtesting. The research-rights classification is therefore `USABLE_WITH_RESTRICTIONS` for this tiny private pilot. Local retention, long-term retention, redistribution, adjusted-price treatment, corporate-action semantics, historical-endpoint request rate, and current API price are not established by the audited pages and remain `UNKNOWN`. Raw data must not be redistributed or committed.

The official Groww examples are aligned like interval-start labels, and the real payload began at 09:15. However, the documentation prose does not explicitly define the candle timestamp as `BAR_START` rather than `BAR_END`. The pilot records `BAR_START_FROM_INTERVAL_ALIGNED_OFFICIAL_EXAMPLES_WITH_PROSE_LIMITATION` and retains that limitation instead of presenting it as unqualified provider prose.

Zerodha was the second candidate. Official Kite documentation supports NSE instrument tokens, historical OHLCV at native 5-minute resolution, `+0530` timestamps, several years of history, and a three-historical-requests-per-second limit. A provider-maintained forum answer states that timestamps are candle starts. No Kite credentials or adapter configuration existed in this project, and retention/redistribution terms require further review, so Zerodha was not contacted. Sources: [Kite historical candles](https://kite.trade/docs/connect/v3/historical/), [Kite instruments](https://kite.trade/docs/connect/v3/market-data-and-instruments/), [Kite rate limits](https://kite.trade/docs/connect/v3/exceptions/), and [provider-maintained timestamp clarification](https://kite.trade/forum/discussion/15973/timestamp-in-candle-data-is-open-time-or-candle-close-time).

No other licensed local real-intraday provider was configured. Synthetic fixtures were excluded as real evidence. No public, unofficial, reverse-engineered, or scraped source was considered.

## Credentials and market-data-only boundary

Credentials were read from `backend/.env` through existing settings. The audit and reports store only `credentials_present = true`; no key, access token, TOTP secret, authorization header, or secret-bearing exception is recorded.

The research adapter exposes instrument resolution and historical 5-minute retrieval only. It has no `place_order`, `modify_order`, or `cancel_order` method. It used one authentication request, one instrument-master request, and five historical-candle requests. All seven succeeded, no retry was used, and no fallback provider was registered. The adapter throttles to one request per second and permits at most three retries for transient network, rate-limit, or server failures. Authentication, permission, unsupported-history, and invalid-instrument failures are not retried indefinitely.

## Pilot selection

The selection was frozen before retrieval:

| Symbol | Frozen case context | Coverage purpose |
|---|---|---|
| ABCAPITAL | small gap up; neither level in four sessions | lower-price and time-exit context |
| ALKYLAMINE | small gap up; frozen stop-first case | high-price and stop-path context |
| BALRAMCHIN | gap down; frozen target-first case | target-path and gap context |
| COALINDIA | small gap up; neither level | lower-price/liquidity context |
| TITAN | gap down; later four-session horizon extends to 10 January | high-price and intentionally bounded partial holding context |

The provider instrument master resolved all five mappings cleanly, including exchange tokens and ISINs. Instrument validity dates remain unknown because the current instrument master is a snapshot rather than a point-in-time master.

The selected dates had no nearby structural corporate action in the repository’s corporate-action event registry. Intraday prices were not auto-adjusted.

## Provenance and storage

Every provider response is stored in a new timestamped retrieval directory under `data/raw/intraday/groww/pilot_v1/`. A raw record contains provider, request ID, internal and provider symbol, instrument ID, requested interval and dates, retrieval time, provider payload, and a content hash. Existing raw files are never overwritten. Re-fetching creates a new retrieval version.

Accepted canonical and derived datasets are stored under:

- `data/normalized/intraday/5m/real_provider_pilot_v1/`
- `data/derived/intraday/10m/real_provider_pilot_v1/`
- `data/derived/intraday/15m/real_provider_pilot_v1/`
- `data/research/intraday/v1/real_intraday_pilot_manifest_v1.json`

Raw, normalized, derived, manifest, and machine-report paths are ignored by Git. The five raw payloads contained 1,915 candle rows. Forty timestamped rows were at or after the 15:30 regular-session boundary—typically 15:30, 15:40, 15:45, or 16:00—and were preserved in raw provenance but excluded from the regular-session canonical dataset. The accepted dataset contains exactly 1,875 rows: 5 symbols × 5 sessions × 75 bars.

## Normalization and real-session quality

Naive provider timestamps are interpreted as Asia/Kolkata under the existing Groww adapter contract, converted to timezone-aware values, and retained as source timestamps. Canonical `bar_start` and `bar_end` are five minutes apart. Regular-session acceptance is limited to aligned bars from 09:15 through 15:25, producing bar ends through 15:30. No daylight-saving conversion is involved.

All 25 accepted symbol-sessions have:

- 75 expected and 75 actual regular-session bars
- zero missing bars
- zero duplicates
- zero out-of-order rows
- zero invalid OHLC rows
- zero negative-volume rows
- zero accepted off-session rows
- 100% regular-session coverage

The 40 provider rows outside the regular-session boundary are reported separately rather than silently discarded. `REAL_INTRADAY_DATA_QUALITY_RESULT = CLEAN` applies to the accepted canonical sessions; the overall pilot is limited because the source semantics and retention terms still have documented uncertainty.

## Derived bars

The accepted 5-minute data produced 950 10-minute rows and 625 15-minute rows. Each 15-minute bar has three source bars. Each normal session produces 38 10-minute bars: 37 complete two-source-bar intervals and one explicit final partial bar containing the single 15:25–15:30 source bar. No synthetic full 10-minute close bar is created.

## Daily reconciliation

Each accepted session was aggregated and compared with the existing official NSE security bhavdata reference. Tolerances are ₹0.05 absolute or 0.50% relative for price and 2% for volume. The relative tolerance exists because the 15:25–15:30 regular bar close and the official exchange closing-price process are not identical concepts.

Across all 25 sessions, opens, highs, and lows matched exactly. Closing differences stayed within 0.4432%, and volume differences stayed within 0.5683%. All sessions are `MINOR_SOURCE_DIFFERENCE`; none is a material price or volume mismatch. `REAL_DAILY_INTRADAY_RECONCILIATION_RESULT = CLEAN_WITH_SOURCE_DIFFERENCES`.

## Opening range and VWAP

The pilot calculated 5-, 10-, 15-, and 30-minute opening ranges for every usable session, producing 100 causal opening-range records. Each record includes its completion time, high, low, midpoint, range percentage, and source-bar count.

`SESSION_VWAP_FROM_5M_V1` produced one cumulative internal VWAP point for every accepted bar, using typical price `(high + low + close) / 3` multiplied by bar volume. Volume was available throughout. Groww does not publish a comparable VWAP in this endpoint, so the result is `NO_PROVIDER_COMPARISON`; internal VWAP is not overwritten.

## First-touch reconstruction and structural confirmation

Five frozen development opportunities were passed through `INTRADAY_FIRST_TOUCH_ENGINE_V1`. Three agreed with the frozen daily classification, ALKYLAMINE refined a daily stop-first event into a gap-through-stop event, and TITAN remained insufficient for a full four-session comparison because the bounded pilot ends on 7 January while its fourth holding session is 10 January. There were no daily ambiguous cases and no same-5-minute-bar ambiguities. This tiny sample is not extrapolated, and no frozen outcome was changed.

For all five T+1 sessions, completed first 5-, 10-, and 15-minute closes, opening-range state, internal VWAP at 5/10/15 minutes, and cumulative volume were structurally available. No entry confirmation rule or pass/fail criterion was defined.

The execution event carries an execution reference compatible with the existing slippage and India equity cost-model interface. This is an architecture contract only; the portfolio was not rerun.

## Reliability and scalability

All seven preregistered requests succeeded with zero retries, rate-limit responses, authentication failures, and data-unavailable responses. `PROVIDER_PILOT_RELIABILITY_RESULT = CLEAN` for this bounded run.

At the documented 30-day native-5-minute window, a rough five-calendar-year Nifty 500 plan requires about 61 windows per symbol, or 30,500 historical requests. At the conservative one-request-per-second planning throttle, the request time alone is about 8.47 hours; a practical range is 10–16 hours plus retry, integrity, and reconciliation work. The existing architecture estimates about 46.9 million rows and 4–10 GiB with metadata. Provider price is unknown. `FULL_INTRADAY_INGESTION_FEASIBILITY = FEASIBLE_WITH_BATCHING`, but no bulk ingestion is authorized.

Any future full-history request requires a separate command and explicit approval after terms, retention, historical sufficiency, quality, reconciliation, request/storage, provider cost, and holdout governance have been reviewed.

## Safety and known limitations

- Validation is SEALED; validation run count is zero and no validation-period bar was requested.
- Strategy V1, frozen scores/outcomes/backtest, diagnostics, cost configuration, temporal manifest, and synthetic intraday baselines remained hash-identical.
- No Strategy V2 artifact, rule, result, or signal was created.
- No order function was exposed or called.
- No remote migration or Supabase write occurred.
- No raw or derived provider data is tracked in Git.
- Exact provider timestamp prose, adjustment semantics, data retention, redistribution, official historical-endpoint rate, and provider cost remain unresolved.
- Current instrument-master mappings are not point-in-time validity evidence.
- The pilot covers only five symbols and five sessions and supports no statistical performance conclusion.

Stop after Step 02.14 / Command 04. The next permitted action is review of this bounded pilot; full-history ingestion remains a separate authorization gate.
