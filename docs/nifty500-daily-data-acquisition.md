# Nifty 500 Daily Data Acquisition

Current phase: Step 02.3C - Nifty 500 Universe Acquisition & Historical Dataset Download

## Source

- Universe source: Nifty Indices official constituent CSV
- Source URL: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
- Source date: 2026-09-07
- Constituent count: 501

## Groww Mapping

- Matched: 498
- Ambiguous: 0
- Not found: 1
- Inactive: 0
- Non-cash equity: 2

## Acquisition Scope

- Pilot symbols: RELIANCE, TCS, HDFCBANK, INFY, SUNPHARMA
- Full Nifty 500 acquisition run: False
- Target start date: 2021-09-07
- Target end date: 2026-09-07
- Overall earliest date received: 2021-09-07
- Overall latest date received: 2026-09-07
- Total daily candles downloaded: 5149

## Fetch Results

- COMPLETE: 0
- PARTIAL: 5
- FAILED: 0
- UNMAPPED: 0
- DRY_RUN: 0

## Storage

- Format: CSV
- Historical path: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\historical\daily\groww
- Summary CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\nifty500_daily_acquisition_summary.csv
- Summary JSON: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\nifty500_daily_acquisition_summary.json
- Mapping CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reference\nifty500\nifty500_groww_mapping.csv

## Data Quality

- OHLCV records are normalized into InterSignal `DailyCandle` models.
- Duplicate dates are merged per symbol after chunked requests.
- Missing sessions are estimated from weekdays only; exchange holidays are not subtracted yet.
- Rows with incomplete required OHLCV fields are skipped and counted.
- Invalid rows: 0
- Duplicate rows merged: 0
- Missing sessions estimate: 1376
- Zero-volume rows: 0
- Large-gap warnings: 10
- Incomplete Groww rows skipped: 1050

## Corporate Actions

- Price adjustment status: UNKNOWN
- No price adjustments were fabricated or applied.

## Rate Limiting And Resume

- Daily Groww requests are chunked into documented 180-day windows.
- Requests use configurable delay, retries, and exponential backoff.
- Resume mode reuses existing per-symbol CSV files.

## Safety

- ZERO order endpoints were called.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- Credentials remain local to ignored `backend/.env`.
