# Groww intraday reconciliation and retrieval audit V1

## Scope and governance

`GROWW_INTRADAY_ROOT_CAUSE_AUDIT_V1` / `GROWW_RECONCILIATION_AND_RETRIEVAL_AUDIT_V1` is the Step 02.14 / Command 05A root-cause audit. It consumes only the retained Command 05 development artifacts, frozen NSE daily references, local corporate-action data, the cached instrument master, request metrics, and installed SDK source. It made zero provider requests and did not resume any of the 540 pending requests.

The 2022-01-01 through 2024-12-31 development window remains frozen. Validation remains `SEALED`, run count 0, with no holdout performance exposed. No strategy metric, Strategy V2 artifact, portfolio rerun, live signal, live order, broker order call, database migration, or Supabase write was produced.

The frozen reconciliation policy is unchanged: ₹0.05 absolute and 0.50% relative price thresholds, 2% volume tolerance, and a 5% command-level failure threshold. This audit explains failures; it does not redefine them away.

## Reconciliation population

The audit reproduced the exact source gate:

- 1,170 daily-comparable sessions
- 1,072 `MATCH_OR_MINOR` sessions
- 98 material price mismatches (8.3760683761%)
- 6 additional material volume-only mismatches

The 98 material price mismatches decompose into 94 `CLOSE_ONLY` and 4 `OPEN_ONLY`. There are no high-only, low-only, multi-price-field, price-and-volume, or unknown cases.

Material maximum-field differences have median 0.6763237012%, p75 0.9166528733%, p90 1.1189018962%, p95 1.2307708722%, p99 1.7505302351%, and maximum 2.1222513617%. Counts by frozen descriptive band are 61 at 0.50–0.75%, 20 at 0.75–1.00%, 16 at 1–2%, 1 at 2–5%, and 0 above 5%.

## Source and field findings

The frozen daily source is the official NSE `sec_bhavdata_full` security bhavcopy. It is a raw, unadjusted trading-date file. The audit reads `OPEN_PRICE`, `HIGH_PRICE`, `LOW_PRICE`, `CLOSE_PRICE`, `LAST_PRICE`, `AVG_PRICE`, and `TTL_TRD_QNTY`. NSE `CLOSE_PRICE` and the final traded price are distinct fields; the intraday dataset's last regular 5-minute trade should therefore not be assumed to equal the daily closing-price process.

Raw Groww regular-session aggregation and the persisted normalized aggregation agree in all 1,170 comparable sessions. There are zero raw-versus-normalized aggregate differences, duplicate raw timestamps, scale errors, decimal conversion errors, rounding effects, or proven normalization defects. `GROWW_INTRADAY_NORMALIZATION_V1_1` was not created.

Of the 94 close-only failures, the final canonical Groww close is closer to NSE `LAST_PRICE` than to `CLOSE_PRICE` in 95 of all 98 material-price sessions and exactly equals `LAST_PRICE` in 57. Eighty-eight material-price sessions contain a later excluded post-close observation matching NSE `CLOSE_PRICE` within ₹0.05; 89 become non-material when the final off-session observation is considered diagnostically. This is evidence of a separate provider final-close publication, not permission to include post-close rows in the canonical regular session.

Accordingly, mismatch origins are classified as 89 `SESSION_FILTERING_EFFECT` and 9 `PROVIDER_VS_DAILY_SOURCE`, with zero normalization, timestamp-alignment, rounding, corporate-action, or unknown origins. All 98 are `EXPLAINED_BENIGN_SOURCE_DIFFERENCE`; none are classified as data corruption or a proven normalization defect. The conservative results are:

- `CROSS_SOURCE_RECONCILIATION_RESULT = SOURCE_DEFINITION_DIFFERENCE`
- `RECONCILIATION_ROOT_CAUSE_RESULT = BENIGN_SOURCE_SEMANTICS`

Command 05 still fails its frozen threshold. The audit does not retrospectively upgrade the accepted partial dataset.

## Symbol, year, date, and corporate-action concentration

The top mismatch symbols are 360ONE (11/37), ANGELONE (8/32), BDL (8/63), AMBUJACEM (7/45), APLAPOLLO (7/39), CGPOWER (7/50), CANFINHOME (6/73), and BALRAMCHIN (5/39). The top five contain 41.8367% of mismatches, so the issue is distributed rather than isolated to a small symbol set.

Yearly counts and rates are:

| Year | Comparable | Mismatches | Rate |
| --- | ---: | ---: | ---: |
| 2022 | 411 | 33 | 8.0291970803% |
| 2023 | 460 | 30 | 6.5217391304% |
| 2024 | 299 | 35 | 11.7056856187% |

No single date dominates. The largest date clusters are three cases each on 2024-06-13 and 2022-08-19; the largest monthly cluster is nine cases in 2022-08. These are descriptive concentrations, not causal expiry or special-session findings.

The existing corporate-action layer finds 1 same-day, 1 within ±1 trading day, and 3 within ±5 trading days. No mismatch falls in a known structural exclusion and none is within five trading days of an adjustment-factor transition. Corporate actions do not explain the population, and no intraday price was adjusted.

## Off-session and timestamp semantics

The exact 5,591 excluded raw rows comprise:

- 35 before 09:15
- 1,840 at 15:30
- 3,716 after 15:30
- 0 other

The largest timestamp groups are 15:40 (2,988), 15:30 (1,840), 16:00 (449), and 15:45 (114). Every 15:30 row is a single-price OHLC row, with median volume 67. None of the 15:30 observations in the material-mismatch population matches NSE `CLOSE_PRICE` within ₹0.05. The later post-close observations usually do. The 15:30 row is therefore supported as a sparse trade observation, not as a provider daily-summary close.

Groww's 09:15-aligned rows, complete 75-bar regular sessions, and exact daily high/low reconciliation support bar-start semantics. Reinterpreting timestamps as bar ends would remove the observed 09:15 opening interval, include the sparse 15:30 observation, produce material open differences in 550 of 1,170 sessions, and increase the material-price population to 647. The canonical interpretation is unchanged:

`GROWW_TIMESTAMP_SEMANTICS_RESULT = BAR_START_SUPPORTED`

## Volume findings

The six material volume mismatches are separate from the 98 price mismatches. Reconciliation to raw rows confirms no normalization arithmetic defect. Including retained off-session volume brings one case within the 2% tolerance; five remain cross-source/full-session definition differences. No missing-bar case explains the six.

## Retrieval stalls and SDK path

The audit analyzed all 165 recorded historical attempts. Median latency is 935.637 ms, p90 1,189.6528 ms, p95 2,054.2026 ms, p99 2,941,141.64488 ms, and maximum 13,035,132.066 ms. Three attempts exceed both the predeclared 30-second stall and 120-second extreme-stall thresholds:

- CANFINHOME 2023-04-27 through 2023-05-26: 1,053,763.027 ms, success
- CANFINHOME 2024-08-28 through 2024-09-26: 6,296,481.410 ms, success
- CHAMBLFERT 2022-01-12 through 2022-02-10: 13,035,132.066 ms, transient failure followed by a successful retry

The installed official `growwapi` 1.5.0 path is synchronous `requests.get` to the official `/v1/historical/candles` endpoint. Legacy Command 05 passed `timeout=30`; the SDK forwards this to Requests. That scalar limits connect and read inactivity, but it is not a total response wall-clock deadline. The module-level `requests.get` path also creates no reusable cross-call session, has no pagination for the bulk response, and performs no token refresh inside the historical call.

Recorded normal requests account for 158.338 seconds (0.5154%) of the 30,724.151-second retrieval window. The three stalls account for 20,385.377 seconds (66.3497%). Bounded retry/backoff accounts for 2 seconds and the conservative throttle upper-bound estimate is 15.691 seconds. The remaining 10,162.745 seconds (33.0774%) are retained as unknown/inter-run pause time; they are not falsely attributed to local normalization.

The retrieval findings are:

- `GROWW_TIMEOUT_CONFIGURATION_RESULT = PARTIAL_TIMEOUTS`
- `RETRIEVAL_STALL_ROOT_CAUSE_RESULT = UNBOUNDED_SDK_TIMEOUT`
- `RETRIEVAL_TRANSPORT_RESULT = SDK_WITH_TIMEOUT_WRAPPER`

No live diagnostic probe was needed.

## Transport safety V1.1

`GROWW_RETRIEVAL_TRANSPORT_V1_1` adds a configurable 10-second connect timeout, 20-second read-inactivity timeout, and 30-second controller wall-clock bound. Timeout attempts are logged as `TIMEOUT`, checkpointed as `FAILED_RETRYABLE_TIMEOUT`, limited to two retries after the first failure, and protected by a three-consecutive-timeout circuit breaker. Request timestamps, row counts, sanitized exception classes, and transport version are recorded for future attempts.

The controller timeout uses an isolated daemon worker around the official SDK. Python cannot forcibly terminate a blocked SDK thread, so a late provider response is discarded and can never be accepted into immutable raw data; the daemon also cannot prevent process exit. If a tightly bounded diagnostic later shows this is insufficient, a separately versioned adapter may call the same official REST endpoint with process-level isolation. No unofficial endpoint is authorized.

## Checkpoint and mapping safety

The checkpoint contains 164 `COMPLETE`, 1 `FAILED_RETRYABLE`, and 540 `PENDING` requests. Every complete request has its immutable raw payload; there are zero phantom completes, missing raw payloads, or duplicate completed paths.

The interrupted request is `DEV-INTRADAY-C05-0165-CHOLAFIN-20230914`. It has no raw payload and no normalized data and is correctly `FAILED_RETRYABLE` with `INTERRUPTED_BEFORE_IMMUTABLE_RAW_ACCEPTANCE`. A future resume would not duplicate accepted data.

The scope has 96 ISIN-verified mappings and 100 current token mappings, but zero historically valid token intervals. No archived point-in-time Groww instrument master is available locally. The correct result remains `POINT_IN_TIME_INSTRUMENT_MAPPING_RESULT = CURRENT_IDENTITY_ONLY`.

## Integrity, status, and next gate

The audit hashed 394 retained Command 05 artifacts totaling 46,440,332 bytes before and after execution. Both snapshots have tree hash `bcff32005fb71130c5afc345185b6769d42469d1b5eb85e1173b518dd4e6cff7`. The frozen scope, request plan, checkpoint, raw data, normalized/derived data, and Command 05 reports were not mutated. All strategy, diagnostic, cost, temporal, intraday-architecture, and Command 04 provider-pilot guards remain unchanged.

The partial Command 05 dataset remains rejected under its frozen 5% rule. The existing frozen scope is eligible for a separately authorized resume only after review of transport V1.1; full-history Nifty 500 ingestion remains prohibited.

- `RESUME_SAFETY_RESULT = SAFE_AFTER_FIX`
- `COMMAND_05_DATASET_STATUS_AFTER_AUDIT = ELIGIBLE_FOR_RESUME_AFTER_FIX`
- Full-history recommendation: `NO`

Machine-readable evidence is under `data/reports/groww_intraday_audit_05a_*`. The input-integrity manifest is `data/research/intraday/v1/groww_root_cause_audit_05a/audit_manifest_v1.json`.
