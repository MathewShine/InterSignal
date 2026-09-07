-- InterSignal Step 02.3A - Historical data ingestion run tracking
-- Local migration only. Execute manually in the Supabase SQL editor when ready.
-- This migration records import attempts and row-level ingestion issues without
-- fetching data or coupling ingestion to a single provider.

create extension if not exists pgcrypto;

create table if not exists public.ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  import_type text not null,
  source_reference text null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null,
  status text not null default 'STARTED',
  rows_read integer not null default 0,
  rows_valid integer not null default 0,
  rows_inserted integer not null default 0,
  rows_updated integer not null default 0,
  rows_skipped integer not null default 0,
  rows_rejected integer not null default 0,
  warnings_count integer not null default 0,
  error_message text null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint ingestion_runs_status_check
    check (status in ('STARTED', 'COMPLETED', 'FAILED', 'PARTIAL', 'DRY_RUN')),
  constraint ingestion_runs_import_type_check
    check (import_type in ('INSTRUMENTS', 'DAILY_CANDLES', 'INTRADAY_CANDLES')),
  constraint ingestion_runs_completion_check
    check (completed_at is null or completed_at >= started_at),
  constraint ingestion_runs_non_negative_counts_check
    check (
      rows_read >= 0
      and rows_valid >= 0
      and rows_inserted >= 0
      and rows_updated >= 0
      and rows_skipped >= 0
      and rows_rejected >= 0
      and warnings_count >= 0
    )
);

comment on table public.ingestion_runs is
  'Provider-agnostic historical-data import run summaries, including dry-run attempts.';

create table if not exists public.ingestion_errors (
  id uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid not null references public.ingestion_runs(id) on delete cascade,
  row_reference text null,
  error_code text not null,
  message text not null,
  raw_record jsonb null,
  created_at timestamptz not null default now()
);

comment on table public.ingestion_errors is
  'Row-level ingestion errors retained for debugging malformed source files and provider payloads.';

create index if not exists idx_ingestion_runs_provider_started
  on public.ingestion_runs (provider, started_at desc);

create index if not exists idx_ingestion_runs_status_started
  on public.ingestion_runs (status, started_at desc);

create index if not exists idx_ingestion_runs_import_type_started
  on public.ingestion_runs (import_type, started_at desc);

create index if not exists idx_ingestion_errors_run
  on public.ingestion_errors (ingestion_run_id);

create index if not exists idx_ingestion_errors_code
  on public.ingestion_errors (error_code);

alter table public.ingestion_runs enable row level security;
alter table public.ingestion_errors enable row level security;
