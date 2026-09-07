# Official NSE 5-Year Daily Dataset

Current phase: Step 02.3D - Official NSE primary daily-history dataset foundation

## Official Sources

- Legacy security bhavcopy: https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv
- CM-UDiFF bhavcopy: https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip
- Authoritative source policy: official NSE archives only.

## Date Coverage

- Run mode: FULL
- Target start date: 2021-09-07
- Target end date: 2026-09-07
- Actual first trading session: 2021-09-07
- Actual last trading session: 2026-09-07
- Calendar dates checked: 1827
- Trading sessions found from official files: 1240
- Non-session dates identified: 587

## Retrieval And Calendar

- The trading calendar is derived from official daily file availability and internal trade dates.
- Weekends are treated as trading sessions only when official rows exist for that date.
- Holidays are not counted as missing sessions when no official daily cash file exists.
- Calendar artifact: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reference\nse\calendar\nse_cash_trading_calendar.csv

## Normalization

- Normalized format: partitioned CSV
- Raw path: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\raw\nse\daily
- Normalized path: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\historical\daily\nse
- Canonical rows retain exchange, symbol, series, ISIN when available, OHLCV, traded value, source file, source format, and adjustment status.

## Series Handling

- Normal eligible equity series: EQ
- Special series are retained with provenance and are not remapped to EQ.
- EQ records: 2425170
- Special-series records: 821584

## Data Quality

- Total normalized records: 3246754
- Invalid records skipped: 216
- Duplicate symbol/series/date rows skipped: 0
- Zero-volume records retained and flagged: 0
- Corporate-action suspect rows flagged: 808

## Completeness

- Sessions downloaded or imported from cache: 1240
- Expected trading sessions missing after calendar derivation: 0
- Sessions failed: 0

## Corporate Actions

- Price adjustment status: RAW
- No adjusted prices were fabricated or applied.
- Next planned phase: Step 02.3E - Corporate Actions & Adjusted Research Prices

## Limitations

- This foundation does not calculate strategy indicators, momentum scores, breakouts, market regime, or backtests.
- Bulk rows remain local and are not persisted to Supabase.
- CSV was used instead of Parquet to avoid adding a heavy dependency before review.

## Safety

- ZERO order endpoints were called.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy calculations were executed.
