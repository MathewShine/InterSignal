# Development Intraday Ingestion Resume V1

`DEVELOPMENT_INTRADAY_INGESTION_RESUME_V1` is the Command 05B continuation of the frozen Command 05 DEVELOPMENT dataset. Its profile is `NSE_CASH_5M_DEVELOPMENT_BOUNDED_RESUME_V1`. It does not define a new universe, request plan, normalization format, or strategy experiment.

## Frozen scope

The DEVELOPMENT interval remains 2022-01-01 through 2024-12-31. Validation remains `SEALED` with run count zero. The immutable scope contains 2,068 opportunities, 100 selected symbols, 1,118 selected-symbol opportunities, 4,829 required symbol-sessions, 705 historical requests, and an estimated 362,175 normalized rows. The exact scope hash is `dcf4cc8587c923fd08e6299f472cd8f37add3baae54498351eb53fe76da75fe3`; the exact request-plan hash is `cd871adf88bc571339b0c3ca7efcb066d88ab8b63ceae5d0804a411fd8e7dfaf`.

The first Command 05B run requires the audited checkpoint state of 164 `COMPLETE`, one `FAILED_RETRYABLE`, 540 `PENDING`, and zero `FAILED_FINAL` requests. The retryable request is `DEV-INTRADAY-C05-0165-CHOLAFIN-20230914`. All 164 complete raw payloads are verified before provider access. A mismatch in either frozen hash, a validation date, a raw hash, a request identity, or the request-ID set stops the run before historical retrieval.

## Transport V1.1

Every Command 05B historical request uses `GROWW_RETRIEVAL_TRANSPORT_V1_1`: a 10-second connect timeout, 20-second read-inactivity timeout, 30-second controller wall-clock bound, and at most two retries after the initial attempt. Requests remain throttled to one attempt per second. Provider `Retry-After` is respected when supplied. Authentication failure stops the run, and three consecutive logical requests that exhaust their timeout retry budget open the request-level circuit breaker. The whole resume has a fresh three-hour operational cap.

The legacy unbounded path is rejected by a runtime transport-version/configuration guard. Each attempt has a request-local generation ID composed from request ID, retry number, and generation. A timed-out generation is invalidated under a lock. The SDK worker can finish later because Python cannot forcibly terminate its thread, but it has no raw-write capability; a late result is discarded by the generation guard. Only the active successful generation can claim the single raw commit.

## Checkpoint and raw safety

Before retrieval, Command 05B writes an immutable checkpoint snapshot and pre-resume manifest under `data/research/intraday/v1/development_bounded/resume_05b/`. The primary checkpoint advances atomically after attempt transitions and logical request terminal states. A successful payload is written once with exclusive creation, hashed, added to the resume raw index, and only then marked `COMPLETE`. Existing complete files are validated and reused; they are never refetched or overwritten.

Progress state is persisted every 25 completions or ten minutes, in addition to per-attempt/per-request checkpoint writes. The original 2 GiB raw cap and five-million normalized-row cap remain active. Credentials come only from ignored configuration, and tokens or authorization headers are never included in reports.

## Dataset merge and interpretation

Only newly accepted raw request IDs are normalized with the unchanged `NSE_CASH_INTRADAY_5M_V1` semantics. Existing canonical 5-minute partitions are loaded and merged by symbol, instrument, bar start, interval, and provider version. Identical duplicates are suppressed and conflicting duplicates fail. The 10-minute and 15-minute datasets are rebuilt only from the merged canonical 5-minute layer, preserving the Command 03 final partial 10-minute behavior. Whole-dataset session quality, corporate-action safety, reconciliation, opportunity coverage, trade structural coverage, and confirmation availability are then recalculated.

Structural bar/session quality is reported separately from cross-source daily reconciliation. Command 05's price tolerance, volume tolerance, and legacy material mismatch definition do not change. Command 05A established that the first 98 price mismatches were benign source semantics rather than normalization, timestamp, rounding, or corruption defects. Command 05B retains the legacy mismatch count and adds an origin-aware view: `EXPLAINED_CLOSE_AUCTION_OR_SOURCE_SEMANTICS` versus unexplained material differences. Later excluded post-close observations and NSE `LAST_PRICE` are diagnostic evidence only; off-session rows remain excluded from canonical regular-session data.

Opportunity coverage always reports two denominators: all 2,068 DEVELOPMENT opportunities and the 1,118 opportunities in the frozen selected-symbol scope. The latter makes clear that the current scope's maximum all-DEVELOPMENT coverage is approximately 54.06%, so 80% is not achievable without a separately authorized scope expansion. Existing 478 admitted trades receive structural data-coverage reporting only. No outcomes or portfolio results are recomputed.

## Governance

The original Command 05 `BOUNDED_INTRADAY_INGESTION_RESULT = FAIL_DATA_QUALITY` remains unchanged in its original artifacts. Command 05B records separate transport, resume, dataset, and full-history recommendation classifications. Even a clean completion can only recommend a separate authorization for wider history; it cannot initiate it.

Historical instrument identity remains `CURRENT_IDENTITY_ONLY`: 96 mappings are ISIN-verified, all 100 use current tokens, and no token has independent point-in-time verification. Groww data remains research-only and usable with licensing restrictions; this command grants no retention or redistribution rights.

Command 05B performs no Strategy V2 research, entry/VWAP comparison, mass first-touch reclassification, portfolio rerun, validation access, live signal, broker order call, remote migration, or Supabase write. `VERIFY` performs zero provider requests and reproduces dataset hashes. A second `RESUME` after all logical requests are terminal performs zero historical fetches.
