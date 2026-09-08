# Nifty 500 Corporate Action Readiness

Current phase: Step 02.3E-Fix / Command 01 - Nifty 500 corporate-action readiness prioritisation

## Recommendation

- Overall readiness: NOT_READY
- Membership survivorship status remains separate and is not upgraded by this report.
- Strategy V1 can use the adjusted price layer only with the eligibility/exclusion metadata produced here.

## Unresolved Suspect Priorities

- Total unresolved suspects: 303
- Nifty 500-relevant unresolved suspects: 2
- P0_CRITICAL: 0
- P1_HIGH: 1
- P2_LOW: 58
- P3_IGNORE_FOR_V1: 244
- P0 resolved/classified: 0
- P0 remaining without official resolution: 0
- P1 resolved with official evidence: 0
- P1 remaining without official resolution: 1

## Root Causes

- CONFIRMED_DEMERGER: 1
- CONFIRMED_RIGHTS: 1
- CONFIRMED_SPLIT: 2
- NO_OFFICIAL_EVENT_FOUND: 60
- SERIES_TRANSITION: 239

## Manual Review Rows

- Manual-review/complex/special-series groups: 4299
- Total affected adjusted rows analyzed: 1177039
- Nifty 500 relevant rows: 186910
- Non-Nifty rows: 990129
- EQ rows: 355455
- Special-series rows: 821584
- Rights rows: 144182
- Special-dividend rows: 163361
- Merger/demerger rows: 47912
- Unresolved manual-review rows: 0

## Research Eligibility

- Eligibility intervals created: 890
- Eligibility CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reference\nse\corporate_actions\research_eligibility.csv
- EXCLUDE_CORPORATE_ACTION_WINDOW: 14
- MANUAL_REVIEW_REQUIRED: 121
- RESEARCH_READY: 755

## Symbol-Level Readiness

- FULLY_READY: 611
- READY_WITH_EXCLUSIONS: 9
- NOT_READY: 86
- Critical unresolved symbols: None

## Integrity And Safety

- Raw NSE unchanged: True
- Normalized RAW unchanged: True
- Existing adjusted dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy calculations were executed.

## Known Limitations

- The historical Nifty 500 membership layer remains PARTIAL_HISTORY.
- P0/P1 official review uses currently normalized official NSE corporate-action rows; cases without matched official event remain conservative.
- Rights, special dividends, mergers, and demergers remain policy-driven exclusions or manual-review metadata, not new adjustment factors.
