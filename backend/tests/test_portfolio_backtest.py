from __future__ import annotations

import copy
import csv
import gzip
import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.portfolio_config import (
    FUTURE_INTRADAY_BACKTEST_PROFILE,
    PORTFOLIO_BACKTEST_VERSION,
    SELECTION_RANKING,
    SWING_PORTFOLIO_BACKTEST_PROFILE,
    PortfolioBacktestConfig,
)
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    SKIP_INSUFFICIENT_CASH,
    SKIP_MAX_POSITIONS,
    SKIP_PORTFOLIO_RISK_LIMIT,
    SKIP_SAME_SYMBOL_ALREADY_OPEN,
    SKIP_ZERO_QUANTITY,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
    OpenPosition,
    PortfolioBacktestEngineConfig,
    build_report_tables,
    calculate_portfolio_quantity,
    determine_exit,
    evaluate_admission,
    load_frozen_opportunities,
    rank_opportunities,
    run_pilot_validation,
    selection_lookahead_violations,
    selection_priority,
    simulate_portfolio,
    write_backtest_artifacts,
)
from app.risk.risk_config import CURRENT_RISK_STRUCTURE_CONFIG_HASH, CURRENT_RISK_STRUCTURE_VERSION
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import (
    CURRENT_STRATEGY_OUTCOME_VERSION,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    outcome_input_hash_checks,
    outcome_input_hashes,
    resolve_current_strategy_outcome_dataset,
)
from app.strategy.scoring.score_baseline import CURRENT_STRATEGY_SCORE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_backtest_identity_and_config_hash_are_reproducible() -> None:
    first = PortfolioBacktestConfig()
    second = PortfolioBacktestConfig()
    assert first.backtest_version == PORTFOLIO_BACKTEST_VERSION
    assert first.backtest_profile == SWING_PORTFOLIO_BACKTEST_PROFILE
    assert first.config_hash() == second.config_hash()
    assert len(first.config_hash()) == 16
    assert FUTURE_INTRADAY_BACKTEST_PROFILE != first.backtest_profile


def test_fixed_contract_values_and_ranking_are_locked() -> None:
    config = PortfolioBacktestConfig()
    assert config.initial_capital_rupees == Decimal("100000")
    assert config.max_concurrent_positions == 4
    assert config.max_risk_per_trade_pct == Decimal("1.00")
    assert config.max_total_open_risk_pct == Decimal("4.00")
    assert config.max_hold_sessions == 4
    assert config.ambiguity_policy == "CONSERVATIVE_STOP_FIRST"
    assert config.selection_ranking == SELECTION_RANKING
    assert config.transaction_cost_status == config.slippage_status == "NOT_MODELED"


def test_frozen_opportunity_pool_and_all_input_hashes() -> None:
    path = resolve_current_strategy_outcome_dataset(DATA_DIR)
    rows, _ = load_frozen_opportunities(path)
    assert len(rows) == 3296
    assert file_sha256(path) == STRATEGY_OUTCOME_V1_DATASET_HASH
    assert all(row["outcome_version"] == CURRENT_STRATEGY_OUTCOME_VERSION for row in rows)
    assert all(row["score_version"] == CURRENT_STRATEGY_SCORE_VERSION for row in rows)
    assert all(row["risk_version"] == CURRENT_RISK_STRUCTURE_VERSION for row in rows)
    assert all(row["risk_config_hash"] == CURRENT_RISK_STRUCTURE_CONFIG_HASH for row in rows)
    assert all(outcome_input_hash_checks(outcome_input_hashes(DATA_DIR)).values())


def test_ranking_is_deterministic_and_uses_all_tie_breaks() -> None:
    lower_rr = opportunity("ZZZ", score="85", rr="2")
    higher_rr = opportunity("BBB", score="85", rr="3")
    alphabetic = opportunity("AAA", score="85", rr="3")
    ranked = rank_opportunities([lower_rr, higher_rr, alphabetic])
    assert [row["symbol"] for row in ranked] == ["AAA", "BBB", "ZZZ"]
    assert [row["_selection_rank"] for row in ranked] == [1, 2, 3]
    assert all(row["_selection_priority_tuple"] for row in ranked)


def test_future_outcome_mutations_cannot_change_selection() -> None:
    first = opportunity("AAA", score="84")
    second = opportunity("BBB", score="83")
    baseline = [row["symbol"] for row in rank_opportunities([first, second])]
    changed = copy.deepcopy(second)
    changed.update(
        {
            "first_touch_outcome": "TARGET_FIRST",
            "mfe_r_4": "999",
            "mae_r_4": "999",
            "close_return_pct_4": "999",
            "high_2": "99999",
            "low_2": "0.01",
        }
    )
    assert [row["symbol"] for row in rank_opportunities([first, changed])] == baseline
    changed["raw_strategy_score"] = "85"
    assert [row["symbol"] for row in rank_opportunities([first, changed])] == ["BBB", "AAA"]
    assert selection_lookahead_violations() == 0


def test_future_price_path_changes_exit_not_earlier_admission() -> None:
    baseline = opportunity("AAA")
    changed = copy.deepcopy(baseline)
    changed["high_2"] = "121"
    first = simulate_portfolio(opportunities=[baseline], trading_dates=session_dates(), config=PortfolioBacktestConfig())
    second = simulate_portfolio(opportunities=[changed], trading_dates=session_dates(), config=PortfolioBacktestConfig())
    assert first["trades"][0]["trade_id"] == second["trades"][0]["trade_id"]
    assert first["trades"][0]["selection_rank"] == second["trades"][0]["selection_rank"] == 1
    assert first["trades"][0]["exit_reason"] == TIME_EXIT
    assert second["trades"][0]["exit_reason"] == TARGET_EXIT


def test_quantity_uses_current_equity_and_available_cash() -> None:
    config = PortfolioBacktestConfig()
    sizing = calculate_portfolio_quantity(
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
        portfolio_equity=Decimal("120000"),
        available_cash=Decimal("10000"),
        config=config,
    )
    assert sizing["risk_budget"] == Decimal("1200")
    assert sizing["quantity_by_risk"] == 240
    assert sizing["quantity_by_cash"] == 100
    assert sizing["quantity"] == 100
    assert sizing["planned_risk"] == Decimal("500")


def test_same_symbol_slot_cash_and_risk_constraints_have_exact_reasons() -> None:
    config = PortfolioBacktestConfig()
    row = opportunity("AAA")
    same = [fake_position("AAA", "500")]
    assert evaluate_admission(row=row, open_positions=same, available_cash=Decimal("100000"), portfolio_equity=Decimal("100000"), config=config)[0] == SKIP_SAME_SYMBOL_ALREADY_OPEN
    full = [fake_position(f"P{i}", "500") for i in range(4)]
    assert evaluate_admission(row=row, open_positions=full, available_cash=Decimal("100000"), portfolio_equity=Decimal("100000"), config=config)[0] == SKIP_MAX_POSITIONS
    expensive = opportunity("CASH", entry="200000", stop="199000", target="202000")
    assert evaluate_admission(row=expensive, open_positions=[], available_cash=Decimal("100000"), portfolio_equity=Decimal("100000"), config=config)[0] == SKIP_INSUFFICIENT_CASH
    risk_full = [fake_position("RISK", "4000")]
    assert evaluate_admission(row=row, open_positions=risk_full, available_cash=Decimal("100000"), portfolio_equity=Decimal("100000"), config=config)[0] == SKIP_PORTFOLIO_RISK_LIMIT
    zero = opportunity("ZERO", entry="100000", stop="1", target="200000")
    assert evaluate_admission(row=zero, open_positions=[], available_cash=Decimal("100000"), portfolio_equity=Decimal("100000"), config=config)[0] == SKIP_ZERO_QUANTITY


def test_target_stop_time_and_ambiguity_exit_policies() -> None:
    config = PortfolioBacktestConfig()
    target = opportunity("TARGET", highs=("121", "110", "110", "110"))
    stop = opportunity("STOP", lows=("89", "99", "99", "99"))
    ambiguous = opportunity("AMB", highs=("121", "110", "110", "110"), lows=("89", "99", "99", "99"))
    neither = opportunity("TIME")
    assert determine_exit(target, "2024-01-02", config)["reason"] == TARGET_EXIT
    assert determine_exit(stop, "2024-01-02", config)["reason"] == STOP_EXIT
    event = determine_exit(ambiguous, "2024-01-02", config)
    assert event["reason"] == AMBIGUOUS_SAME_BAR_EXIT
    assert event["price"] == Decimal("90")
    assert event["ambiguity"] is True
    assert determine_exit(neither, "2024-01-05", config)["reason"] == TIME_EXIT


def test_entry_day_exit_and_gross_pnl_are_accounted() -> None:
    result = simulate_portfolio(
        opportunities=[opportunity("AAA", highs=("121", "110", "110", "110"))],
        trading_dates=session_dates(),
        config=PortfolioBacktestConfig(),
    )
    trade = result["trades"][0]
    assert trade["holding_sessions"] == 1
    assert trade["exit_reason"] == TARGET_EXIT
    assert trade["quantity"] == 100
    assert trade["gross_pnl"] == Decimal("2000")
    assert trade["realized_r_multiple"] == Decimal("2")
    assert result["daily"][0]["closing_cash"] == Decimal("102000")


def test_daily_close_marking_and_portfolio_equity() -> None:
    result = simulate_portfolio(
        opportunities=[opportunity("AAA", closes=("105", "106", "107", "104"))],
        trading_dates=session_dates(),
        config=PortfolioBacktestConfig(),
    )
    first_day = result["daily"][0]
    assert first_day["closing_cash"] == Decimal("90000")
    assert first_day["market_value_open"] == Decimal("10500")
    assert first_day["portfolio_equity"] == Decimal("100500")
    assert first_day["unrealized_pnl"] == Decimal("500")


def test_max_four_positions_and_stable_same_day_selection() -> None:
    rows = [opportunity(f"S{i}", score=str(85 - (i % 3))) for i in range(5)]
    result = simulate_portfolio(opportunities=rows, trading_dates=session_dates(), config=PortfolioBacktestConfig())
    assert result["entered"] == 4
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["skip_reason"] == SKIP_MAX_POSITIONS
    assert max(row["peak_open_positions"] for row in result["daily"]) == 4
    assert result["invariants"]["max_position_violations"] == 0


def test_repeated_symbol_is_skipped_only_while_position_is_open() -> None:
    first = opportunity("AAA")
    second = opportunity(
        "AAA",
        decision_date="2024-01-02",
        entry_date="2024-01-03",
        dates=("2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
    )
    result = simulate_portfolio(
        opportunities=[first, second],
        trading_dates=("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
        config=PortfolioBacktestConfig(),
    )
    assert result["entered"] == 1
    assert result["skipped"][0]["skip_reason"] == SKIP_SAME_SYMBOL_ALREADY_OPEN
    assert result["invariants"]["same_symbol_duplicate_violations"] == 0


def test_intraday_exit_cash_is_not_reused_for_same_open_entries() -> None:
    first = opportunity(
        "AAA",
        entry="100",
        stop="99",
        target="101",
        highs=("100.5", "102", "102", "102"),
        lows=("99.5", "99.5", "99.5", "99.5"),
    )
    second = opportunity(
        "BBB",
        decision_date="2024-01-02",
        entry_date="2024-01-03",
        dates=("2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
        entry="1000",
        stop="999",
        target="1002",
    )
    result = simulate_portfolio(
        opportunities=[first, second],
        trading_dates=("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
        config=PortfolioBacktestConfig(),
    )
    assert result["skipped"][0]["symbol"] == "BBB"
    assert result["skipped"][0]["skip_reason"] == SKIP_INSUFFICIENT_CASH
    assert result["trades"][0]["exit_date"] == "2024-01-03"
    assert result["daily"][1]["opening_cash"] == Decimal("0")
    assert result["daily"][1]["closing_cash"] == Decimal("101000")


def test_cash_position_risk_and_linkage_invariants_reconcile() -> None:
    result = simulate_portfolio(
        opportunities=[opportunity("AAA"), opportunity("BBB", score="84")],
        trading_dates=session_dates(),
        config=PortfolioBacktestConfig(),
    )
    assert result["all_invariants_valid"] is True
    assert not any(result["invariants"].values())
    assert len({trade["source_key"] for trade in result["trades"]}) == 2


def test_real_chronological_pilot_covers_all_fourteen_cases() -> None:
    rows, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(DATA_DIR))
    pilot = run_pilot_validation(rows, PortfolioBacktestConfig())
    assert pilot["passed"] is True
    assert [row["pilot_case"] for row in pilot["rows"]] == list("ABCDEFGHIJKLMN")
    assert pilot["real_case_count"] >= 10
    assert all(row["result"] == "PASS" for row in pilot["rows"])


def test_report_and_bulk_artifacts_are_generated(tmp_path: Path) -> None:
    config = PortfolioBacktestConfig()
    opportunities = [opportunity("AAA")]
    simulation = simulate_portfolio(opportunities=opportunities, trading_dates=session_dates(), config=config)
    pilot = {"passed": True, "rows": [{"pilot_case": "A", "result": "PASS"}]}
    tables = build_report_tables(simulation, opportunities, pilot, config)
    engine = PortfolioBacktestEngineConfig(data_dir=tmp_path)
    paths = write_backtest_artifacts(engine, simulation, tables)
    assert engine.trades_path in paths
    assert engine.daily_path in paths
    assert engine.skipped_path in paths
    assert all(path.exists() for path in paths)
    with gzip.open(engine.trades_path, "rt", encoding="utf-8") as file:
        assert "trade_id" in file.readline()


def test_build_cli_uses_registered_contract_and_ignored_output_paths() -> None:
    source = (REPO_ROOT / "backend/scripts/build_portfolio_backtest.py").read_text(encoding="utf-8")
    assert "get_portfolio_backtest_config" in source
    assert "get_current_portfolio_backtest_version" in source
    assert "get_current_portfolio_backtest_profile" in source
    assert "portfolio_trades_v1.csv.gz" not in source
    engine = PortfolioBacktestEngineConfig(data_dir=DATA_DIR)
    assert engine.trades_path == DATA_DIR / "research/backtests/swing/portfolio/v1/portfolio_trades_v1.csv.gz"


def test_generated_full_baseline_ledgers_match_summary_and_contract() -> None:
    engine = PortfolioBacktestEngineConfig(data_dir=DATA_DIR)
    summary = json.loads(engine.report_path("summary.json").read_text(encoding="utf-8"))
    with gzip.open(engine.trades_path, "rt", encoding="utf-8", newline="") as file:
        trades = list(csv.DictReader(file))
    with gzip.open(engine.daily_path, "rt", encoding="utf-8", newline="") as file:
        daily = list(csv.DictReader(file))
    with gzip.open(engine.skipped_path, "rt", encoding="utf-8", newline="") as file:
        skipped = list(csv.DictReader(file))
    assert summary["ready_for_review"] is True
    assert summary["opportunity_pool"]["mechanically_valid_opportunities_considered"] == 3296
    assert len(trades) == summary["opportunity_pool"]["actual_portfolio_trades_entered"] == 728
    assert len(skipped) == summary["opportunity_pool"]["opportunities_skipped"] == 2568
    assert len(trades) + len(skipped) == 3296
    assert daily[0]["date"] == summary["portfolio_metrics"]["start_date"]
    assert daily[-1]["date"] == summary["portfolio_metrics"]["end_date"]
    assert daily[-1]["portfolio_equity"] == summary["portfolio_metrics"]["ending_equity"]
    assert len({trade["trade_id"] for trade in trades}) == len(trades)
    assert all(trade["backtest_version"] == PORTFOLIO_BACKTEST_VERSION for trade in trades)
    assert all(trade["transaction_cost_status"] == "NOT_MODELED" for trade in trades)
    assert all(trade["slippage_status"] == "NOT_MODELED" for trade in trades)
    assert all(int(row["open_positions_end"]) <= 4 for row in daily)
    assert all(Decimal(row["closing_cash"]) >= 0 for row in daily)
    yearly = list(csv.DictReader(engine.report_path("yearly.csv").open("r", encoding="utf-8", newline="")))
    assert all(
        Decimal(current["starting_equity"]) == Decimal(previous["ending_equity"])
        for previous, current in zip(yearly, yearly[1:])
    )


def fake_position(symbol: str, planned_risk: str) -> OpenPosition:
    return OpenPosition(
        trade={"trade_id": f"FAKE-{symbol}", "symbol": symbol, "quantity": 1, "initial_planned_risk": planned_risk},
        source={},
        last_mark=Decimal("1"),
    )


def session_dates() -> tuple[str, ...]:
    return ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05")


def opportunity(
    symbol: str,
    *,
    decision_date: str = "2024-01-01",
    entry_date: str = "2024-01-02",
    dates: tuple[str, ...] = ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"),
    entry: str = "100",
    stop: str = "90",
    target: str = "120",
    score: str = "85",
    rr: str = "2",
    highs: tuple[str, ...] = ("110", "110", "110", "110"),
    lows: tuple[str, ...] = ("99", "99", "99", "99"),
    closes: tuple[str, ...] = ("100", "101", "102", "104"),
) -> dict[str, str]:
    row = {
        "decision_date": decision_date,
        "symbol": symbol,
        "score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "score_profile": "SWING_DAILY_EOD_V1",
        "score_config_hash": "e257c76b90e25cb7",
        "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "outcome_version": CURRENT_STRATEGY_OUTCOME_VERSION,
        "outcome_profile": "SWING_DAILY_OUTCOME_V1",
        "outcome_config_hash": "2ea683a8f8b5b041",
        "outcome_cohort": "HISTORICAL_ELIGIBLE_OPPORTUNITY",
        "source_scoring_disposition": "ENTRY_ELIGIBLE",
        "primary_evaluation_eligible": "True",
        "entry_valid": "True",
        "entry_recheck_status": "ENTRY_VALID",
        "forward_data_safe": "True",
        "entry_model": "NEXT_SESSION_OPEN",
        "next_session_date": entry_date,
        "hypothetical_entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "target_basis": "R_MULTIPLE_2R_RESEARCH_REFERENCE",
        "raw_strategy_score": score,
        "effective_reward_risk": rr,
        "setup_quality": "STRONG",
        "candidate_category": "BOTH_ELIGIBLE",
        "regime_state": "BULLISH",
        "momentum_points": "20",
        "rvol_points": "15",
        "relative_strength_points": "15",
        "position_notional": "10000",
        "first_touch_outcome": "NEITHER_WITHIN_HORIZON",
        "first_target_session": "",
        "first_stop_session": "",
        "mfe_r_4": "1",
        "mae_r_4": "0.5",
        "close_return_pct_4": "4",
    }
    for index, trading_date in enumerate(dates, start=1):
        row[f"session_date_{index}"] = trading_date
        row[f"open_{index}"] = entry
        row[f"high_{index}"] = highs[index - 1]
        row[f"low_{index}"] = lows[index - 1]
        row[f"close_{index}"] = closes[index - 1]
    return row
