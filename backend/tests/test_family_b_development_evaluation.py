from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_phase2_closure import EXPECTED_CLOSURE_HASH
from app.research.strategy.family_b_development_evaluation import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXECUTABLE_MODE,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_RESULT_HASHES,
    REPORT_NAMES,
    drawdown_relative_improvement,
    family_result_mapping,
    next_research_stage,
    return_preservation_ratio,
    temporal_support,
    treatment_schedules,
    verify_command_01_freeze,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    CAPITAL_INR,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    build_signal_dataset,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_dev_v1_summary.json"


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_exact_command_identity_and_primary_mode() -> None:
    assert COMMAND_VERSION == "FAMILY_B_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "RELATIVE_ABSOLUTE_MOMENTUM_DEVELOPMENT_V1"
    assert EXECUTABLE_MODE == "EXECUTABLE_INTEGER_SHARE_500K"


def test_prerun_gate_verifies_all_frozen_hashes_before_performance() -> None:
    frozen = verify_command_01_freeze(REPO_ROOT)
    assert frozen["status"] == "VERIFIED"
    assert all(frozen["checks"].values())
    assert frozen["snapshot"]["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH
    assert frozen["snapshot"]["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert frozen["snapshot"]["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    assert frozen["snapshot"]["experiment_hashes"] == EXPECTED_EXPERIMENT_HASHES
    assert frozen["snapshot"]["family_a_closure_hash"] == EXPECTED_CLOSURE_HASH


def test_development_partition_is_exact_and_never_crosses_2024() -> None:
    partition = summary()["development_window"]
    assert partition["start"] == "2022-01-01"
    assert partition["end"] == "2024-12-31"
    assert partition["latest_loaded_date"] == "2024-12-31"
    assert partition["development_only"] is True


def test_control_reproduces_frozen_a2_002_at_500k() -> None:
    result = summary()["control"]
    assert result["role"] == "CONTROL_REPRODUCTION_ONLY"
    assert result["performance"]["starting_equity"] == "500000"
    assert result["performance"]["mode"] == EXECUTABLE_MODE
    assert result["control_reproduction"]["all_metrics_exact"] is True
    assert all(result["control_reproduction"]["metric_checks"].values())
    assert result["control_reproduction"]["family_a_result_overwritten"] is False


def test_treatment_schedules_preserve_rules_minimum_and_no_backfill() -> None:
    signal_rows, breadth_rows, _, _, _ = build_signal_dataset(REPO_ROOT)
    b001 = treatment_schedules(signal_rows, breadth_rows, "MOM-B-001")
    b002 = treatment_schedules(signal_rows, breadth_rows, "MOM-B-002")
    assert len(b001) == len(b002) == 11
    assert all(row.execution_date > row.formation_date for row in (*b001, *b002))
    assert all(len(row.selected) == row.intended_count for row in b001)
    assert all(len(row.selected) == row.intended_count for row in b002 if row.sufficient_universe)
    assert all(len(row.selected) == 0 for row in b002 if not row.sufficient_universe)
    assert [row.formation_date.isoformat() for row in b002 if not row.sufficient_universe] == [
        "2022-03-31"
    ]
    assert min(row.intended_count for row in b001) >= 10


def test_frozen_b001_and_b002_selection_rules_are_reflected_in_results() -> None:
    result = summary()
    assert result["treatments"]["MOM-B-001"]["filter_impact"]["removed"] == 0
    assert result["treatments"]["MOM-B-001"]["qualifying_breadth"][
        "minimum_qualifying_count"
    ] == 19
    assert result["treatments"]["MOM-B-002"]["filter_impact"]["below_sma"] == 1
    assert result["treatments"]["MOM-B-002"]["filter_impact"]["unavailable"] == 30
    assert result["treatments"]["MOM-B-002"]["qualifying_breadth"][
        "insufficient_breadth_schedules"
    ] == ["2022-03-31"]


def test_both_modes_use_500k_and_executable_is_primary() -> None:
    result = summary()
    for record in (result["control"], *result["treatments"].values()):
        assert record["performance"]["starting_equity"] == "500000"
        assert record["idealized_performance"]["starting_equity"] == "500000"
        assert record["idealized_vs_executable"]["primary_decision_mode"] == EXECUTABLE_MODE


def test_whole_share_equal_weight_next_open_and_cost_accounting() -> None:
    result = summary()
    for record_id in ("CONTROL-B-000", "MOM-B-001", "MOM-B-002"):
        path_key = "control" if record_id == "CONTROL-B-000" else record_id.lower().replace("-", "_")
        directory = REPO_ROOT / result["storage"][path_key] / EXECUTABLE_MODE.lower()
        rebalances = (directory / "rebalances.csv").read_text(encoding="utf-8")
        holdings = (directory / "holdings.csv").read_text(encoding="utf-8")
        costs = (directory / "costs.csv").read_text(encoding="utf-8")
        assert "formation_date,execution_date" in rebalances
        assert "quantity" in holdings
        assert "FULL_FROZEN_COST_MODEL" in costs
        assert Decimal(
            (result["control"] if record_id == "CONTROL-B-000" else result["treatments"][record_id])[
                "performance"
            ]["total_cost"]
        ) > 0


def test_return_preservation_calculation_and_boundaries() -> None:
    assert return_preservation_ratio(Decimal("8.5"), Decimal("10")) == Decimal("0.85")
    assert return_preservation_ratio(Decimal("9"), Decimal("10")) == Decimal("0.9")
    with pytest.raises(ValueError):
        return_preservation_ratio(Decimal("1"), Decimal("0"))


def test_drawdown_improvement_calculation_and_boundaries() -> None:
    assert drawdown_relative_improvement(Decimal("-17"), Decimal("-20")) == Decimal("0.15")
    assert drawdown_relative_improvement(Decimal("-22"), Decimal("-20")) == Decimal("-0.10")
    assert drawdown_relative_improvement(Decimal("-24.01"), Decimal("-20")) < Decimal("-0.20")


def test_temporal_support_uses_exact_two_of_three_and_15pp_rule() -> None:
    control = [
        {"year": 2022, "net_return_pct": Decimal("20")},
        {"year": 2023, "net_return_pct": Decimal("20")},
        {"year": 2024, "net_return_pct": Decimal("20")},
    ]
    passing = [
        {"year": 2022, "net_return_pct": Decimal("5")},
        {"year": 2023, "net_return_pct": Decimal("5")},
        {"year": 2024, "net_return_pct": Decimal("1")},
    ]
    failing = [
        {"year": 2022, "net_return_pct": Decimal("4.9")},
        {"year": 2023, "net_return_pct": Decimal("4.9")},
        {"year": 2024, "net_return_pct": Decimal("0")},
    ]
    assert temporal_support(passing, control)["passed"] is True
    assert temporal_support(failing, control)["passed"] is False


def test_all_a_to_g_criteria_pass_for_both_treatments() -> None:
    treatments = summary()["treatments"]
    for experiment_id in ("MOM-B-001", "MOM-B-002"):
        evaluation = treatments[experiment_id]["criteria"]
        assert list(evaluation["criteria"]) == [
            "A_RETURN_PRESERVATION",
            "B_DRAWDOWN",
            "C_TEMPORAL_SUPPORT",
            "D_COST_EFFICIENCY",
            "E_BREADTH",
            "F_CAPITAL_DEPLOYMENT",
            "G_ACCOUNTING_DATA_INTEGRITY",
        ]
        assert all(evaluation["criteria"].values())
        assert evaluation["criteria_pass_count"] == 7
        assert evaluation["fatal_failure_triggered"] is False


def test_exact_treatment_criterion_values() -> None:
    treatments = summary()["treatments"]
    b001 = treatments["MOM-B-001"]["criteria"]
    b002 = treatments["MOM-B-002"]["criteria"]
    assert Decimal(b001["RETURN_PRESERVATION_RATIO"]) >= Decimal("0.90")
    assert Decimal(b001["DRAWDOWN_RELATIVE_IMPROVEMENT"]) == 0
    assert Decimal(b001["normalized_cost_drag_relative_increase"]) <= Decimal("0.25")
    assert Decimal(b001["breadth_fraction"]) == 1
    assert Decimal(b001["average_cash_fraction"]) <= Decimal("0.35")
    assert Decimal(b002["RETURN_PRESERVATION_RATIO"]) >= Decimal("0.90")
    assert Decimal(b002["DRAWDOWN_RELATIVE_IMPROVEMENT"]) < Decimal("0.15")
    assert Decimal(b002["normalized_cost_drag_relative_increase"]) <= Decimal("0.25")
    assert Decimal(b002["breadth_fraction"]) >= Decimal("0.80")
    assert Decimal(b002["average_cash_fraction"]) <= Decimal("0.35")


def test_treatment_results_follow_frozen_classification() -> None:
    classifications = summary()["classifications"]
    assert classifications["MOM_B_001_DEVELOPMENT_RESULT"] == "SUPPORTED"
    assert classifications["MOM_B_002_DEVELOPMENT_RESULT"] == "SUPPORTED"
    assert all(
        treatment["classification"] == "SUPPORTED"
        for treatment in summary()["treatments"].values()
    )


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("STRONGLY_SUPPORTED", "PARTIALLY_SUPPORTED", "STRONG_SUPPORT"),
        ("SUPPORTED", "PARTIALLY_SUPPORTED", "SUPPORT"),
        ("SUPPORTED", "FAILED", "MIXED"),
        ("PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED", "WEAK"),
        ("FAILED", "FAILED", "FAILED"),
        ("INCONCLUSIVE", "INCONCLUSIVE", "INCONCLUSIVE"),
    ],
)
def test_family_result_mapping(first: str, second: str, expected: str) -> None:
    assert family_result_mapping(first, second) == expected


def test_family_result_and_next_stage_mapping() -> None:
    classifications = summary()["classifications"]
    assert classifications["FAMILY_B_DEVELOPMENT_RESULT"] == "SUPPORT"
    assert classifications["FAMILY_B_NEXT_RESEARCH_STAGE"] == (
        "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
    )
    assert next_research_stage(
        ["SUPPORTED", "PARTIALLY_SUPPORTED"],
        unresolved_implementation_or_data_issue=False,
    ) == "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
    assert next_research_stage(
        ["FAILED", "FAILED"], unresolved_implementation_or_data_issue=False
    ) == "STOP_FAMILY_B"


def test_yearly_metrics_cover_exactly_2022_2023_2024() -> None:
    result = summary()
    for record in (result["control"], *result["treatments"].values()):
        assert [row["year"] for row in record["yearly"]] == [2022, 2023, 2024]
        assert all("positive_month_rate_pct" in row for row in record["yearly"])
        assert all("average_cash_pct" in row for row in record["yearly"])
        assert all("average_holdings" in row for row in record["yearly"])


def test_diagnostics_are_descriptive_and_not_new_thresholds() -> None:
    treatments = summary()["treatments"]
    for record in treatments.values():
        diagnostic = record["downside_upside_diagnostics"]
        assert diagnostic["diagnostic_only"] is True
        assert diagnostic["success_criterion"] is False
        assert diagnostic["bearish_control_month_count"] > 0
        assert diagnostic["positive_control_month_count"] > 0
        assert diagnostic["treatment_upside_capture_ratio"] is not None


def test_cash_decomposition_reconciles_and_captures_b002_no_portfolio_cash() -> None:
    cash = summary()["comparison"]["cash_decomposition"]
    assert all(row["reconciles_to_average_cash"] is True for row in cash.values())
    assert Decimal(cash["MOM-B-001"]["insufficient_breadth_no_portfolio_cash_contribution_pct"]) == 0
    assert Decimal(cash["MOM-B-002"]["insufficient_breadth_no_portfolio_cash_contribution_pct"]) > 0
    assert cash["MOM-B-002"]["insufficient_breadth_no_portfolio_sessions"] == 62


def test_overlap_turnover_and_implementation_gap_are_reported() -> None:
    comparison = summary()["comparison"]
    assert Decimal(comparison["overlap"]["MOM-B-001"]["average_jaccard_pct"]) > Decimal("90")
    assert Decimal(comparison["overlap"]["MOM-B-002"]["average_jaccard_pct"]) > Decimal("80")
    assert comparison["turnover_cause"]["MOM-B-001"]["finding"] == "INCREASES_TURNOVER"
    assert comparison["turnover_cause"]["MOM-B-002"]["finding"] == "REDUCES_TURNOVER"
    for experiment_id in ("MOM-B-001", "MOM-B-002"):
        gap = comparison["idealized_vs_executable"][experiment_id]
        assert Decimal(gap["implementation_gap_net_return_pp"]) < 0


def test_no_parameter_or_success_criteria_mutation_or_new_experiment() -> None:
    governance = summary()["governance"]
    assert governance["parameters_changed"] is False
    assert governance["success_criteria_changed"] is False
    assert governance["B003_created"] is False
    assert governance["combined_filter_tested"] is False
    assert governance["alternate_threshold_tested"] is False
    assert governance["alternate_moving_average_tested"] is False
    assert governance["alternate_capital_tested"] is False


def test_no_validation_strategy_v2_regime_stop_or_intraday() -> None:
    governance = summary()["governance"]
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["market_regime_added"] is False
    assert governance["stop_or_target_added"] is False
    assert governance["intraday_added"] is False
    assert governance["family_c_started"] is False


def test_accounting_reconciles_for_control_and_treatments() -> None:
    result = summary()
    for record in (result["control"], *result["treatments"].values()):
        assert all(record["accounting"].values())
        assert record["performance"]["cash_reconciliation_violations"] == 0
        assert record["performance"]["equity_reconciliation_violations"] == 0


def test_result_hashes_and_registry_hash_are_immutable_and_exact() -> None:
    result = summary()
    assert result["result_hashes"] == EXPECTED_RESULT_HASHES
    assert result["development_registry_hash"] == EXPECTED_DEVELOPMENT_REGISTRY_HASH
    for record_id, expected_hash in EXPECTED_RESULT_HASHES.items():
        record = result["control"] if record_id == "CONTROL-B-000" else result["treatments"][record_id]
        assert record["development_result_hash"] == expected_hash
        body = {key: value for key, value in record.items() if key != "development_result_hash"}
        assert canonical_hash(body) == expected_hash
    registry_path = REPO_ROOT / result["storage"]["comparison"] / "development_registry_v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in registry.items() if key != "development_registry_hash"}
    assert canonical_hash(body) == EXPECTED_DEVELOPMENT_REGISTRY_HASH
    assert all(row["status"] == "DEVELOPMENT_EVALUATED" for row in registry["experiments"])
    assert all(row["parameters_changed"] is False for row in registry["experiments"])


def test_command_01_family_a_strategy_v1_and_cap4_baselines_are_unchanged() -> None:
    regression = summary()["regression"]
    assert regression["baseline_unchanged"] is True
    assert regression["command_01_before_snapshot_hash"] == regression[
        "command_01_after_snapshot_hash"
    ]
    assert regression["family_a_before_snapshot_hash"] == regression[
        "family_a_after_snapshot_hash"
    ]
    assert regression["family_a_closure_hash"] == EXPECTED_CLOSURE_HASH


def test_required_storage_and_reports_exist() -> None:
    result = summary()
    output_root = REPO_ROOT / result["storage"]["root"]
    for directory in ("control", "mom_b_001", "mom_b_002", "comparison", "ledgers"):
        assert (output_root / directory).is_dir()
    assert len(REPORT_NAMES) == 12
    assert all((REPO_ROOT / "data/reports" / name).exists() for name in REPORT_NAMES)


def test_security_has_zero_external_side_effects() -> None:
    safety = summary()["safety"]
    assert safety == {
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "secrets_written": 0,
    }
