# InterSignal

InterSignal is a provider-agnostic research platform for NSE swing-trading analysis. This repository currently contains the web/API foundation and the local initial database schema migration.

## Current Phase

Step 02.2 - Database Schema

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
      schemas/
      services/
      utils/
      main.py
    migrations/
      001_initial_schema.sql
    tests/
    .env.example
    requirements.txt
  docs/
    database-schema.md
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

## Architecture Principles

- Keep broker and market-data providers behind generic interfaces.
- Keep future strategy configuration outside strategy code.
- Load runtime settings from environment variables or future configuration services.
- Keep secrets out of source control and logs.
- Keep dependencies minimal until the product surface requires more.
- Preserve raw, normalized, derived, candidate, signal, trade, and outcome layers separately.
- Retain rejected candidates so missed winners and good rejections can be studied later.
- Keep strategy and risk thresholds configuration-driven and versioned.

## Current Scope Exclusions

- No live trading implemented.
- No strategy logic implemented.
- No Groww integration implemented.
- No React Native application implemented.

## Next Planned Task

Step 02.3 - Historical Data Ingestion
