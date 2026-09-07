# Groww vs NSE Daily Data Audit

Current phase: Step 02.3C Fix - Groww missing/incomplete daily row diagnosis

## Purpose

Diagnose whether skipped Groww daily rows are harmless placeholders, official NSE non-trading days, genuine missing trading-session data, malformed provider responses, or another provider-format issue.

## Sources

- Groww source: official Groww historical candles API via `growwapi`
- NSE source: Official NSE daily security bhavcopy sec_bhavdata_full_DDMMYYYY.csv
- NSE URL template: https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv
- Nifty universe context: NIFTY 500

## Scope

- Pilot symbols: RELIANCE, TCS, HDFCBANK, INFY, SUNPHARMA
- Date range: 2021-09-07 to 2026-09-07
- Expected NSE sessions per symbol: 1240

## Per-Symbol Completeness

- RELIANCE: NSE expected 1240, Groww valid 1029, incomplete 210, missing 1, completeness 82.98%, status PARTIAL
- TCS: NSE expected 1240, Groww valid 1029, incomplete 210, missing 1, completeness 82.98%, status PARTIAL
- HDFCBANK: NSE expected 1240, Groww valid 1029, incomplete 210, missing 1, completeness 82.98%, status PARTIAL
- INFY: NSE expected 1240, Groww valid 1028, incomplete 210, missing 2, completeness 82.90%, status PARTIAL
- SUNPHARMA: NSE expected 1240, Groww valid 1029, incomplete 210, missing 1, completeness 82.98%, status PARTIAL

## Root Cause Totals

- NSE expected symbol-sessions: 6200
- Groww valid sessions: 5144
- Groww incomplete sessions on NSE trading days: 1050
- Groww missing sessions on NSE trading days: 6
- Non-trading-day placeholders: 5
- Incomplete rows inspected: 1050
- Incomplete rows on official NSE trading sessions: 1050
- Incomplete rows with valid NSE symbol record: 1050
- Incomplete weekday rows: 1045
- Incomplete weekend special-session rows: 5
- Unique incomplete dates: 210
- Incomplete date range: 2025-01-01 to 2026-09-04

## Value Comparison

- Both-present near matches: 4027
- Both-present mismatches: 1117
- Mismatch count: 1117
- Max price absolute diff: 350049.50
- Max price pct diff: 98.67855502831777131486300321
- Max volume absolute diff: 3262598
- Max volume pct diff: 0.2193393917815645618964230164

## Corporate Actions

- Adjustment conclusion: UNKNOWN
- No corporate-action adjustment was implemented or applied.

## Decision

- Final classification: C_INSUFFICIENT_FOR_BACKTESTING
- Recommended next action: Make official NSE daily history the primary source for backtesting.

## Storage

- Row audit directory: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\groww_nse_audit
- Summary CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\groww_nse_daily_audit_summary.csv
- Summary JSON: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\groww_nse_daily_audit_summary.json
- NSE cache directory: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reference\nse\daily\raw

## Safety

- ZERO order endpoints were called.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- Credentials remain local to ignored `backend/.env`.
