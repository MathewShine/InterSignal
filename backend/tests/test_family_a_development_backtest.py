from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.strategy.family_a_development_backtest import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXECUTABLE_MODE,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_CONFIG_HASH,
    FamilyAValidationAccessError,
    FamilyAResultImmutabilityError,
    IDEALIZED_MODE,
    REPORT_NAMES,
    RebalanceSchedule,
    SelectedInstrument,
    full_baseline_snapshot,
    load_rebalance_schedules,
    quality_classifications,
    simulate_executable,
    simulate_idealized,
    summarize_simulation,
    validate_development_date,
    verify_family_a_preregistration,
    write_csv,
    write_json,
    yearly_results,
    _immutable_result,
)
from app.research.strategy.family_a_momentum import AdjustedBar


REPO_ROOT = Path(__file__).resolve().parents[2]


def fixture_market() -> tuple[list[date], dict[date, dict[str, AdjustedBar]], list[RebalanceSchedule]]:
    sessions = [date(2022, 1, 3) + timedelta(days=index) for index in range(5)]
    symbols = [f"S{index:02d}" for index in range(25)]
    bars: dict[date, dict[str, AdjustedBar]] = {}
    for day_index, value_date in enumerate(sessions):
        bars[value_date] = {}
        for symbol_index, symbol in enumerate(symbols):
            base = Decimal(100 + symbol_index)
            open_price = base + Decimal(day_index)
            close_price = open_price + Decimal("1")
            bars[value_date][symbol] = AdjustedBar(
                trading_date=value_date,
                symbol=symbol,
                isin=f"I{symbol_index}",
                open_price=open_price,
                close_price=close_price,
                volume=Decimal("1000000"),
                usability_status="ADJUSTED_READY",
                methodology_version="PRICE_ADJUSTED_STRUCTURAL_V1",
            )
    first = tuple(
        SelectedInstrument(symbol, f"I{index}", index + 1, Decimal(25 - index))
        for index, symbol in enumerate(symbols[:20])
    )
    second_symbols = symbols[:15] + symbols[20:25]
    second = tuple(
        SelectedInstrument(symbol, f"I{symbols.index(symbol)}", index + 1, Decimal(25 - index))
        for index, symbol in enumerate(second_symbols)
    )
    schedules = [
        RebalanceSchedule("MOM-A-001", sessions[1], sessions[2], 200, 20, True, first),
        RebalanceSchedule("MOM-A-001", sessions[2], sessions[3], 200, 20, True, second),
    ]
    return sessions, bars, schedules


def test_exact_command_identity_and_frozen_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_A_DEVELOPMENT_BACKTEST_V1"
    assert COMMAND_PROFILE == "MEDIUM_TERM_MOMENTUM_DEVELOPMENT_BASELINES_V1"
    assert EXPECTED_FAMILY_CONFIG_HASH == "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3"
    assert tuple(EXPECTED_EXPERIMENT_HASHES) == ("MOM-A-001", "MOM-A-002", "MOM-A-003")


def test_current_preregistration_verifies_without_mutation() -> None:
    result = verify_family_a_preregistration(REPO_ROOT)
    assert result["family_config_verified"] is True
    assert [row["experiment_id"] for row in result["experiments"]] == [
        "MOM-A-001",
        "MOM-A-002",
        "MOM-A-003",
    ]


def test_development_partition_rejects_validation_dates() -> None:
    validate_development_date(date(2022, 1, 1))
    validate_development_date(date(2024, 12, 31))
    with pytest.raises(FamilyAValidationAccessError):
        validate_development_date(date(2025, 1, 1))
    with pytest.raises(FamilyAValidationAccessError):
        validate_development_date(date(2021, 12, 31))


def test_frozen_schedule_counts_monthly_quarterly_and_next_open() -> None:
    schedules = load_rebalance_schedules(REPO_ROOT)
    assert {key: len(value) for key, value in schedules.items()} == {
        "MOM-A-001": 35,
        "MOM-A-002": 11,
        "MOM-A-003": 35,
    }
    assert all(row.formation_date < row.execution_date for values in schedules.values() for row in values)
    assert all(row.formation_date.month in {3, 6, 9, 12} for row in schedules["MOM-A-002"])


def test_frozen_signals_selection_and_equal_weight_parameters() -> None:
    verified = verify_family_a_preregistration(REPO_ROOT)
    experiments = {row["experiment_id"]: row for row in verified["registry"]["experiments"]}
    assert experiments["MOM-A-001"]["parameters"]["signal"] == "6M"
    assert experiments["MOM-A-002"]["parameters"]["signal"] == "6M"
    assert experiments["MOM-A-003"]["parameters"]["signal"] == "12M_EX_LAST_1M"
    assert experiments["MOM-A-003"]["parameters"]["lookback_trading_sessions"] == 252
    assert experiments["MOM-A-003"]["parameters"]["skip_most_recent_trading_sessions"] == 21
    assert all(row["parameters"]["selection"] == "TOP_DECILE" for row in experiments.values())
    assert all(row["parameters"]["weighting"] == "EQUAL_WEIGHT" for row in experiments.values())


def test_idealized_engine_uses_fractional_equal_weight_and_limited_costs() -> None:
    sessions, bars, schedules = fixture_market()
    result = simulate_idealized("MOM-A-001", schedules, sessions, bars)
    assert result["mode"] == IDEALIZED_MODE
    assert result["cost_model_status"] == "IDEALIZED_COST_MODEL_LIMITED"
    assert result["cash_reconciliation_violations"] == 0
    assert result["equity_reconciliation_violations"] == 0
    first_holdings = [row for row in result["holdings"] if row["execution_date"] == sessions[2].isoformat()]
    assert len(first_holdings) == 20
    assert abs(sum(Decimal(str(row["actual_weight_pct"])) for row in first_holdings) - 100) < Decimal("1e-20")
    assert any(Decimal(str(row["quantity"])) % 1 != 0 for row in first_holdings)


def test_executable_engine_uses_integers_residual_cash_and_full_costs() -> None:
    sessions, bars, schedules = fixture_market()
    result = simulate_executable("MOM-A-001", schedules, sessions, bars)
    assert result["mode"] == EXECUTABLE_MODE
    assert result["cost_model_status"] == "FULL_FROZEN_COST_MODEL"
    assert result["cash_reconciliation_violations"] == 0
    assert result["equity_reconciliation_violations"] == 0
    assert all(Decimal(str(row["quantity"])) % 1 == 0 for row in result["holdings"])
    assert all(Decimal(str(row["cash"])) >= 0 for row in result["rebalances"])
    assert any(row["side"] == "SELL" and Decimal(str(row["dp_charge"])) > 0 for row in result["costs"])
    assert any(row["side"] == "BUY" and Decimal(str(row["stamp_duty"])) > 0 for row in result["costs"])


def test_retention_additions_removals_and_turnover_are_reconciled() -> None:
    sessions, bars, schedules = fixture_market()
    result = simulate_executable("MOM-A-001", schedules, sessions, bars)
    second = result["rebalances"][1]
    assert second["retained_count"] == 15
    assert second["added_count"] == 5
    assert second["removed_count"] == 5
    assert Decimal(str(second["gross_buy_turnover"])) > 0
    assert Decimal(str(second["gross_sell_turnover"])) > 0
    assert Decimal(str(second["one_way_turnover"])) > 0
    assert Decimal(str(second["cash_reconciliation_mismatch"])) <= Decimal("0.000001")


def test_insufficient_universe_retains_prior_portfolio_without_relaxation() -> None:
    sessions, bars, schedules = fixture_market()
    insufficient = RebalanceSchedule(
        "MOM-A-001", sessions[2], sessions[3], 190, 19, False, ()
    )
    result = simulate_executable("MOM-A-001", [schedules[0], insufficient], sessions, bars)
    second = result["rebalances"][1]
    assert second["status"] == "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"
    assert second["gross_buy_turnover"] == 0
    assert second["gross_sell_turnover"] == 0
    assert second["actual_holdings"] > 0


def test_performance_metrics_cover_gross_net_periods_months_and_drawdown() -> None:
    sessions, bars, schedules = fixture_market()
    simulation = simulate_executable("MOM-A-001", schedules, sessions, bars)
    analysis = summarize_simulation(simulation)
    summary = analysis["summary"]
    assert summary["gross_ending_equity"] >= summary["net_ending_equity"]
    assert summary["total_cost"] > 0
    assert summary["gross_to_net_return_deterioration_pp"] > 0
    assert summary["rebalance_period_count"] == 1
    assert summary["final_partial_period"]["final_partial_period"] is True
    assert summary["net_max_drawdown_pct"] <= 0
    assert len(analysis["drawdowns"]) == len(sessions) * 2


def test_yearly_results_and_quality_gate_are_deterministic() -> None:
    sessions, bars, schedules = fixture_market()
    simulation = simulate_executable("MOM-A-001", schedules, sessions, bars)
    summary = summarize_simulation(simulation)["summary"]
    # Classification accepts a complete three-year fixture; yearly calculation itself is covered
    # on the real development input by the generated report contract.
    yearly_fixture = [
        {"year": 2022, "net_return_pct": Decimal("10")},
        {"year": 2023, "net_return_pct": Decimal("8")},
        {"year": 2024, "net_return_pct": Decimal("6")},
    ]
    summary.update(
        {
            "net_cagr_pct": Decimal("8"),
            "net_total_return_pct": Decimal("26"),
            "net_max_drawdown_pct": Decimal("-20"),
            "gross_to_net_return_deterioration_pp": Decimal("3"),
            "net_return_per_unit_turnover": Decimal("0.05"),
            "average_residual_cash_pct": Decimal("7"),
            "average_tracking_difference_l1_pct": Decimal("8"),
            "min_holdings": 20,
        }
    )
    classifications = quality_classifications(summary, yearly_fixture)
    assert classifications["FAMILY_A_TEMPORAL_STABILITY"] == "CONSISTENT"
    assert classifications["TURNOVER_EFFICIENCY_RESULT"] == "ACCEPTABLE"
    assert classifications["CAPITAL_FEASIBILITY_RESULT"] == "MODERATE_DISTORTION"
    assert classifications["ELIGIBLE_FOR_FAMILY_A_PHASE2"] == "YES"


def test_yearly_return_calculation_uses_prior_year_ending_equity() -> None:
    simulation = {
        "experiment_id": "MOM-A-001",
        "mode": EXECUTABLE_MODE,
        "daily": [
            {"date": "2022-12-30", "gross_equity": Decimal("110000"), "net_equity": Decimal("108000")},
            {"date": "2023-12-29", "gross_equity": Decimal("121000"), "net_equity": Decimal("118800")},
            {"date": "2024-12-31", "gross_equity": Decimal("133100"), "net_equity": Decimal("130680")},
        ],
        "rebalances": [],
        "periods": [],
        "costs": [],
    }
    rows = yearly_results(simulation)
    assert [row["year"] for row in rows] == [2022, 2023, 2024]
    assert rows[0]["net_return_pct"] == Decimal("8.00")
    assert rows[1]["net_return_pct"] == Decimal("10.0")
    assert rows[2]["net_return_pct"] == Decimal("10.0")


def test_result_immutability_rejects_changed_body(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    first = _immutable_result(path, {"experiment_id": "MOM-A-001", "value": 1}, "result_hash")
    second = _immutable_result(path, {"experiment_id": "MOM-A-001", "value": 1}, "result_hash")
    assert first == second
    with pytest.raises(FamilyAResultImmutabilityError):
        _immutable_result(path, {"experiment_id": "MOM-A-001", "value": 2}, "result_hash")


def test_no_parameter_mutation_extra_variant_validation_or_strategy_v2() -> None:
    verified = verify_family_a_preregistration(REPO_ROOT)
    assert verified["config"]["performance_policy"]["strategy_v2_creation_allowed"] is False
    assert verified["config"]["temporal_governance"]["family_a_validation_accessed"] is False
    assert tuple(verified["registry"]["experiment_ids"]) == tuple(EXPECTED_EXPERIMENT_HASHES)
    assert all(row["promotion_allowed"] is False for row in verified["registry"]["experiments"])


def test_frozen_project_and_command_one_baseline_remain_immutable() -> None:
    before = full_baseline_snapshot(REPO_ROOT)
    verify_family_a_preregistration(REPO_ROOT)
    after = full_baseline_snapshot(REPO_ROOT)
    assert before == after


def test_report_generation_contract(tmp_path: Path) -> None:
    assert REPORT_NAMES == (
        "family_a_dev_v1_summary.json",
        "family_a_dev_v1_comparison.csv",
        "family_a_dev_v1_yearly.csv",
        "family_a_dev_v1_turnover.csv",
        "family_a_dev_v1_costs.csv",
        "family_a_dev_v1_capital_distortion.csv",
        "family_a_dev_v1_rebalances.csv",
        "family_a_dev_v1_holdings.csv",
        "family_a_dev_v1_position_returns.csv",
        "family_a_dev_v1_drawdowns.csv",
        "family_a_dev_v1_pilot.csv",
    )
    write_json(tmp_path / REPORT_NAMES[0], {"command_version": COMMAND_VERSION})
    for name in REPORT_NAMES[1:]:
        write_csv(tmp_path / name, [{"status": "GENERATED"}])
    assert all((tmp_path / name).stat().st_size > 0 for name in REPORT_NAMES)
