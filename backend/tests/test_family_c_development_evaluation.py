from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_c_breakout_continuation import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    FamilyCBar,
)
from app.research.strategy.family_c_development_evaluation import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXECUTABLE_MODE,
    IDEALIZED_MODE,
    REPORT_NAMES,
    _bar_path_available,
    _size_position,
    accounting_data_integrity,
    evaluate_control,
    evaluate_treatment,
    expectancy,
    map_family_result,
    next_research_stage,
    position_win_rate,
    profit_factor,
    quantile,
    simulate_strategy,
    summarize_simulation,
    verify_freeze_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    REPO_ROOT
    / "data/research/strategy_families/family_c/v1/development_evaluation"
)


def _family_c_bar(trading_date: date, price: str) -> FamilyCBar:
    value = Decimal(price)
    return FamilyCBar(
        trading_date=trading_date,
        symbol="TEST",
        isin="INE000000001",
        open_price=value,
        high_price=value * Decimal("1.02"),
        low_price=value * Decimal("0.98"),
        close_price=value * Decimal("1.01"),
        volume=Decimal("100000"),
        usability_status="ADJUSTED_READY",
        methodology_version="TEST",
    )


def _synthetic_inputs(two_signals: bool = False):
    sessions = [date(2022, 1, 1) + timedelta(days=index) for index in range(30)]
    bars = {
        session: {"TEST": _family_c_bar(session, str(100 + index))}
        for index, session in enumerate(sessions)
    }
    signal_rows = [
        {
            "decision_date": sessions[0],
            "symbol": "TEST",
            "isin": "INE000000001",
            "point_in_time_member": True,
            "close": Decimal("100"),
            "breakout_strength_pct": Decimal("0.02"),
            "compression_range_pct": Decimal("0.07"),
            "formation_volume_ratio": Decimal("1.60"),
            "control_signal": True,
            "c001_signal": True,
            "c002_signal": True,
        }
    ]
    if two_signals:
        signal_rows.append({**signal_rows[0], "decision_date": sessions[1]})
    return sessions, bars, signal_rows


def _metrics(**overrides):
    value = {
        "net_CAGR": Decimal("0.10"),
        "net_profit_factor": Decimal("1.20"),
        "net_expectancy": Decimal("0.01"),
        "max_drawdown": Decimal("0.20"),
        "closed_positions": 120,
        "yearly_returns": {
            "2022": Decimal("0.05"),
            "2023": Decimal("0.02"),
            "2024": Decimal("0.03"),
        },
        "position_win_rate": Decimal("0.55"),
        "turnover": Decimal("5"),
        "normalized_cost_drag": Decimal("0.02"),
        "accounting_data_integrity": {"status": "PASS"},
    }
    value.update(overrides)
    return value


def test_exact_command_and_frozen_hash_gate() -> None:
    assert COMMAND_VERSION == "FAMILY_C_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "BREAKOUT_CONTINUATION_DEVELOPMENT_V1"
    gate = verify_freeze_gate(REPO_ROOT)
    assert gate["status"] == "VERIFIED"
    assert len(gate["checks"]) == 14
    assert all(gate["checks"].values())
    assert gate["config"]["family_c_config_hash"] == EXPECTED_FAMILY_C_CONFIG_HASH
    assert gate["criteria"]["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert gate["registry"]["control"]["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    for row in gate["registry"]["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]
        assert row["parameter_hash"] == expected["parameter_hash"]
        assert row["preregistration_hash"] == expected["preregistration_hash"]


def test_terminal_path_is_excluded_without_2025_access() -> None:
    sessions = [date(2024, 12, 15) + timedelta(days=index) for index in range(17)]
    bars = {
        session: {"TEST": _family_c_bar(session, "100")}
        for session in sessions
        if session <= date(2024, 12, 31)
    }
    chronology = {
        "entry_date": sessions[6],
        "holding_dates": tuple(sessions[6:16]),
        "exit_date": date(2025, 1, 1),
    }
    available, reason = _bar_path_available("TEST", chronology, bars)
    assert available is False
    assert reason == "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"


def test_executable_sizing_is_whole_share_5_percent_and_cash_safe() -> None:
    result = _size_position(
        EXECUTABLE_MODE,
        STARTING_CAPITAL,
        STARTING_CAPITAL,
        Decimal("333"),
        date(2022, 1, 2),
    )
    assert STARTING_CAPITAL == Decimal("500000")
    assert TARGET_NOTIONAL_FRACTION == Decimal("0.05")
    assert result["intended_notional"] == Decimal("25000.00")
    assert result["quantity"] == Decimal("75")
    assert result["quantity"] == result["quantity"].to_integral_value()
    assert result["actual_notional"] + result["buy_cost"] <= STARTING_CAPITAL


def test_idealized_mode_uses_fractional_percentage_position() -> None:
    result = _size_position(
        IDEALIZED_MODE,
        STARTING_CAPITAL,
        STARTING_CAPITAL,
        Decimal("333"),
        date(2022, 1, 2),
    )
    assert result["intended_notional"] == Decimal("25000.00")
    assert result["quantity"] != result["quantity"].to_integral_value()
    assert result["actual_notional"] + result["buy_cost"] <= STARTING_CAPITAL


def test_simulation_uses_next_open_ten_holds_next_open_exit_and_costs() -> None:
    sessions, bars, signal_rows = _synthetic_inputs()
    simulation = simulate_strategy(
        experiment_id="CONTROL-C-000",
        experiment_name="PURE_20D_CLOSE_BREAKOUT_V1",
        signal_field="control_signal",
        mode=EXECUTABLE_MODE,
        signal_rows=signal_rows,
        sessions=sessions,
        bars=bars,
    )
    assert simulation["closed_positions"] == 1
    position = simulation["positions"][0]
    assert position["formation_date"] == sessions[0].isoformat()
    assert position["entry_date"] == sessions[1].isoformat()
    assert position["holding_sessions"] == HOLDING_SESSIONS == 10
    assert position["exit_date"] == sessions[11].isoformat()
    assert position["transaction_costs"] > 0
    assert position["actual_shares"] == position["actual_shares"].to_integral_value()
    assert simulation["total_transaction_costs"] > 0


def test_one_position_per_symbol_and_no_pyramid() -> None:
    sessions, bars, signal_rows = _synthetic_inputs(two_signals=True)
    simulation = simulate_strategy(
        experiment_id="CONTROL-C-000",
        experiment_name="PURE_20D_CLOSE_BREAKOUT_V1",
        signal_field="control_signal",
        mode=EXECUTABLE_MODE,
        signal_rows=signal_rows,
        sessions=sessions,
        bars=bars,
    )
    assert simulation["already_open_rejections"] == 1
    assert simulation["closed_positions"] == 1
    assert max(row["open_positions"] for row in simulation["ledger"]) == 1
    assert MAX_CONCURRENT_POSITIONS == 20


def test_profit_factor_expectancy_win_rate_and_quantiles() -> None:
    assert profit_factor([Decimal("10"), Decimal("-4"), Decimal("6")]) == Decimal("4")
    assert expectancy([Decimal("0.1"), Decimal("-0.05")]) == Decimal("0.025")
    assert position_win_rate([Decimal("0.1"), Decimal("-0.05"), Decimal("0")]) == Decimal("1") / Decimal("3")
    assert quantile([Decimal("1"), Decimal("2"), Decimal("3")], Decimal("0.5")) == Decimal("2")


def test_mfe_mae_and_accounting_reconcile() -> None:
    sessions, bars, signal_rows = _synthetic_inputs()
    simulation = simulate_strategy(
        experiment_id="CONTROL-C-000",
        experiment_name="PURE_20D_CLOSE_BREAKOUT_V1",
        signal_field="control_signal",
        mode=EXECUTABLE_MODE,
        signal_rows=signal_rows,
        sessions=sessions,
        bars=bars,
    )
    position = simulation["positions"][0]
    assert position["MFE_pct"] > position["MAE_pct"]
    assert position["return_after_1_session"] is not None
    assert position["return_after_3_sessions"] is not None
    assert position["return_after_5_sessions"] is not None
    assert position["return_after_10_sessions"] is not None
    assert accounting_data_integrity(simulation)["status"] == "PASS"
    assert all(row["equity_reconciled"] for row in simulation["ledger"])


def test_control_viability_and_fatal_conditions_are_exact() -> None:
    viable = evaluate_control(_metrics())
    assert viable["CONTROL_VIABLE"] is True
    assert viable["CONTROL_FAILED"] is False
    fatal = evaluate_control(
        _metrics(net_CAGR=Decimal("-0.05"), closed_positions=49)
    )
    assert fatal["CONTROL_FAILED"] is True
    assert fatal["fatal_conditions"]["NET_CAGR_AT_OR_BELOW_MINUS_5_PERCENT"] is True
    assert fatal["fatal_conditions"]["FEWER_THAN_50_POSITIONS"] is True


def test_treatment_criteria_A_G_and_quality_H_K() -> None:
    control = _metrics()
    treatment = _metrics(
        net_CAGR=Decimal("0.11"),
        net_profit_factor=Decimal("1.30"),
        net_expectancy=Decimal("0.012"),
        max_drawdown=Decimal("0.17"),
        position_win_rate=Decimal("0.61"),
        turnover=Decimal("4"),
        normalized_cost_drag=Decimal("0.015"),
    )
    result = evaluate_treatment(treatment, control)
    assert all(result["criteria_A_G"].values())
    assert all(result["quality_H_K"].values())
    assert result["classification"] == "STRONGLY_SUPPORTED"


def test_treatment_classification_partial_and_failed() -> None:
    control = _metrics()
    partial = evaluate_treatment(
        _metrics(
            net_CAGR=Decimal("0.08"),
            net_profit_factor=Decimal("1.06"),
            net_expectancy=Decimal("0.005"),
            position_win_rate=Decimal("0.54"),
        ),
        control,
    )
    assert partial["classification"] == "PARTIALLY_SUPPORTED"
    failed = evaluate_treatment(_metrics(closed_positions=49), control)
    assert failed["classification"] == "FAILED"
    assert failed["fatal_conditions"]["FATAL_SAMPLE_FAILURE"] is True


def test_family_mapping_and_next_stage_are_frozen() -> None:
    assert map_family_result(True, "STRONGLY_SUPPORTED", "PARTIALLY_SUPPORTED") == "STRONG_SUPPORT"
    assert map_family_result(True, "SUPPORTED", "PARTIALLY_SUPPORTED") == "SUPPORT"
    assert map_family_result(True, "PARTIALLY_SUPPORTED", "FAILED") == "MIXED"
    assert map_family_result(True, "PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED") == "WEAK"
    assert map_family_result(False, "FAILED", "FAILED") == "FAILED"
    assert next_research_stage("SUPPORT", ["SUPPORTED", "PARTIALLY_SUPPORTED"]) == "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
    assert next_research_stage("WEAK", ["PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED"]) == "CONTINUE_CONTROLLED_DEVELOPMENT"
    assert next_research_stage("FAILED", ["FAILED", "FAILED"]) == "STOP_FAMILY_C"


def test_summary_metrics_use_executable_ledger_and_high_win_rate_flag() -> None:
    sessions, bars, signal_rows = _synthetic_inputs()
    simulation = simulate_strategy(
        experiment_id="CONTROL-C-000",
        experiment_name="PURE_20D_CLOSE_BREAKOUT_V1",
        signal_field="control_signal",
        mode=EXECUTABLE_MODE,
        signal_rows=signal_rows,
        sessions=sessions,
        bars=bars,
    )
    summary = summarize_simulation(simulation)
    assert summary["starting_equity"] == STARTING_CAPITAL
    assert summary["closed_positions"] == 1
    assert summary["maximum_concurrent_positions"] <= 20
    assert summary["accounting_data_integrity"]["status"] == "PASS"
    assert summary["HIGH_WIN_RATE_FLAG"] in {"YES", "NO"}


def test_cost_model_is_unchanged() -> None:
    gate = verify_freeze_gate(REPO_ROOT)
    assert gate["config"]["costs"] == {
        "model": "INDIA_EQUITY_COST_MODEL_V1",
        "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "scenario": "COST-SCENARIO-002",
        "slippage_bps_per_side": "5",
    }
    assert EXPECTED_COST_CONFIG_HASH


def test_generated_result_hashes_registry_reports_and_prohibitions() -> None:
    assert len(REPORT_NAMES) == 14
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).is_file()
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_dev_v1_summary.json").read_text(
            encoding="utf-8"
        )
    )
    for experiment_id, hash_field in (
        ("CONTROL-C-000", "control_c_000_result_hash"),
        ("BRK-C-001", "brk_c_001_result_hash"),
        ("BRK-C-002", "brk_c_002_result_hash"),
    ):
        result = summary["results"][experiment_id]
        assert canonical_hash({key: value for key, value in result.items() if key != hash_field}) == result[hash_field]
    registry = json.loads(
        (OUTPUT_ROOT / "comparison/family_c_development_registry_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(row["status"] == "DEVELOPMENT_EVALUATED" for row in registry["experiments"])
    assert registry["experiments"][0]["preregistration_hash"] == EXPECTED_EXPERIMENT_HASHES["BRK-C-001"]["preregistration_hash"]
    assert registry["experiments"][1]["preregistration_hash"] == EXPECTED_EXPERIMENT_HASHES["BRK-C-002"]["preregistration_hash"]
    assert canonical_hash({key: value for key, value in registry.items() if key != "family_c_development_registry_hash"}) == registry["family_c_development_registry_hash"]
    assert summary["governance"]["validation_accessed"] is False
    assert summary["governance"]["stop_added"] is False
    assert summary["governance"]["target_added"] is False
    assert summary["governance"]["combined_filter_tested"] is False
    assert summary["immutability"]["parameter_mutations"] == 0
    assert summary["immutability"]["success_criteria_mutations"] == 0
    assert summary["security"]["live_orders"] == 0


def test_all_required_output_directories_and_documentation_exist() -> None:
    for directory in (
        "control", "brk_c_001", "brk_c_002", "comparison", "positions", "ledgers", "diagnostics"
    ):
        assert (OUTPUT_ROOT / directory).is_dir()
    assert (REPO_ROOT / "docs/strategy-family-c-development-evaluation-v1.md").is_file()
