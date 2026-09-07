from pathlib import Path


def test_initial_schema_migration_defines_required_tables():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "001_initial_schema.sql"
    ).read_text(encoding="utf-8")

    required_tables = [
        "instruments",
        "daily_candles",
        "intraday_candles",
        "raw_market_events",
        "news_events",
        "market_regime_snapshots",
        "feature_snapshots",
        "strategy_candidates",
        "signal_penalties",
        "trade_signals",
        "strategy_configurations",
        "backtest_runs",
        "candidate_outcomes",
        "simulated_trades",
        "audit_events",
    ]

    for table in required_tables:
        assert f"create table if not exists public.{table}" in migration
        assert f"alter table public.{table} enable row level security;" in migration


def test_initial_schema_keeps_research_execution_separate_from_live_trading():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "001_initial_schema.sql"
    ).read_text(encoding="utf-8")

    assert "account_mode in ('RESEARCH', 'PAPER')" in migration
    assert "LIVE" not in migration
    assert "UNASSIGNED_RESEARCH" in migration


def test_data_ingestion_migration_tracks_runs_and_row_errors():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "002_data_ingestion.sql"
    ).read_text(encoding="utf-8")

    assert "create table if not exists public.ingestion_runs" in migration
    assert "create table if not exists public.ingestion_errors" in migration
    assert "status in ('STARTED', 'COMPLETED', 'FAILED', 'PARTIAL', 'DRY_RUN')" in migration
    assert "alter table public.ingestion_runs enable row level security;" in migration
