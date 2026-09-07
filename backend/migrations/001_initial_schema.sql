-- InterSignal Step 02.2 - Initial database schema
-- Local migration only. Execute manually in the Supabase SQL editor when ready.
-- This schema preserves the research pipeline:
-- raw data -> normalized data -> derived features -> candidates -> signals
-- -> trade / paper trade -> outcomes / analytics.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.strategy_configurations (
  id uuid primary key default gen_random_uuid(),
  strategy_name text not null,
  version text not null,
  status text not null default 'DRAFT',
  effective_from timestamptz null,
  effective_to timestamptz null,
  configuration jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint strategy_configurations_unique_version unique (strategy_name, version),
  constraint strategy_configurations_status_check
    check (status in ('DRAFT', 'ACTIVE', 'ARCHIVED')),
  constraint strategy_configurations_effective_range_check
    check (effective_to is null or effective_from is null or effective_to >= effective_from)
);

comment on table public.strategy_configurations is
  'Versioned, configuration-driven strategy and risk settings. Values are JSONB so thresholds can evolve without strategy code changes.';

create table if not exists public.instruments (
  id uuid primary key default gen_random_uuid(),
  provider_symbol text null,
  exchange text not null,
  trading_symbol text not null,
  company_name text not null,
  isin text null,
  sector text null,
  industry text null,
  instrument_type text not null,
  nifty500_member boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint instruments_exchange_symbol_unique unique (exchange, trading_symbol)
);

comment on table public.instruments is
  'Canonical provider-agnostic tradable-instrument master. Provider-specific symbols are optional metadata, not table identity.';

create table if not exists public.daily_candles (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  trading_date date not null,
  open numeric(18, 4) not null,
  high numeric(18, 4) not null,
  low numeric(18, 4) not null,
  close numeric(18, 4) not null,
  adjusted_close numeric(18, 4) null,
  volume bigint not null,
  traded_value numeric(20, 2) null,
  source text not null,
  created_at timestamptz not null default now(),
  constraint daily_candles_unique_source unique (instrument_id, trading_date, source),
  constraint daily_candles_price_order_check check (high >= low),
  constraint daily_candles_volume_check check (volume >= 0)
);

comment on table public.daily_candles is
  'Normalized end-of-day OHLCV candles. Raw provider payloads belong in raw_market_events.';

create table if not exists public.intraday_candles (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  candle_timestamp timestamptz not null,
  interval_code text not null,
  open numeric(18, 4) not null,
  high numeric(18, 4) not null,
  low numeric(18, 4) not null,
  close numeric(18, 4) not null,
  volume bigint not null,
  traded_value numeric(20, 2) null,
  vwap numeric(18, 4) null,
  source text not null,
  created_at timestamptz not null default now(),
  constraint intraday_candles_unique_source unique (
    instrument_id,
    candle_timestamp,
    interval_code,
    source
  ),
  constraint intraday_candles_price_order_check check (high >= low),
  constraint intraday_candles_volume_check check (volume >= 0)
);

comment on table public.intraday_candles is
  'Normalized historical or live candles across all intervals. Intervals stay in one table through interval_code.';

create table if not exists public.raw_market_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_type text not null,
  instrument_id uuid null references public.instruments(id) on delete set null,
  provider_symbol text null,
  event_timestamp timestamptz not null,
  received_at timestamptz not null default now(),
  payload jsonb not null,
  schema_version text not null default '1',
  created_at timestamptz not null default now()
);

comment on table public.raw_market_events is
  'Original provider market events retained for reproducibility and debugging. Derived features are intentionally stored elsewhere.';

create table if not exists public.news_events (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid null references public.instruments(id) on delete set null,
  headline text not null,
  summary text null,
  source text not null,
  source_url text null,
  published_at timestamptz not null,
  ingested_at timestamptz not null default now(),
  event_category text not null,
  sentiment text not null,
  source_confidence numeric(6, 4) null,
  materiality_score numeric(6, 4) null,
  freshness_score numeric(6, 4) null,
  duplicate_cluster_id uuid null,
  raw_payload jsonb null,
  created_at timestamptz not null default now(),
  constraint news_events_sentiment_check check (sentiment in ('positive', 'negative', 'neutral')),
  constraint news_events_source_confidence_check
    check (source_confidence is null or (source_confidence >= 0 and source_confidence <= 1)),
  constraint news_events_materiality_score_check
    check (materiality_score is null or (materiality_score >= 0 and materiality_score <= 1)),
  constraint news_events_freshness_score_check
    check (freshness_score is null or (freshness_score >= 0 and freshness_score <= 1))
);

comment on table public.news_events is
  'Normalized catalyst and news events. News can support context, but does not itself create a trade.';

create table if not exists public.market_regime_snapshots (
  id uuid primary key default gen_random_uuid(),
  calculated_at timestamptz not null,
  regime text not null,
  subtype text null,
  score numeric(8, 4) not null,
  confidence numeric(6, 4) null,
  nifty_trend_score numeric(8, 4) null,
  breadth_score numeric(8, 4) null,
  sector_score numeric(8, 4) null,
  global_gift_score numeric(8, 4) null,
  vix_score numeric(8, 4) null,
  intraday_confirmation_score numeric(8, 4) null,
  configuration_version_id uuid null references public.strategy_configurations(id) on delete set null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint market_regime_confidence_check
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

comment on table public.market_regime_snapshots is
  'Every calculated market-regime state, including component scores and configuration version used.';

create table if not exists public.feature_snapshots (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  calculated_at timestamptz not null,
  timeframe text not null,
  feature_version text not null,
  features jsonb not null default '{}'::jsonb,
  relative_volume numeric(12, 6) null,
  relative_strength_nifty numeric(12, 6) null,
  relative_strength_sector numeric(12, 6) null,
  atr numeric(18, 4) null,
  atr_percent numeric(12, 6) null,
  vwap numeric(18, 4) null,
  distance_from_vwap numeric(18, 4) null,
  breakout_level numeric(18, 4) null,
  breakout_type text null,
  breakout_quality numeric(8, 4) null,
  momentum_score numeric(8, 4) null,
  extension_score numeric(8, 4) null,
  created_at timestamptz not null default now(),
  constraint feature_snapshots_unique_version unique (
    instrument_id,
    calculated_at,
    timeframe,
    feature_version
  )
);

comment on table public.feature_snapshots is
  'Derived stock features at a point in time. JSONB preserves extensibility while selected fields remain queryable.';

create table if not exists public.strategy_candidates (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  detected_at timestamptz not null,
  strategy_name text not null,
  strategy_version text not null,
  execution_mode text not null,
  momentum_classification text not null,
  status text not null default 'DISCOVERED',
  feature_snapshot_id uuid null references public.feature_snapshots(id) on delete set null,
  market_regime_snapshot_id uuid null references public.market_regime_snapshots(id) on delete set null,
  news_event_id uuid null references public.news_events(id) on delete set null,
  catalyst_context jsonb null,
  base_score numeric(8, 4) null,
  adjusted_score numeric(8, 4) null,
  rejection_reason text null,
  configuration_version_id uuid null references public.strategy_configurations(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint strategy_candidates_execution_mode_check check (execution_mode in ('INTRADAY', 'SWING')),
  constraint strategy_candidates_momentum_check check (momentum_classification in ('EMERGING', 'CONFIRMED')),
  constraint strategy_candidates_status_check
    check (status in (
      'DISCOVERED',
      'WATCH',
      'BREAKOUT_DETECTED',
      'CONFIRMING',
      'ENTRY_ELIGIBLE',
      'REJECTED',
      'EXPIRED'
    )),
  constraint strategy_candidates_rejection_reason_check
    check (status <> 'REJECTED' or rejection_reason is not null)
);

comment on table public.strategy_candidates is
  'All meaningful candidates, accepted or rejected. Retention supports later missed-winner and good-rejection analysis.';

create table if not exists public.signal_penalties (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.strategy_candidates(id) on delete cascade,
  penalty_type text not null,
  penalty_value numeric(8, 4) not null,
  reason text not null,
  metadata jsonb null,
  created_at timestamptz not null default now()
);

comment on table public.signal_penalties is
  'Score penalties stored separately so UI and analytics can show base score and deductions independently.';

create table if not exists public.trade_signals (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.strategy_candidates(id) on delete cascade,
  generated_at timestamptz not null,
  signal_type text not null,
  execution_mode text not null,
  entry_price numeric(18, 4) null,
  entry_price_low numeric(18, 4) null,
  entry_price_high numeric(18, 4) null,
  stop_price numeric(18, 4) not null,
  target_price numeric(18, 4) null,
  risk_reward_ratio numeric(10, 4) null,
  planned_risk_amount numeric(18, 4) null,
  planned_position_size numeric(18, 4) null,
  signal_score numeric(8, 4) not null,
  status text not null default 'GENERATED',
  configuration_version_id uuid null references public.strategy_configurations(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint trade_signals_execution_mode_check check (execution_mode in ('INTRADAY', 'SWING')),
  constraint trade_signals_status_check
    check (status in ('GENERATED', 'ACTIVE', 'EXPIRED', 'CANCELLED', 'CLOSED')),
  constraint trade_signals_entry_range_check
    check (
      entry_price_low is null
      or entry_price_high is null
      or entry_price_high >= entry_price_low
    )
);

comment on table public.trade_signals is
  'Signal-level records only. No broker order placement is represented or executed by this table.';

create table if not exists public.backtest_runs (
  id uuid primary key default gen_random_uuid(),
  strategy_name text not null,
  strategy_version text not null,
  configuration_version_id uuid null references public.strategy_configurations(id) on delete set null,
  dataset_version text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null,
  start_date date not null,
  end_date date not null,
  status text not null default 'PENDING',
  parameters jsonb not null default '{}'::jsonb,
  results_summary jsonb null,
  created_at timestamptz not null default now(),
  constraint backtest_runs_status_check
    check (status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
  constraint backtest_runs_date_range_check check (end_date >= start_date),
  constraint backtest_runs_completion_check check (completed_at is null or completed_at >= started_at)
);

comment on table public.backtest_runs is
  'Reproducible research experiment metadata. Backtest execution itself is not implemented in Step 02.2.';

create table if not exists public.candidate_outcomes (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null unique references public.strategy_candidates(id) on delete cascade,
  evaluation_completed_at timestamptz not null,
  return_5m numeric(12, 6) null,
  return_15m numeric(12, 6) null,
  return_30m numeric(12, 6) null,
  return_60m numeric(12, 6) null,
  return_eod numeric(12, 6) null,
  return_1d numeric(12, 6) null,
  return_2d numeric(12, 6) null,
  return_3d numeric(12, 6) null,
  return_4d numeric(12, 6) null,
  mfe numeric(12, 6) null,
  mae numeric(12, 6) null,
  mfe_r numeric(12, 6) null,
  mae_r numeric(12, 6) null,
  hit_0_5r boolean null,
  hit_1r boolean null,
  hit_1_5r boolean null,
  hit_2r boolean null,
  hit_3r boolean null,
  stop_hit boolean null,
  hit_1r_before_stop boolean null,
  hit_2r_before_stop boolean null,
  outcome_label text not null,
  metadata jsonb null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_outcomes_label_check
    check (outcome_label in (
      'STRONG_WIN',
      'WIN',
      'SMALL_WIN',
      'BREAKEVEN',
      'LOSS',
      'STRONG_LOSS',
      'NO_FOLLOW_THROUGH',
      'FALSE_BREAKOUT',
      'MISSED_WINNER',
      'GOOD_REJECTION'
    ))
);

comment on table public.candidate_outcomes is
  'Post-event labels for accepted and rejected candidates. This closes the candidate/outcome learning loop.';

create table if not exists public.simulated_trades (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.strategy_candidates(id) on delete cascade,
  signal_id uuid null references public.trade_signals(id) on delete set null,
  account_mode text not null,
  entry_price numeric(18, 4) null,
  exit_price numeric(18, 4) null,
  quantity numeric(18, 4) null,
  planned_risk numeric(18, 4) null,
  simulated_costs numeric(18, 4) null,
  actual_costs numeric(18, 4) null,
  slippage numeric(18, 4) null,
  pnl numeric(18, 4) null,
  pnl_r numeric(12, 6) null,
  status text not null default 'PLANNED',
  entry_time timestamptz null,
  exit_time timestamptz null,
  exit_reason text null,
  metadata jsonb null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint simulated_trades_account_mode_check check (account_mode in ('RESEARCH', 'PAPER')),
  constraint simulated_trades_status_check
    check (status in ('PLANNED', 'OPEN', 'CLOSED', 'CANCELLED', 'EXPIRED')),
  constraint simulated_trades_time_order_check
    check (exit_time is null or entry_time is null or exit_time >= entry_time)
);

comment on table public.simulated_trades is
  'Future research and paper-trade records only. Live execution is intentionally out of scope.';

create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  event_timestamp timestamptz not null default now(),
  event_type text not null,
  entity_type text not null,
  entity_id uuid null,
  actor_type text not null,
  actor_id text null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on table public.audit_events is
  'System-level audit trail for future configuration changes, signal transitions, trade lifecycle changes, risk decisions, and failures.';

insert into public.strategy_configurations (
  strategy_name,
  version,
  status,
  configuration
)
values (
  'UNASSIGNED_RESEARCH',
  '0.0.0',
  'DRAFT',
  '{"description": "Safe placeholder only. No strategy thresholds, weights, risk values, or trading parameters are defined.", "parameters": {}}'::jsonb
)
on conflict (strategy_name, version) do nothing;

create index if not exists idx_instruments_active on public.instruments (active);
create index if not exists idx_instruments_exchange_type on public.instruments (exchange, instrument_type);
create index if not exists idx_daily_candles_instrument_date on public.daily_candles (instrument_id, trading_date desc);
create index if not exists idx_daily_candles_date_source on public.daily_candles (trading_date desc, source);
create index if not exists idx_intraday_candles_instrument_interval_time on public.intraday_candles (instrument_id, interval_code, candle_timestamp desc);
create index if not exists idx_intraday_candles_time_source on public.intraday_candles (candle_timestamp desc, source);
create index if not exists idx_raw_market_events_provider_time on public.raw_market_events (provider, event_timestamp desc);
create index if not exists idx_raw_market_events_instrument on public.raw_market_events (instrument_id, event_timestamp desc);
create index if not exists idx_raw_market_events_payload_gin on public.raw_market_events using gin (payload);
create index if not exists idx_news_events_instrument_time on public.news_events (instrument_id, published_at desc);
create index if not exists idx_news_events_source_time on public.news_events (source, published_at desc);
create index if not exists idx_news_events_cluster on public.news_events (duplicate_cluster_id);
create unique index if not exists idx_news_events_unique_source_url on public.news_events (source, source_url) where source_url is not null;
create index if not exists idx_market_regime_snapshots_time on public.market_regime_snapshots (calculated_at desc);
create index if not exists idx_market_regime_snapshots_regime on public.market_regime_snapshots (regime, calculated_at desc);
create index if not exists idx_feature_snapshots_instrument_timeframe_time on public.feature_snapshots (instrument_id, timeframe, calculated_at desc);
create index if not exists idx_feature_snapshots_features_gin on public.feature_snapshots using gin (features);
create index if not exists idx_strategy_candidates_instrument_time on public.strategy_candidates (instrument_id, detected_at desc);
create index if not exists idx_strategy_candidates_status_time on public.strategy_candidates (status, detected_at desc);
create index if not exists idx_strategy_candidates_strategy on public.strategy_candidates (strategy_name, strategy_version);
create index if not exists idx_strategy_candidates_news_event on public.strategy_candidates (news_event_id);
create index if not exists idx_signal_penalties_candidate on public.signal_penalties (candidate_id);
create index if not exists idx_trade_signals_candidate on public.trade_signals (candidate_id);
create index if not exists idx_trade_signals_status_time on public.trade_signals (status, generated_at desc);
create index if not exists idx_backtest_runs_strategy on public.backtest_runs (strategy_name, strategy_version);
create index if not exists idx_backtest_runs_status on public.backtest_runs (status, started_at desc);
create index if not exists idx_candidate_outcomes_label on public.candidate_outcomes (outcome_label);
create index if not exists idx_simulated_trades_candidate on public.simulated_trades (candidate_id);
create index if not exists idx_simulated_trades_signal on public.simulated_trades (signal_id);
create index if not exists idx_simulated_trades_status on public.simulated_trades (status, entry_time desc);
create index if not exists idx_audit_events_time on public.audit_events (event_timestamp desc);
create index if not exists idx_audit_events_entity on public.audit_events (entity_type, entity_id);
create index if not exists idx_audit_events_type on public.audit_events (event_type, event_timestamp desc);

drop trigger if exists set_strategy_configurations_updated_at on public.strategy_configurations;
create trigger set_strategy_configurations_updated_at
before update on public.strategy_configurations
for each row execute function public.set_updated_at();

drop trigger if exists set_instruments_updated_at on public.instruments;
create trigger set_instruments_updated_at
before update on public.instruments
for each row execute function public.set_updated_at();

drop trigger if exists set_strategy_candidates_updated_at on public.strategy_candidates;
create trigger set_strategy_candidates_updated_at
before update on public.strategy_candidates
for each row execute function public.set_updated_at();

drop trigger if exists set_trade_signals_updated_at on public.trade_signals;
create trigger set_trade_signals_updated_at
before update on public.trade_signals
for each row execute function public.set_updated_at();

drop trigger if exists set_candidate_outcomes_updated_at on public.candidate_outcomes;
create trigger set_candidate_outcomes_updated_at
before update on public.candidate_outcomes
for each row execute function public.set_updated_at();

drop trigger if exists set_simulated_trades_updated_at on public.simulated_trades;
create trigger set_simulated_trades_updated_at
before update on public.simulated_trades
for each row execute function public.set_updated_at();

-- Supabase RLS preparation:
-- Enable RLS now and intentionally define no frontend write policies in this
-- migration. The backend/service role should own ingestion, derived research
-- records, signal transitions, configuration changes, outcomes, and audits.
alter table public.strategy_configurations enable row level security;
alter table public.instruments enable row level security;
alter table public.daily_candles enable row level security;
alter table public.intraday_candles enable row level security;
alter table public.raw_market_events enable row level security;
alter table public.news_events enable row level security;
alter table public.market_regime_snapshots enable row level security;
alter table public.feature_snapshots enable row level security;
alter table public.strategy_candidates enable row level security;
alter table public.signal_penalties enable row level security;
alter table public.trade_signals enable row level security;
alter table public.backtest_runs enable row level security;
alter table public.candidate_outcomes enable row level security;
alter table public.simulated_trades enable row level security;
alter table public.audit_events enable row level security;
