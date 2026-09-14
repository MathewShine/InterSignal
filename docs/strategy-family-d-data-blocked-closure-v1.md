# Strategy Family D data-blocked closure V1

## Decision

Family D (`STRATEGY_FAMILY_D_OPENING_RANGE_V1`) is `PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE`. It is not rejected because the strategy failed. The preregistered control `CONTROL-D-000` and treatment `ORB-D-001` are both `PREREGISTERED_NOT_EVALUATED`: neither is classified as good or bad. Available approved data cannot satisfy the frozen continuity standard required for a fair DEVELOPMENT evaluation, so no performance conclusion may be drawn.

The final evidence status is `PREREGISTERED_NOT_PERFORMANCE_EVALUATED`. Validation is `NOT_ACCESSED` and Strategy V2 is `NOT_CREATED`.

## Frozen continuity finding

The bounded 100-symbol DEVELOPMENT population contains 4,821 target sessions. Exactly 3,752 have all 20 immediately preceding strict opening-volume sessions and 1,069 are incomplete, for 77.826177% coverage (`INSUFFICIENT`). The frozen readiness target remains at least 95%.

Command 02 performed the authorized continuity remediation and preserved all source, quality, and lineage diagnostics. Command 03 then made 211 exact Groww requests; all 211 succeeded on their first attempt, but zero new required sessions were recovered. The remaining 217 defects comprise 105 missing-opening cases, 48 Groww-confirmed unavailable cases, and 64 strict-quality failures. Reconciliation found zero unexplained provider differences.

Groww historical retrieval is reliable for data that is available. The exact retry result demonstrates persistent gaps for this particular Family D continuity contract and must not be generalized into a claim of provider unreliability. There is no approved alternate real NSE historical intraday source, no alternate provider was contacted, and this command authorizes none.

## Why the standard was preserved

`FAMILY_D_CONTINUITY_STANDARD` is `PRESERVED_NOT_RELAXED`. The project did not use sparse prior observations, substitute older sessions, use daily volume, remove problematic sessions post hoc, or lower the 95% readiness target merely to enable a backtest. The opening range, activity definition, threshold, entry, stop, exit, risk, capacity, universe, ranking, and success criteria were unchanged.

## Resume requirements

Family D may resume only after all of the following are true:

1. An approved/licensed compatible historical NSE intraday source exists.
2. The exact required gaps are retrieved and reconciled.
3. Volume semantics are compatible.
4. Exact prior-20 continuity reaches at least 95%.
5. The frozen Family D strategy/config hashes remain intact.

If only better data changes, the existing preregistration may remain valid provided strategy parameters, success criteria, and outcome-independent scope remain unchanged. That work requires a new data-source/remediation version, not a new strategy version. Any change to opening range, activity definition, threshold, entry, stop, exit, risk, capacity, universe, ranking, or success criteria requires a new strategy preregistration.

## Preserved research infrastructure and lesson

The original intraday artifacts, Command 02 extension, Command 03 exact-gap recovery, continuity matrices, request plans, quality diagnostics, and activity structural data remain preserved. Sparse event-oriented intraday ingestion is sufficient for setup/path diagnostics but not for features that require continuous rolling intraday-session history. Future intraday-family planning must identify rolling-history requirements before ingestion scope is frozen.

## Roadmap handoff

Family E is next planned as `FAMILY_E_PULLBACK_RECLAIM_CONTINUATION`. Its high-level concept is a strong prior trend followed by a controlled pullback and reclaim/continuation. It investigates continuation after temporary counter-trend movement rather than immediate strength, which distinguishes it from factor momentum, absolute-trend filters, breakout continuation, and opening-range trading. No Family E parameters were defined and implementation has not started.

Closure manifest: `data/research/strategy_families/family_d/v1/closure/manifest/family_d_closure_manifest_v1.json`
`family_d_closure_hash`: `1628774e5a6032487ac6e15e9beba21cbf52c96389b83aca7d4e87a46e577414`
