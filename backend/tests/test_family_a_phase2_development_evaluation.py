from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.strategy.family_a_development_backtest import (
    RebalanceSchedule,
    SelectedInstrument,
    simulate_executable,
    summarize_simulation,
)
from app.research.strategy.family_a_momentum import AdjustedBar
from app.research.strategy.family_a_phase2_development_evaluation import (
    A2_001_MODE,
    A2_002_MODE,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_RESULT_HASHES,
    REPORT_NAMES,
    command_03_snapshot,
    evaluate_phase2,
    evaluation_baseline_snapshot,
    retention_schedule_resolver,
    verify_phase2_freeze,
)
from app.research.strategy.family_a_phase2_research import (
    EXPECTED_PHASE2_CONFIG_HASH,
    EXPECTED_PHASE2_EXPERIMENT_HASHES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def evaluation() -> dict:
    return evaluate_phase2(REPO_ROOT)


def test_exact_command_identity() -> None:
    assert COMMAND_VERSION == "FAMILY_A_PHASE2_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "MOMENTUM_IMPLEMENTATION_EFFICIENCY_EVALUATION_V1"
    assert A2_001_MODE == "EXECUTABLE_INTEGER_SHARE_100K_RETENTION_BAND"
    assert A2_002_MODE == "EXECUTABLE_INTEGER_SHARE_500K"


def test_exact_frozen_hashes_verify_before_evaluation() -> None:
    result = verify_phase2_freeze(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert result["config"]["phase2_config_hash"] == EXPECTED_PHASE2_CONFIG_HASH
    assert all(result["checks"].values())


def test_development_partition_only(evaluation: dict) -> None:
    assert evaluation["sessions"][0] >= date(2022, 1, 1)
    assert evaluation["sessions"][-1] <= date(2024, 12, 31)
    assert max(evaluation["bars"]) <= date(2024, 12, 31)


def test_a2_001_resolver_preserves_exact_10_15_rules() -> None:
    resolver, resolved, decisions = retention_schedule_resolver(REPO_ROOT)
    assert callable(resolver)
    assert resolved == [] and decisions == []
    assert EXPECTED_PHASE2_EXPERIMENT_HASHES["A2-001"]["parameter_hash"] == (
        "1998b338f22ef1c3151bd8431869923620fa7742bab986ed92da65b5e884e482"
    )


def test_a2_001_turnover_and_cost_comparison(evaluation: dict) -> None:
    treatment = evaluation["a2_001"]
    assert Decimal(treatment["turnover"]["annualized_turnover_x"]) < Decimal(
        evaluation["reference_turnover"]["annualized_turnover_x"]
    )
    assert Decimal(treatment["cost"]["total_modeled_cost_rupees"]) < Decimal(
        evaluation["reference_cost"]["total_modeled_cost_rupees"]
    )
    assert treatment["turnover_result"] == "MINOR_IMPROVEMENT"


def test_a2_001_performance_comparison_is_multimetric(evaluation: dict) -> None:
    treatment = evaluation["a2_001"]
    assert set(treatment["performance_evidence"]) == {
        "net_return_delta_pp",
        "net_cagr_delta_pp",
        "drawdown_worsening_pp",
        "rebalance_success_delta_pp",
        "positive_year_count",
    }
    assert treatment["performance_result"] == "MODEST_DEGRADATION"
    assert treatment["development_result"] == "PARTIALLY_SUPPORTED"


def test_custom_starting_capital_is_normalized() -> None:
    sessions = [date(2024, 1, 2) + timedelta(days=index) for index in range(3)]
    bars = {
        value_date: {
            "A": AdjustedBar(
                trading_date=value_date,
                symbol="A",
                isin="I1",
                open_price=Decimal("100"),
                close_price=Decimal("101") + index,
                volume=Decimal("1000000"),
                usability_status="ADJUSTED_READY",
                methodology_version="TEST",
            )
        }
        for index, value_date in enumerate(sessions)
    }
    schedule = RebalanceSchedule(
        "A2-002", sessions[0], sessions[1], 10, 1, True,
        (SelectedInstrument("A", "I1", 1, Decimal("0.2")),),
    )
    simulation = simulate_executable(
        "A2-002", [schedule], sessions, bars,
        starting_capital=Decimal("500000"), mode=A2_002_MODE,
    )
    summary = summarize_simulation(simulation, starting_capital=Decimal("500000"))["summary"]
    assert summary["starting_equity"] == Decimal("500000")
    assert summary["mode"] == A2_002_MODE


def test_a2_002_exact_500k_and_same_frozen_selection(evaluation: dict) -> None:
    assert evaluation["a2_002"]["summary"]["starting_equity"] == Decimal("500000")
    assert evaluation["a2_002"]["simulation"]["mode"] == A2_002_MODE
    assert len(evaluation["reference_schedules"]) == 11


def test_a2_002_affordability_and_residual_cash_improve(evaluation: dict) -> None:
    treatment = evaluation["a2_002"]["fidelity"]
    reference = evaluation["reference_fidelity"]
    assert treatment["unaffordable_selection_count"] == 0
    assert reference["unaffordable_selection_count"] == 17
    assert treatment["average_cash_pct"] < reference["average_cash_pct"]


def test_a2_002_weight_tracking_and_capital_fidelity(evaluation: dict) -> None:
    treatment = evaluation["a2_002"]["fidelity"]
    reference = evaluation["reference_fidelity"]
    assert treatment["mean_absolute_weight_error_pp"] < reference["mean_absolute_weight_error_pp"]
    assert treatment["average_l1_tracking_difference_pct"] < reference["average_l1_tracking_difference_pct"]
    assert evaluation["a2_002"]["capital_improvement"] == "MATERIAL_IMPROVEMENT"
    assert evaluation["a2_002"]["capital_distortion"] == "LOW_DISTORTION"
    assert evaluation["a2_002"]["strategy_fidelity"] == "IMPROVED_BUT_MATERIAL_GAP"
    assert evaluation["a2_002"]["development_result"] == "SUPPORTED"


def test_cost_normalization_uses_capital_and_average_equity(evaluation: dict) -> None:
    metrics = evaluation["a2_002"]["cost"]
    assert metrics["cost_pct_starting_capital"] == (
        metrics["total_modeled_cost_rupees"] / Decimal("500000") * Decimal("100")
    )
    assert metrics["cost_pct_average_equity"] == (
        metrics["total_modeled_cost_rupees"] / metrics["average_net_equity"] * Decimal("100")
    )


def test_yearly_metrics_and_temporal_stability(evaluation: dict) -> None:
    for experiment in (evaluation["a2_001"], evaluation["a2_002"]):
        assert [row["year"] for row in experiment["yearly"]] == [2022, 2023, 2024]
        assert all(row["net_return_pct"] is not None for row in experiment["yearly"])
        assert all(row["average_cash_pct"] is not None for row in experiment["yearly"])
        assert all(row["mean_absolute_weight_error_pp"] is not None for row in experiment["yearly"])
        assert experiment["temporal_stability"] == "CONSISTENT"


def test_accounting_and_equity_reconcile(evaluation: dict) -> None:
    for experiment in (evaluation["a2_001"], evaluation["a2_002"]):
        assert experiment["simulation"]["cash_reconciliation_violations"] == 0
        assert experiment["simulation"]["equity_reconciliation_violations"] == 0


def test_no_combined_or_alternate_experiment(evaluation: dict) -> None:
    assert evaluation["a2_001"]["summary"]["starting_equity"] == Decimal("100000")
    assert evaluation["a2_002"]["summary"]["starting_equity"] == Decimal("500000")
    assert evaluation["a2_001"]["summary"]["mode"] != evaluation["a2_002"]["summary"]["mode"]


def test_no_validation_or_strategy_v2_in_summary() -> None:
    summary = json.loads((REPO_ROOT / "data/reports" / REPORT_NAMES[0]).read_text(encoding="utf-8"))
    assert summary["governance"]["validation_accessed"] is False
    assert summary["governance"]["strategy_v2_created"] is False
    assert summary["governance"]["combined_experiment_run"] is False
    assert summary["governance"]["alternate_band_tested"] is False
    assert summary["governance"]["alternate_capital_tested"] is False


def test_family_result_and_next_stage(evaluation: dict) -> None:
    assert evaluation["family_result"] == "PARTIAL_SUPPORT"
    assert evaluation["next_stage"] == "CONTINUE_CONTROLLED_DEVELOPMENT"


def test_command_03_and_full_baseline_snapshots_are_stable() -> None:
    assert command_03_snapshot(REPO_ROOT) == command_03_snapshot(REPO_ROOT)
    assert evaluation_baseline_snapshot(REPO_ROOT) == evaluation_baseline_snapshot(REPO_ROOT)


def test_frozen_result_hashes_and_registry_statuses() -> None:
    summary = json.loads((REPO_ROOT / "data/reports" / REPORT_NAMES[0]).read_text(encoding="utf-8"))
    registry_path = REPO_ROOT / summary["storage"]["registry"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(EXPECTED_RESULT_HASHES) == 2
    assert all(
        summary["experiments"][experiment_id]["development_result_hash"] == expected
        for experiment_id, expected in EXPECTED_RESULT_HASHES.items()
    )
    assert [row["status"] for row in registry["experiments"]] == [
        "DEVELOPMENT_EVALUATED",
        "DEVELOPMENT_EVALUATED",
    ]


def test_all_machine_reports_exist() -> None:
    assert len(REPORT_NAMES) == 9
    assert all((REPO_ROOT / "data/reports" / name).exists() for name in REPORT_NAMES)
