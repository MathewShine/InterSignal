# Nifty 500 Point-in-Time Membership

Current phase: Step 02.3D-Fix - historical membership reconstruction

## Official Sources

- Current constituent CSV: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
- Press-release index: https://www.niftyindices.com/press-release
- Index rebalancing schedule reference: https://www.niftyindices.com/resources/index-rebalancing-schedule
- Official documents inventoried: 135
- Documents containing Nifty 500 changes: 35
- Documents successfully parsed: 34
- Documents parsed with review items: 0
- Documents requiring manual review: 0

## Current Snapshot

- Source date: 2026-09-07
- Current constituent snapshot count: 501

## Extracted Events

- ADD events: 305
- REMOVE events: 304
- Earliest effective event date: 2021-06-30
- Latest effective event date: 2026-09-30

## Review Cycle Coverage

- Expected semi-annual cycles: 11
- Covered cycles: 11
- 2021-09: source_found=True, parsed=True, effective_dates=2021-09-30, additions=22, removals=22, unresolved_rows=0
- 2022-03: source_found=True, parsed=True, effective_dates=2022-03-31, additions=32, removals=32, unresolved_rows=0
- 2022-09: source_found=True, parsed=True, effective_dates=2022-09-30, additions=19, removals=19, unresolved_rows=0
- 2023-03: source_found=True, parsed=True, effective_dates=2023-03-31, additions=20, removals=20, unresolved_rows=0
- 2023-09: source_found=True, parsed=True, effective_dates=2023-09-29, additions=18, removals=18, unresolved_rows=0
- 2024-03: source_found=True, parsed=True, effective_dates=2024-03-28, additions=34, removals=34, unresolved_rows=0
- 2024-09: source_found=True, parsed=True, effective_dates=2024-09-30, additions=27, removals=27, unresolved_rows=0
- 2025-03: source_found=True, parsed=True, effective_dates=2025-03-21,2025-03-28, additions=31, removals=31, unresolved_rows=0
- 2025-09: source_found=True, parsed=True, effective_dates=2025-09-23,2025-09-30, additions=19, removals=19, unresolved_rows=0
- 2026-03: source_found=True, parsed=True, effective_dates=2026-03-30, additions=31, removals=31, unresolved_rows=0
- 2026-09: source_found=True, parsed=True, effective_dates=2026-09-07,2026-09-30, additions=28, removals=27, unresolved_rows=0

## Reconstruction

- Method: BACKWARD_RECONSTRUCTED_FROM_CURRENT_SNAPSHOT
- Earliest reliable date: 2021-09-30
- Latest reliable date: 2026-09-07
- Membership periods available: 755
- Unresolved company/symbol mappings: 0
- Controlled identity aliases: 7
- Reconciliation differences: 1
- Lifecycle anomalies: 3

## Point-In-Time Query Capability

- `get_nifty500_members(as_of_date)` returns symbol set, count, coverage status, confidence, and reconstructable date bounds.
- It does not silently substitute current constituents for dates outside verified range.
- Use `python scripts/query_nifty500_membership.py --date YYYY-MM-DD` for diagnostics.

## Survivorship Bias Status

- Status: PARTIAL_HISTORY

## Limitations

- Historical membership is reconstructed from parsed official documents but has not been manually reconciled end to end.
- Lifecycle anomalies remain unresolved: 3 event applications need review.
- Count reconciliation differences remain on 1 effective dates.

## Safety

- ZERO order endpoints were called.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy calculations were executed.
