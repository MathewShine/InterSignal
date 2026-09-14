from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_development_backtest import verify_family_a_preregistration
from app.research.strategy.family_a_phase2_research import (
    A2_001_CAPITAL,
    A2_002_CAPITAL,
    ENTRY_PERCENTILE,
    EXPECTED_PHASE2_CONFIG_HASH,
    EXPECTED_PHASE2_EXPERIMENT_HASHES,
    EXPECTED_PHASE2_REGISTRY_HASH,
    PHASE2_EXPERIMENT_IDS,
    PHASE2_PROFILE,
    PHASE2_VERSION,
    REPORT_NAMES,
    RETENTION_PERCENTILE,
    build_capital_pilot,
    build_retention_pilot,
    capital_allocation_pilot,
    phase2_baseline_snapshot,
    phase2_config,
    phase2_registry,
    retention_band_action,
    retention_band_selection,
    verify_command_02_results,
    verify_phase2_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def registry_fixture() -> tuple[dict, dict, dict]:
    verified = verify_family_a_preregistration(REPO_ROOT)
    reference = next(
        row for row in verified["registry"]["experiments"]
        if row["experiment_id"] == "MOM-A-002"
    )
    config = phase2_config()
    registry = phase2_registry(reference["parameters"], config)
    return config, registry, reference


def test_exact_phase2_identity_and_experiment_count() -> None:
    assert PHASE2_VERSION == "FAMILY_A_PHASE2_RESEARCH_V1"
    assert PHASE2_PROFILE == "MOMENTUM_IMPLEMENTATION_EFFICIENCY_V1"
    assert PHASE2_EXPERIMENT_IDS == ("A2-001", "A2-002")


def test_frozen_phase2_hashes_recompute() -> None:
    config, registry, reference = registry_fixture()
    verify_phase2_registry(registry, config, reference["parameters"])
    assert config["phase2_config_hash"] == EXPECTED_PHASE2_CONFIG_HASH
    assert registry["phase2_registry_hash"] == EXPECTED_PHASE2_REGISTRY_HASH
    for row in registry["experiments"]:
        assert row["parameter_hash"] == EXPECTED_PHASE2_EXPERIMENT_HASHES[row["experiment_id"]]["parameter_hash"]
        assert row["preregistration_hash"] == EXPECTED_PHASE2_EXPERIMENT_HASHES[row["experiment_id"]]["preregistration_hash"]
        assert canonical_hash(row["parameters"]) == row["parameter_hash"]


def test_a2_001_exact_10_15_band_and_100k() -> None:
    config, registry, _ = registry_fixture()
    row = registry["experiments"][0]
    assert config["allowed_retention_band"]["alternatives_allowed"] is False
    assert row["parameters"]["entry_percentile"] == ENTRY_PERCENTILE == Decimal("0.10")
    assert row["parameters"]["retention_percentile"] == RETENTION_PERCENTILE == Decimal("0.15")
    assert row["parameters"]["starting_capital_inr"] == A2_001_CAPITAL == Decimal("100000")


def test_held_ranks_11_through_15_are_retained() -> None:
    for percent in range(11, 16):
        assert retention_band_action(
            rank_fraction=Decimal(percent) / Decimal("100"),
            is_held=True,
            infrastructure_eligible=True,
        ) == "RETAIN"


def test_nonheld_ranks_11_through_15_do_not_enter() -> None:
    for percent in range(11, 16):
        assert retention_band_action(
            rank_fraction=Decimal(percent) / Decimal("100"),
            is_held=False,
            infrastructure_eligible=True,
        ) == "DO_NOT_ENTER"


def test_held_rank_above_15_exits() -> None:
    assert retention_band_action(
        rank_fraction=Decimal("0.16"), is_held=True, infrastructure_eligible=True
    ) == "EXIT"


def test_eligibility_failure_overrides_retention() -> None:
    assert retention_band_action(
        rank_fraction=Decimal("0.08"), is_held=True, infrastructure_eligible=False
    ) == "EXIT"


def test_replacement_is_deterministic_and_equal_weighted() -> None:
    ranked = [
        {"symbol": f"S{rank:03d}", "rank": rank, "infrastructure_eligible": True}
        for rank in range(1, 101)
    ]
    held = [*(f"S{rank:03d}" for rank in range(1, 10)), "S016"]
    first = retention_band_selection(ranked, held)
    second = retention_band_selection(list(reversed(ranked)), list(reversed(held)))
    assert first == second
    assert first["entered"] == ["S010"]
    assert first["exited"] == ["S016"]
    assert set(first["equal_weights"].values()) == {Decimal("0.1")}
    assert sum(first["equal_weights"].values()) == Decimal("1")


def test_a2_002_capital_is_500k_and_only_parameter_change() -> None:
    config, registry, reference = registry_fixture()
    row = registry["experiments"][1]
    differences = {
        key for key in set(reference["parameters"]) | set(row["parameters"])
        if reference["parameters"].get(key) != row["parameters"].get(key)
    }
    assert differences == {"starting_capital_inr"}
    assert row["parameters"]["starting_capital_inr"] == A2_002_CAPITAL == Decimal("500000")
    assert config["allowed_capitals_inr"] == {
        "A2-001": Decimal("100000"),
        "A2-002": Decimal("500000"),
        "alternatives_allowed": False,
    }


def test_no_signal_or_rebalance_change() -> None:
    _, registry, _ = registry_fixture()
    assert all(row["parameters"]["signal"] == "6M" for row in registry["experiments"])
    assert all(row["parameters"]["rebalance_frequency"] == "QUARTERLY" for row in registry["experiments"])


def test_normalized_comparison_and_cost_normalization_are_frozen() -> None:
    config = phase2_config()
    comparison = config["comparison_rules"]
    assert comparison["capital_comparison"] == "PERCENTAGE_RETURNS_AND_NORMALIZED_EQUITY_NOT_RAW_RUPEE_PNL"
    assert comparison["cost_comparison"] == "RUPEES_AND_PERCENT_OF_STARTING_OR_EVOLVING_EQUITY"


def test_capital_allocator_reconciles_and_changes_integer_shares() -> None:
    selected = [
        {"symbol": "A", "rank": 1, "price": Decimal("130")},
        {"symbol": "B", "rank": 2, "price": Decimal("275")},
    ]
    small = capital_allocation_pilot(selected, capital=A2_001_CAPITAL, execution_date=date(2024, 10, 1))
    large = capital_allocation_pilot(selected, capital=A2_002_CAPITAL, execution_date=date(2024, 10, 1))
    assert small["selected_symbols"] == large["selected_symbols"] == ["A", "B"]
    assert small["target_weight"] == large["target_weight"] == Decimal("0.5")
    assert [row["shares"] for row in small["allocations"]] != [row["shares"] for row in large["allocations"]]
    for pilot in (small, large):
        assert pilot["invested_notional"] + pilot["total_buy_cost_rupees"] + pilot["cash_residual"] == pilot["capital"]
        assert pilot["performance_evaluated"] is False


def test_all_eight_retention_pilot_cases_pass() -> None:
    rows, summary = build_retention_pilot()
    assert [row["case_id"] for row in rows] == list("ABCDEFGH")
    assert summary["passed_case_count"] == 8
    assert summary["performance_evaluated"] is False


def test_mechanical_capital_pilot_uses_same_selection_and_no_performance() -> None:
    rows, comparison = build_capital_pilot(REPO_ROOT)
    assert len(rows) == 2
    assert comparison["same_selected_symbols"] is True
    assert comparison["same_prices"] is True
    assert comparison["same_target_percentages"] is True
    assert comparison["different_integer_share_counts"] is True
    assert comparison["normalized_comparison_verified"] is True
    assert comparison["cost_normalization_verified"] is True
    assert comparison["performance_evaluated"] is False


def test_development_only_and_no_validation_or_performance() -> None:
    config, registry, _ = registry_fixture()
    assert config["development_window"] == {"start": "2022-01-01", "end": "2024-12-31"}
    assert config["governance"]["validation_accessed"] is False
    assert config["governance"]["full_performance_evaluation_allowed"] is False
    assert registry["performance_evaluated"] is False


def test_no_strategy_v2_or_unapproved_features() -> None:
    config = phase2_config()
    governance = config["governance"]
    assert governance["strategy_v2_allowed"] is False
    assert governance["extra_signal_allowed"] is False
    assert governance["extra_band_allowed"] is False
    assert governance["extra_capital_allowed"] is False
    assert config["shared_frozen_rules"]["stop_loss"] is None
    assert config["shared_frozen_rules"]["profit_target"] is None
    assert config["shared_frozen_rules"]["leverage_allowed"] is False


def test_frozen_command_02_and_mom_a_002_reference_verify() -> None:
    verified = verify_command_02_results(REPO_ROOT)
    assert verified["verified"] is True
    assert verified["reference"]["baseline_result_hash"] == "ce6f81671e1ede73743cb701a4612e6104c0d81b523409b2c2e04c8a4aab77c6"


def test_phase2_baseline_snapshot_is_stable() -> None:
    before = phase2_baseline_snapshot(REPO_ROOT)
    after = phase2_baseline_snapshot(REPO_ROOT)
    assert before == after
    assert before["cap4_validation_state"] == "EVALUATED"
    assert before["cap4_validation_run_count"] == 1


def test_exact_machine_reports_exist_and_contain_no_performance_result() -> None:
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).exists()
    summary = json.loads((REPO_ROOT / "data/reports" / REPORT_NAMES[0]).read_text(encoding="utf-8"))
    assert summary["experiment_count"] == 2
    assert summary["governance"]["full_performance_run"] is False
    assert summary["classifications"]["RETENTION_BAND_TURNOVER_RESULT"] == "NOT_EVALUATED"
    assert summary["classifications"]["CAPITAL_FEASIBILITY_IMPROVEMENT"] == "NOT_EVALUATED"
