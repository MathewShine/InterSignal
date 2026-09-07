# InterSignal

InterSignal is a provider-agnostic research platform for NSE swing-trading analysis. This repository currently contains the web/API foundation, local database schema migrations, and a provider-agnostic historical data ingestion framework.

## Current Phase

Step 02.3C - Nifty 500 Universe Acquisition & Historical Dataset Download

## Technology Stack

- Frontend: React, JavaScript, Vite
- Backend: Python, FastAPI
- Database/configuration platform: Supabase
- Later backend deployment target: Railway

## Folder Structure

```text
InterSignal/
  frontend/
    public/
    src/
      api/
      components/
      config/
      hooks/
      layouts/
      pages/
      services/
      utils/
      App.jsx
      main.jsx
      styles.css
    .env.example
    index.html
    package.json
    vite.config.js
  backend/
    app/
      api/
        routes/
        v1.py
      config/
      core/
      db/
      models/
      providers/
        groww/
      schemas/
      services/
      utils/
      main.py
    migrations/
      001_initial_schema.sql
      002_data_ingestion.sql
    scripts/
      ingest_history.py
      download_nifty500_daily.py
      audit_groww_vs_nse_daily.py
      test_groww_history.py
    tests/
      fixtures/
    .env.example
    requirements.txt
  docs/
    database-schema.md
    groww-historical-provider.md
    groww-vs-nse-daily-data-audit.md
    historical-data-ingestion.md
    nifty500-daily-data-acquisition.md
  data/
    reference/
      nifty500/
    historical/
      daily/
        groww/
    reports/
  scripts/
  .env.example
  .gitignore
  README.md
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:5173`.

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend defaults to `http://localhost:8000`.

## Environment Variables

Copy the example files before local development:

```bash
copy .env.example .env
copy frontend\.env.example frontend\.env
copy backend\.env.example backend\.env
```

Do not commit real `.env` files or secrets.

## Run Both Applications

Open two terminals:

```bash
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

```bash
cd frontend
npm run dev
```

## Current API Endpoints

- `GET /health`
- `GET /health/database`
- `GET /api/v1/health`
- `GET /api/v1/health/database`

## Database Schema

The initial local migration lives at:

```text
backend/migrations/001_initial_schema.sql
```

It is designed to be executable in the Supabase SQL editor. This repository does not automatically apply migrations to a remote Supabase database.

The schema preserves the research pipeline:

```text
raw data -> normalized data -> derived features -> candidates -> signals -> trade / paper trade -> outcomes / analytics
```

See `docs/database-schema.md` for table purposes, relationships, RLS notes, and the candidate/outcome learning loop.

## Historical Data Ingestion

The ingestion framework is provider-agnostic. It currently supports generic CSV dry runs, NSE local file/ZIP normalization foundations, and a read-only Groww historical provider validation path for one NSE cash equity.

Example dry run:

```bash
cd backend
.venv\Scripts\python.exe scripts\ingest_history.py --provider csv --file tests\fixtures\sample_daily_candles.csv --mode daily --source synthetic_fixture --mapping-preset sample-daily --dry-run
```

See `docs/historical-data-ingestion.md` for architecture, mappings, timezone rules, validation behavior, deduplication, and import-run auditing.

Groww read-only diagnostic:

```bash
cd backend
.venv\Scripts\python.exe scripts\test_groww_history.py --symbol RELIANCE --daily-start 2025-01-01 --daily-end 2025-03-31
```

See `docs/groww-historical-provider.md` for credential handling, official SDK references, supported intervals, and current Step 02.3B limits.

Nifty 500 daily acquisition pilot:

```bash
cd backend
.venv\Scripts\python.exe scripts\download_nifty500_daily.py --resume
```

The default command runs the five-symbol pilot only. Use `--run-full` only after reviewing pilot output and API pacing. Bulk historical files under `data/historical/` and machine-readable reports under `data/reports/` are ignored by Git.

Groww versus NSE daily audit:

```bash
cd backend
.venv\Scripts\python.exe scripts\audit_groww_vs_nse_daily.py
```

The audit compares the five-symbol Groww pilot with official NSE daily security bhavcopy records and writes local report artifacts under `data/reports/`.

## Architecture Principles

- Keep broker and market-data providers behind generic interfaces.
- Keep future strategy configuration outside strategy code.
- Load runtime settings from environment variables or future configuration services.
- Keep secrets out of source control and logs.
- Keep dependencies minimal until the product surface requires more.
- Preserve raw, normalized, derived, candidate, signal, trade, and outcome layers separately.
- Retain rejected candidates so missed winners and good rejections can be studied later.
- Keep strategy and risk thresholds configuration-driven and versioned.
- Keep ingestion separate from indicators, signals, strategy logic, and execution.

## Current Scope Exclusions

- No live trading implemented.
- No strategy logic implemented.
- No trading execution implemented.
- No React Native application implemented.
- No full historical dataset download implemented.

## Next Planned Task

Step 02.3D - Historical Dataset Review & Database Ingestion Planning
