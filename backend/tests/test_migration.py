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

