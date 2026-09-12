# Bounded DEVELOPMENT intraday ingestion V1

`DEVELOPMENT_INTRADAY_INGESTION_V1` builds a private, local, resumable Groww 5-minute dataset for the frozen 2022-01-01 through 2024-12-31 DEVELOPMENT window. It is data infrastructure only: it emits no signal, places no order, changes no strategy rule, performs no portfolio rerun, and does not expose or ingest the sealed validation period.

## Bounded selection

The source universe is the 2,068 mechanically valid frozen DEVELOPMENT opportunities. Symbols are ranked by opportunity count, frozen admitted-trade count, prior same-bar ambiguity/execution relevance, breadth across frozen score/setup/reward-risk/candidate categories, exact instrument mapping availability, then symbol as a deterministic tie-break. Realized return, P&L, win rate, target rate, and every other performance field are excluded from selection.

The target is 80% source-opportunity coverage, subordinate to hard caps of 100 symbols, 5,000,000 normalized 5-minute rows, 5,000 provider requests, 2 GiB raw storage, and three estimated wall-clock hours. The plan stops at the first target-achieving mapped prefix or 100 symbols, whichever comes first. It must still aim for at least 20 symbols and 500 unique symbol-sessions.

Each selected opportunity contributes its decision session and the actual frozen T+1 through four-session holding dates, never calendar-day guesses. Dates are deduplicated by symbol, and sorted required sessions are grouped into non-overlapping request windows of at most 30 calendar days. Collateral regular-session rows returned inside a window remain in immutable raw provenance but are not admitted to canonical storage.

## Scope freeze and restart safety

Planning uses the cached official Groww SDK instrument master, before network access. Exact symbol matches, exchange token, ISIN, exchange, mapping status, master hash, required sessions, request windows, and estimates are frozen in `data/research/intraday/v1/development_bounded/manifests/development_intraday_scope_manifest_v1.json`. The deterministic request plan is frozen beside it. Both hashes exclude only their creation timestamp and own hash field.

Current token and matching ISIN strengthen mapping, but the current master does not prove historical token validity. Every selected mapping therefore records `POINT_IN_TIME_INSTRUMENT_VALIDITY = UNVERIFIED`; similarly named substitutes are forbidden.

The checkpoint persists after every state transition and uses `PENDING`, `IN_PROGRESS`, `COMPLETE`, `FAILED_RETRYABLE`, `FAILED_FINAL`, and `SKIPPED`. `RESUME` requires the same scope and plan hashes, skips complete requests, and recovers an immutable raw payload written immediately before an interrupted checkpoint. `REPLAY_FAILED` targets only retryable failed request IDs. Raw files use exclusive creation and are never overwritten.

Supported modes are:

- `PLAN_ONLY`: freeze or verify plan and checkpoint without network access.
- `INGEST`: execute a fresh all-pending frozen plan.
- `RESUME`: continue pending, interrupted, or retryable requests from the same hashes.
- `VERIFY`: perform no requests; verify raw hashes and rebuild canonical artifacts.
- `REPLAY_FAILED`: retry only checkpoint rows classified retryable.

The runner is `backend/scripts/run_development_intraday_ingestion.py --mode <MODE>`.

## Provenance, storage, and quality

Accepted responses are stored under `data/raw/intraday/groww/development_bounded_v1/` for private local research only. Raw, normalized, derived, and research manifests are ignored by Git and must not be redistributed. Groww retention and redistribution rights remain incompletely documented, so the prior `USABLE_WITH_RESTRICTIONS` status remains in force.

Only regular 09:15–15:30 Asia/Kolkata bars for frozen required sessions enter `NSE_CASH_INTRADAY_5M_V1`. Canonical storage is deterministic gzip CSV partitioned by year and symbol. Ten- and fifteen-minute bars are derived only from accepted 5-minute rows. Each partition receives a file SHA-256; dataset hashes are SHA-256 over the canonical sorted partition manifest. Raw index, session index, scope, plan, and opportunity coverage have separate deterministic hashes.

Every required symbol-session is classified by `REAL_INTRADAY_SESSION_USABILITY_V1`. Strict sessions require exactly 75 aligned bars, unique ordered timestamps, valid OHLC, nonnegative volume, correct timezone, and no gaps. Off-session provider rows remain raw and are counted. Every available session is reconciled to the frozen NSE daily reference using the already-approved Command 04 price and volume tolerances. Corporate-action research eligibility is joined as `SAFE`, `CAUTION`, or `UNSAFE_STRUCTURAL`; prices are never automatically adjusted.

The coverage map records decision and holding sessions, availability, strict usability, full four-session reconstructability, confirmation-field availability, and corporate-action safety for all 2,068 opportunities. The admitted-trade map is structural only and is built from the existing frozen trade ledger; it neither reads performance for selection nor reruns the portfolio. Opening ranges, session VWAP, first 5/10/15-minute closes, and cumulative-volume availability are checked mechanically. No mass first-touch or outcome research is performed.

## Validation and authorization gate

All provider request dates are rejected unless they are inside the frozen DEVELOPMENT window and no window may end after 2024-12-31. Validation remains `SEALED` with run count zero. No 2025+ bar is fetched, normalized, derived, or reported as strategy evidence.

Full-history scale-up is not authorized by this command. Reliability, strict usability, reconciliation, achieved coverage, storage burden, and licensing uncertainty produce a recommendation only. Any wider universe, new scope, validation access, mass first-touch study, or strategy experiment requires a separate explicit authorization and version.
