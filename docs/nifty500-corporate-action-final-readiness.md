# Nifty 500 Corporate Action Final Readiness

Current phase: Step 02.3E-Fix / Command 02 - final Nifty 500 corporate-action readiness

## Final Status

- Corporate-action readiness: READY_WITH_EXCLUSIONS
- Feature Engine may safely start: True
- Historical Nifty 500 membership remains PARTIAL_HISTORY and must travel as separate metadata.

## INFIBEAM

- Classification: UNRESOLVED_DISCONTINUITY
- Handling: EXCLUDED
- Adjusted: False
- Notes: INFIBEAM 2022-03-14 raw close gap was -51.9553%; official NSE corporate-action and announcement probes found no matching event, so no factor was created and a finite exclusion is used.

## Original NOT_READY Resolution

- Original NOT_READY symbols: 86
- Converted to READY_WITH_EXCLUSIONS: 86
- Still NOT_READY: 0
- Still NOT_READY symbols: None
- FULLY_READY: 611
- READY_WITH_EXCLUSIONS: 95
- NOT_READY: 0

## Root Causes

- MULTIPLE_COMPLEX_ACTIONS: 5
- RIGHTS: 16
- SPECIAL_DIVIDEND: 64
- UNRESOLVED_DISCONTINUITY: 1

## Event Handling

- Rights symbols: 17 - Finite exclusion windows; diagnostic TERP is deferred and not applied to PRICE_ADJUSTED_STRUCTURAL_V1.
- Special-dividend symbols: 69 - Finite exclusion windows; no total-return or structural price factor was created.
- Merger/demerger symbols: 4 - CONTINUITY_BREAK retained with finite exclusion windows.

## Exclusion Policy

- Version: CORPORATE_ACTION_EXCLUSIONS_V1
- Exclusion intervals: 135
- Lookback contamination is supported through `is_research_eligible(symbol, as_of_date, lookback_sessions)`.

## Observation Impact

- Total historical Nifty 500 EQ observations: 597924
- Usable at 0-session lookback: 597141 (99.8690%)
- Excluded at 0-session lookback: 783
- Usable at 5-session lookback: 596501 (99.7620%)
- Excluded at 5-session lookback: 1423
- Usable at 20-session lookback: 594594 (99.4431%)
- Excluded at 20-session lookback: 3330
- Usable at 60-session lookback: 589838 (98.6477%)
- Excluded at 60-session lookback: 8086

## Integrity And Safety

- Raw NSE unchanged: True
- Normalized RAW unchanged: True
- Adjusted dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy calculations were executed.

## Known Limitations

- INFIBEAM remains without an official event match; it is bounded by exclusion, not adjusted.
- Rights TERP diagnostics are not promoted into PRICE_ADJUSTED_STRUCTURAL_V1.
- Special dividends remain exclusion metadata, not total-return adjustment.
- Complex restructurings retain continuity-break treatment.
