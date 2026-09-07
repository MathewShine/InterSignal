# Historical Data Ingestion

Current phase: Step 02.3B - Groww Historical Connection Validation

The ingestion framework preserves this flow:

```text
SOURCE DATA
  -> RAW INGESTION
  -> NORMALIZATION
  -> VALIDATION / DATA QUALITY
  -> DATABASE PERSISTENCE
  -> LATER FEATURE ENGINE
```

Strategy calculations, indicators, signal generation, backtesting, and trading execution are intentionally out of scope.

## Architecture

Historical sources implement `HistoricalDataProvider`. Providers return normalized records plus parse errors; they do not write directly to the database.

`HistoricalIngestionService` receives provider output, validates records, deduplicates rows inside the import batch, prepares persistence operations, and returns an `ImportSummary`.

Repository classes isolate Supabase-specific upsert logic from provider parsing and ingestion orchestration.

## Provider Abstraction

The historical provider contract supports:

- `list_instruments`
- `get_daily_candles`
- `get_intraday_candles`
- `supports_interval`
- `get_provider_metadata`

Current provider modules:

- `CsvHistoricalDataProvider`
- `NSEFileProvider`
- `GrowwHistoricalProvider`

## Supported Sources

CSV imports are supported for local files with configurable column mappings.

NSE file ingestion is prepared for local official files, including CSV inside ZIP archives. Step 02.3A includes a daily bhavcopy-style adapter and a security-master adapter skeleton.

Groww historical ingestion is implemented as a read-only SDK-backed adapter for one NSE cash equity validation path. It authenticates from `backend/.env`, normalizes candle data into the generic provider contract, and does not place orders.

See `docs/groww-historical-provider.md` for credential rules, supported intervals, official SDK references, and the read-only diagnostic.

## CSV Format Flexibility

CSV parsing uses a mapping object rather than hardcoded shared column names. Example:

```json
{
  "symbol": "SYMBOL",
  "date": "DATE",
  "open": "OPEN",
  "high": "HIGH",
  "low": "LOW",
  "close": "CLOSE",
  "volume": "VOLUME"
}
```

Optional columns include adjusted close, traded value, VWAP, provider symbol, sector, industry, and instrument metadata.

## Timezone Rules

Intraday timestamps are normalized to `Asia/Kolkata`. Normalized intraday models reject naive timestamps, while CSV parsing treats naive local-file timestamps as Indian market time and attaches `Asia/Kolkata`.

Daily candles keep `trading_date` as a date, not a timestamp.

## Data Quality Checks

Validation currently checks:

- OHLC consistency
- negative prices
- negative volume
- missing source/symbol/exchange
- unsupported intraday intervals
- zero-volume warnings
- configurable extreme one-candle movement warning
- duplicate rows inside a batch
- gaps in expected intraday sequences

Records with errors are rejected. Records with warnings remain valid unless they are duplicates.

## Deduplication And Upsert Strategy

Within a single import batch, duplicate rows are skipped and reported as warnings.

Database persistence is designed to use existing unique constraints:

- Daily candles: instrument, trading date, source
- Intraday candles: instrument, timestamp, interval, source

The repository layer uses upsert semantics. Re-running an import should update matching rows rather than create duplicate candle records.

## Dry-Run Workflow

Dry-run mode does not require Supabase credentials. It parses, normalizes, validates, deduplicates, and summarizes records without writing to the database.

Example:

```bash
cd backend
.venv\Scripts\python.exe scripts\ingest_history.py --provider csv --file tests\fixtures\sample_daily_candles.csv --mode daily --source synthetic_fixture --mapping-preset sample-daily --dry-run
```

NSE local ZIP example:

```bash
cd backend
.venv\Scripts\python.exe scripts\ingest_history.py --provider nse-file --file path\to\bhavcopy.zip --mode daily --source nse_bhavcopy --dry-run
```

## Import Run Auditing

The local migration `backend/migrations/002_data_ingestion.sql` adds:

- `ingestion_runs`
- `ingestion_errors`

These tables are intended to store import summaries and row-level errors after remote migrations are applied and persistence is enabled.

## Remote Application

No migration has been applied remotely in Step 02.3A. No historical market data has been downloaded.
