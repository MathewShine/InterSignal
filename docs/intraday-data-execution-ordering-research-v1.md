# Intraday Data and Execution-Ordering Research V1

## Purpose and boundary

`INTRADAY_RESEARCH_ARCHITECTURE_V1` provides the data, quality, feature, and causal-ordering contracts needed for a later, separately authorized intraday study. Its canonical profile is `NSE_CASH_INTRADAY_5M_V1`; its event-ordering contract is `EXECUTION_ORDERING_V1`.

This command is architecture plus a small synthetic test validation. It does not define Strategy V2, alter Strategy V1, evaluate the sealed validation holdout, produce trade signals, call a broker, place orders, migrate a database, or persist anything to Supabase. No real intraday dataset was locally available with auditable provenance, so `INTRADAY_DATA_QUALITY_RESULT` is `NO_REAL_DATA_AVAILABLE`. The fictional `ALPHA` rows are labeled `SYNTHETIC_TEST_FIXTURE` everywhere and are not empirical evidence.

## Canonical interval and schema

Five-minute bars are the only stored canonical V1 interval. They match the original early-confirmation research intent, support causal intraday ordering, and can be aggregated without retaining redundant provider 10-minute or 15-minute feeds. One-minute data is neither required nor ingested.

Every normalized bar contains:

- instrument ID, symbol, ISIN, exchange, trading date, interval, bar start, and bar end;
- open, high, low, close, and volume;
- source provider, source interval, source timestamp, ingestion timestamp, and normalization version;
- session ID and one-based session sequence;
- partial/missing-context indicators, quality status, and multiple quality flags;
- source-bar count and separately labeled provider VWAP;
- corporate-action reference metadata without an automatic price transformation.

All canonical and event timestamps are timezone-aware. Exchange-local normalization uses `Asia/Kolkata`. A file may contain naive timestamps only when its capability manifest explicitly declares them to be exchange-local; the stored result is always aware.

## NSE session and calendar semantics

`NSE_CASH_SESSION_V1` defines a regular cash session from 09:15 through 15:30 IST. With half-open bars—09:15–09:20 through 15:25–15:30—the exact expectation is 75 five-minute bars. Seventy-four or 76 is never silently classified as complete.

The calendar consumes an explicit, sourced trading-session universe. It does not infer sessions from Monday through Friday. Holidays therefore remain absent unless the source calendar declares a session. Special or shortened sessions can be registered only with timezone-aware open/close timestamps, a session type, and an auditable source; the architecture does not invent them. Sequence numbers are derived from the session open and are stable from 1 through N.

## Quality and completeness

`INTRADAY_BAR_QUALITY_V1` supports `COMPLETE`, `PARTIAL_SESSION`, `MISSING_BARS`, `DUPLICATE_BARS`, `OUT_OF_ORDER`, `OHLC_INVALID`, `NEGATIVE_VOLUME`, `SESSION_MISMATCH`, `SOURCE_GAP`, and `UNUSABLE`. A session can have multiple flags.

Validation enforces:

- high at or above open and close, low at or below open and close, and high at or above low;
- non-negative volume when present;
- end after start, exact five-minute duration, and five-minute clock alignment;
- no duplicate start timestamps;
- membership in the declared session and a report of every absent expected timestamp.

Per symbol/date reports include expected count, actual count, missing count, duplicate count, coverage percentage, and strict/lenient usability. The default causal policy is strict: any missing bar makes a session unavailable for strategy evaluation. Lenient mode can retain missing-bar sessions for limited data-quality work but never disguises the gap. Duplicate, out-of-order, invalid OHLC, negative-volume, or session-mismatch inputs are unusable.

## Lineage, storage, and hashing

Lineage is append-only:

`SOURCE_RAW -> NORMALIZED_5M -> DERIVED_10M / DERIVED_15M -> INTRADAY_FEATURES -> EXECUTION_EVENTS`

Raw source payloads are not overwritten. Bulk paths are reserved under:

- `data/raw/intraday/<provider>/`
- `data/normalized/intraday/5m/`
- `data/derived/intraday/10m/`
- `data/derived/intraday/15m/`
- `data/research/intraday/v1/`

Those paths and machine reports are ignored by Git. Canonical rows are sorted by exchange, symbol, start timestamp, interval, and provider before SHA-256 hashing. Volatile ingestion time is retained for audit but excluded from the content projection, making normalized 5m, derived 10m, and derived 15m hashes reproducible for identical source content.

Parquet is the recommended bulk format because columnar compression, predicate pushdown, and batch processing fit millions of bars. CSV.gz remains acceptable for tiny pilots and reports. No heavy service or database dependency is introduced. A future file layout should partition by exchange/interval/year/month, retain symbol and trading date as query columns, and sort within partitions by symbol then bar start. This supports symbol-plus-range, date-plus-universe, and whole-session access without creating tiny per-symbol files.

If database persistence is later authorized, a reasonable design is range partitioning on trading date with an `instrument_id, bar_start` index. This is documentation only: Command 03 adds no migration and writes no bulk history to Supabase.

## Deterministic derived bars

Two source bars form 10-minute bars; three form 15-minute bars. Open comes from the first source row, high is the maximum, low the minimum, close comes from the last, and volume is summed. Start/end, source count, and the union of source quality flags are retained. Aggregation only consumes chronologically available source bars and never reads a later group.

A 375-minute regular session is not evenly divisible by ten. V1 therefore retains 38 10-minute records: 37 complete two-source-bar groups plus an explicit final one-source-bar partial group from 15:25 to 15:30. It is never mislabeled as a full 10-minute candle. Fifteen-minute aggregation yields 25 complete groups. Thirty- and 60-minute source datasets remain potential future extensions, not V1 requirements.

## Provider abstraction and ingestion audit

`IntradayDataProvider` separates fetching, normalization, metadata, supported intervals/history, and session validation. `FILE_OR_LOCAL_FIXTURE_PROVIDER` is the only concrete Command 03 provider. It performs deterministic local CSV reads and no network access. A generic disabled external-provider placeholder demonstrates the boundary without claiming Groww or Zerodha capabilities or using credentials.

`IntradayProviderCapabilityManifest` records provider, exchange, instrument type, intervals, history bounds, known rate limits, adjustment status, volume/VWAP availability, timestamp semantics, limitations, and data classification. Unknown external facts must remain unknown.

`IntradayIngestionRequest` fixes instrument, requested dates, canonical interval, provider, purpose, research window, and request ID. `IntradayIngestionAudit` records requested and received bounds, row count, missing sessions, aware ingestion time, raw hash, normalization hash, and status. Request and audit snapshots have deterministic hashes.

The local two-row `ALPHA` fixture is a provider contract smoke test only. It is structurally inspected and reported as a 73-bar-short synthetic session. It is not presented as local real data and is not used to make a strategy claim.

## Corporate actions and daily reconciliation

V1 retains raw observed intraday prices and corporate-action safety/reference metadata. It does not copy or apply daily structural-adjustment factors. Any later adjusted-intraday transform needs its own methodology, validation, and version.

Optional reconciliation aggregates session open, high, low, close, and total volume against a canonical daily bar. It reports every difference and uses configurable price and volume tolerances. Price agreement with only a volume-source difference becomes `CLEAN_WITH_SOURCE_DIFFERENCES`; material price divergence becomes `MATERIAL_MISMATCH`. Exact equality is not assumed across vendors. Reconciliation results are `CLEAN`, `CLEAN_WITH_SOURCE_DIFFERENCES`, `MATERIAL_MISMATCH`, or `INCONCLUSIVE`.

Synthetic input is always `INCONCLUSIVE`, even when constructed from a matching daily row. Real or provenance-backed local-real data was unavailable, so Command 03 does not claim a daily reconciliation result.

## Opening range

`OPENING_RANGE_V1` supports the first 5, 10, 15, and 30 minutes. It stores high, low, midpoint, percentage range, completion timestamp, source count, and optionally range divided by a causally available daily ATR. A range is computed only when every required completed 5-minute bar is present.

Post-completion bars can emit `OR_BREAK_UP`, `OR_BREAK_DOWN`, and `OR_RECLAIM`. These are descriptive events, not entry rules. The synthetic pilot recalculates all four windows from their exact source subsets.

## Session VWAP

`SESSION_VWAP_FROM_5M_V1` uses:

`typical price = (high + low + close) / 3`

`session VWAP = cumulative(typical price * volume) / cumulative(volume)`

Each point stores VWAP, cumulative volume, completed-bar timestamp, methodology, and quality flags. Provider VWAP remains a separate field and is never blended with calculated VWAP. Missing volume, zero cumulative volume, or incomplete session coverage is flagged; zero-volume prefixes return no value rather than a fabricated number. The pilot independently recalculates the first bar, first three bars, and full session.

The schema is ready for later opening volume, cumulative volume, time-of-day relative volume, and first-15-minute volume share, but Command 03 does not introduce a normalization study.

## Causal confirmations and price semantics

Confirmation windows support 5, 10, and 15 minutes. A feature available at time X may consume only bars whose `bar_end <= X`; partial future bars are excluded. The architecture can later query confirmation close, opening-range state, VWAP relation, and volume confirmation, but it makes no strategy decision.

Research must preserve separate concepts for the daily decision reference close, next-session open, confirmation close, trigger price, assumed execution reference, and slippage-adjusted price. `ExecutionPriceModel` provides `BAR_CLOSE_CONFIRMATION`, `STOP_TRIGGER_PRICE`, `TARGET_TRIGGER_PRICE`, `NEXT_BAR_OPEN`, and `FIXED_BPS_SLIPPAGE_OVER_REFERENCE`. Its fixed-bps mode delegates the monetary calculation to the existing `SLIPPAGE_MODEL_V1` implementation. Ordering chooses the reference event; the frozen cost/slippage layer owns economics.

## Execution events and first-touch ordering

`ExecutionEvent` stores aware timestamp, event type, symbol/date, sequence, reference price, trigger price, observed bar, source, causal flag, and metadata. Supported types include session/bar open, high/low touch, bar close, opening-range completion and break/reclaim events, entry confirmation/trigger/execution, stop/target trigger, time exit, and session close.

`INTRADAY_FIRST_TOUCH_ENGINE_V1` evaluates long-position bars chronologically after the actual entry boundary and across later sessions through the configured maximum date. Earlier bar timestamp always wins. Bars strictly before entry are excluded. When entry falls inside a bar, V1 discards that containing bar because its post-entry path is unknowable; normal research entry should occur at a completed-bar boundary. Optional time exit can reference the configured final-session close.

Within one OHLC bar, high-versus-low tick order is unknown. If both stop and target are touched, the primary state is always `INTRABAR_SEQUENCE_AMBIGUOUS`. It is never silently resolved favorably. An explicitly selected research policy can separately resolve the assumption as `CONSERVATIVE_STOP_FIRST`, `OPTIMISTIC_TARGET_FIRST`, or `AMBIGUOUS_EXCLUDED`; the frozen daily backtest is not changed.

For a long position opening below its stop on a later session, the engine records `GAP_THROUGH_STOP` and uses the session open as the execution reference—not the stale stop. An open above target records `GAP_THROUGH_TARGET` and uses the session open unless a future strategy explicitly defines limit-fill semantics. Stop market, stop limit, limit target, and market exit are distinct order types. `ASSUMED_FILLED_ON_TOUCH` is an explicit research assumption, not a fill guarantee; queue position and liquidity remain unmodeled.

## Temporal governance

All intraday research integrates with `TEMPORAL_RESEARCH_HARNESS_V1` and `TEMPORAL_VALIDATION_PROTOCOL_V1`. Development-window structural work is allowed. Validation remains `SEALED`. A validation-date pilot could perform data-quality inspection only; it could not expose outcome or performance fields. Command 03 uses development-era synthetic dates for its architecture cases and performs no strategy performance calculation anywhere.

## Pilot coverage and limitations

Four synthetic sessions test one complete session, one missing-bar session, one duplicate session, and one invalid-OHLC session. Additional deterministic cases cover opening gaps up/down, stop first, target first, same-bar ambiguity, gap-through stop/target, first-5-minute and first-15-minute confirmation, VWAP, entry exclusion, and multi-session sequencing. Manual case records retain entry boundary, stop, target, touch timestamps, ambiguity/gap status, and exit event.

This validates code paths, not market representativeness. With no broad intraday history, daily OHLC still cannot resolve:

- same-day stop/target ordering;
- exact confirmation timing;
- opening-range behavior;
- VWAP relation;
- intraday retests;
- actual stop slippage;
- target-fill realism.

The synthetic same-bar ambiguity rate is reported only over five constructed first-touch cases and must not be extrapolated.

## Scale estimate and research gate

Nifty 500 × 75 bars × about 250 sessions × five years is approximately 46,875,000 normalized rows. At an assumed 64–160 compressed bytes per row, raw columnar payload is roughly 2.8–7.0 GiB; a practical planning envelope including metadata, partitions, and indexes is 4–10 GiB. This is an estimate, not a download.

Full-history ingestion requires separate authorization after provider capability, history availability, rate limits, licensing/terms, cost, and storage are reviewed. The processing design favors canonical ordering, grouped/batched aggregation, and columnar files so it can extend to millions of bars. Command 03 performs no Nifty 500 ingestion.

## Result

The architecture classification is `READY_FOR_PILOT_INGESTION`: it is ready for a small, licensed, provenance-backed real-data pilot, not yet broad controlled research. Execution ordering is `CLEAN_WITH_INTRABAR_AMBIGUITY`, reflecting the irreducible OHLC same-bar limitation. Data quality is `NO_REAL_DATA_AVAILABLE`. No result named or implying live readiness is used.
