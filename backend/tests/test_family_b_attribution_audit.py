from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_b_attribution_audit import (
    ATTRIBUTION_CATEGORIES,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
    REMOVAL_CATEGORIES,
    REPLAY_LABEL,
    REPLAY_STATUS,
    REPORT_NAMES,
    verify_frozen_inputs,
)
from app.research.strategy.family_b_development_evaluation import (
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_RESULT_HASHES,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_attribution_v1_summary.json"
RESULT_PATH = (
    REPO_ROOT
    / "data/research/strategy_families/family_b/v1/attribution_audit/manifests/family_b_attribution_audit_result_v1.json"
)


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def read_report(name: str) -> list[dict[str, str]]:
    with (REPO_ROOT / "data/reports" / name).open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


def test_exact_command_identity() -> None:
    assert COMMAND_VERSION == "FAMILY_B_ATTRIBUTION_AUDIT_V1"
    assert COMMAND_PROFILE == "RELATIVE_ABSOLUTE_MOMENTUM_ATTRIBUTION_V1"


def test_all_frozen_family_b_inputs_verify_before_audit() -> None:
    frozen = verify_frozen_inputs(REPO_ROOT)
    assert frozen["status"] == "VERIFIED"
    assert all(frozen["checks"].values())
    assert frozen["summary"]["result_hashes"] == EXPECTED_RESULT_HASHES
    assert frozen["summary"]["development_registry_hash"] == EXPECTED_DEVELOPMENT_REGISTRY_HASH
    assert frozen["summary"]["hash_gate"]["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH
    assert frozen["summary"]["hash_gate"]["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH


def test_b001_zero_filter_removals_reproduce_exactly() -> None:
    result = summary()["B001"]
    assert result["candidate_count"] == 302
    assert result["filter_removed_count"] == 0
    assert result["B001_DISTINCT_FILTER_EVIDENCE"] == "NONE"


def test_b001_preallocation_selected_sets_match_on_every_date() -> None:
    rows = read_report("family_b_attribution_v1_b001_rebalance_diff.csv")
    assert len(rows) == 11
    assert all(row["selected_set_equivalent"] == "True" for row in rows)
    assert all(int(row["symmetric_difference_count"]) == 0 for row in rows)
    assert all(row["control_eligible_universe_count"] == row["B001_eligible_universe_count"] for row in rows)


def test_b001_non_equivalence_is_minimum_breadth_then_path_dependence() -> None:
    result = summary()["B001"]
    assert result["exact_mechanical_equivalent_dates"] == ["2022-03-31"]
    assert result["non_equivalent_dates"][0] == "2022-06-30"
    assert len(result["non_equivalent_dates"]) == 10
    assert result["B001_CONTROL_EQUIVALENCE_RESULT"] == "EXPLAINED_NON_EQUIVALENCE"
    assert result["unexplained_differences"] == []


def test_b001_attribution_uses_only_closed_categories() -> None:
    rows = read_report("family_b_attribution_v1_b001_rebalance_diff.csv")
    allowed = set(ATTRIBUTION_CATEGORIES) | {"NONE"}
    for row in rows:
        assert row["allocation_attribution"] in allowed
        assert row["cash_attribution"] in allowed
        assert row["trade_attribution"] in allowed
        assert row["cost_attribution"] in allowed
    counts = summary()["B001"]["attribution_category_counts"]
    assert set(counts) == set(ATTRIBUTION_CATEGORIES)
    assert counts["ABSOLUTE_FILTER_EFFECT"] == 0
    assert counts["IMPLEMENTATION_DEFECT"] == 0
    assert counts["UNEXPLAINED"] == 0


def test_b002_removal_decomposition_is_exact_and_non_overlapping() -> None:
    result = summary()["B002"]
    assert result["candidate_count"] == 302
    assert result["removal_counts"] == {
        "BELOW_SMA200": 1,
        "SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY": 30,
        "OTHER_DATA_UNAVAILABLE": 0,
        "INFRASTRUCTURE_FILTER": 0,
        "OTHER": 0,
    }
    rows = read_report("family_b_attribution_v1_b002_removals.csv")
    assert len(rows) == 31
    assert all(row["removal_category"] in REMOVAL_CATEGORIES for row in rows)


def test_first_schedule_audit_is_exact() -> None:
    first = summary()["B002"]["first_schedule"]
    assert first["formation_date"] == "2022-03-31"
    assert first["execution_date"] == "2022-04-01"
    assert first["control_holding_count"] == 23
    assert first["B002_available_SMA_count"] == 0
    assert first["B002_unavailable_count"] == 23
    assert first["B002_qualifying_count"] == 0
    assert first["B002_formed_portfolio"] is False
    assert Decimal(first["B002_cash_allocation_pct"]) == 100


def test_first_interval_audit_quantifies_cash_avoidance() -> None:
    first = summary()["B002"]["first_schedule"]
    assert Decimal(first["control_subsequent_period_return_pct"]) == Decimal(
        "-12.88628350715217773851624085"
    )
    assert Decimal(first["B002_subsequent_period_return_pct"]) == 0
    assert Decimal(first["difference_contribution_rupees"]) == Decimal("65153.5554")


def test_interval_attribution_arithmetic_reconciles_to_final_gap() -> None:
    rows = read_report("family_b_attribution_v1_b002_intervals.csv")
    contributions = sum((Decimal(row["difference_contribution_rupees"]) for row in rows), Decimal("0"))
    assert len(rows) == 11
    assert contributions == Decimal(summary()["B002"]["observed_final_equity_gap_rupees"])
    assert Decimal(rows[-1]["cumulative_difference_contribution_rupees"]) == contributions


def test_year_attribution_arithmetic_reconciles_and_is_2022_dominant() -> None:
    rows = read_report("family_b_attribution_v1_year_attribution.csv")
    contributions = sum(
        (Decimal(row["origin_carried_forward_contribution_rupees"]) for row in rows),
        Decimal("0"),
    )
    result = summary()["B002"]
    assert [int(row["year"]) for row in rows] == [2022, 2023, 2024]
    assert abs(contributions - Decimal(result["observed_final_equity_gap_rupees"])) < Decimal("0.0001")
    assert Decimal(result["2022_share_of_overall_relative_advantage_pct"]) > 95


def test_true_below_sma_event_is_one_observation_and_not_overclaimed() -> None:
    event = summary()["B002"]["true_filter_effect"]
    assert event["symbol"] == "AUBANK"
    assert event["formation_date"] == "2022-06-30"
    assert event["close"] == "591.7"
    assert event["sma200"] == "612.7415"
    assert event["actually_held_by_control"] is False
    assert event["control_realized_contribution_if_held_rupees"] == "0"
    assert event["statistical_claim_allowed"] is False


def test_missing_history_effect_is_quantified_without_imputation() -> None:
    result = summary()["B002"]
    missing = result["missing_history_effect"]
    replay = result["attribution_replay"]
    assert missing["candidate_count"] == 30
    assert missing["otherwise_in_control_count"] == 30
    assert Decimal(missing["first_schedule_incremental_uninvested_vs_control_rupees"]) == Decimal(
        "490595.2077"
    )
    assert replay["label"] == REPLAY_LABEL
    assert replay["status"] == REPLAY_STATUS
    assert replay["imputed_SMA_used"] is False
    assert replay["new_curve_generated"] is False


def test_cash_effect_is_dominant_and_not_misattributed_to_true_filter() -> None:
    cash = summary()["B002"]["cash_effect"]
    assert cash["B002_CASH_EFFECT_MATERIALITY"] == "DOMINANT"
    assert cash["insufficient_breadth_cash_event_count"] == 1
    assert Decimal(cash["2022_share_of_overall_relative_advantage_pct"]) > 95
    assert Decimal(cash["true_filter_actual_control_contribution_rupees"]) == 0


def test_mature_history_date_is_deterministic_and_diagnostic_only() -> None:
    mature = summary()["B002"]["mature_history"]
    assert mature["formation_date"] == "2022-06-30"
    assert mature["execution_date"] == "2022-07-01"
    assert Decimal(mature["SMA_history_coverage_pct"]) >= 90
    assert mature["diagnostic_only"] is True
    assert mature["rebalance_count"] == 10


def test_later_period_diagnostics_have_no_new_threshold() -> None:
    result = summary()["B002"]
    assert Decimal(result["control_2023_2024_return_pct"]) == Decimal(
        "89.50926531808902559632217030"
    )
    assert Decimal(result["B002_2023_2024_return_pct"]) == Decimal(
        "90.39916806128564394596121400"
    )
    assert result["B002_TREND_FILTER_EVIDENCE"] == "CONFOUNDED_BY_HISTORY_AVAILABILITY"
    assert result["B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"] == "PRIMARILY_HISTORY_AVAILABILITY"


def test_timeline_has_only_three_frozen_curves_and_annotations() -> None:
    rows = read_report("family_b_attribution_v1_timeline.csv")
    assert rows
    assert rows[0]["date"] >= "2022-01-01"
    assert rows[-1]["date"] == "2024-12-31"
    assert all(row["new_strategy_curve"] == "False" for row in rows)
    assert all(
        key in rows[0]
        for key in (
            "CONTROL_normalized_net_equity",
            "B001_normalized_net_equity",
            "B002_normalized_net_equity",
        )
    )


def test_no_parameter_change_new_strategy_b003_or_validation() -> None:
    governance = summary()["governance"]
    assert governance["new_strategy_created"] is False
    assert governance["parameters_changed"] is False
    assert governance["B003_created"] is False
    assert governance["alternate_MA_tested"] is False
    assert governance["alternate_threshold_tested"] is False
    assert governance["missing_SMA_behavior_changed"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False


def test_validation_design_readiness_obeys_evidence_rules() -> None:
    decision = summary()["decision"]
    assert decision["FAMILY_B_VALIDATION_DESIGN_READINESS"] == "NO_CANDIDATE_READY"
    assert decision["B001_ready_for_validation_design"] is False
    assert decision["B002_ready_for_validation_design"] is False


def test_result_hash_is_frozen_and_recomputes_exactly() -> None:
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    observed = result.pop("family_b_attribution_audit_hash")
    assert observed == EXPECTED_ATTRIBUTION_AUDIT_HASH
    assert canonical_hash(result) == EXPECTED_ATTRIBUTION_AUDIT_HASH
    assert summary()["family_b_attribution_audit_hash"] == EXPECTED_ATTRIBUTION_AUDIT_HASH


def test_all_required_reports_and_storage_directories_exist() -> None:
    for report_name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / report_name).is_file()
    root = REPO_ROOT / "data/research/strategy_families/family_b/v1/attribution_audit"
    assert {path.name for path in root.iterdir() if path.is_dir()} == {
        "b001_equivalence",
        "b002_attribution",
        "timeline",
        "manifests",
    }


def test_baselines_and_security_remain_unchanged() -> None:
    result = summary()
    assert result["regression"]["baseline_unchanged"] is True
    assert all(
        result["regression"][key] == "UNCHANGED"
        for key in (
            "strategy_v1",
            "CAP4",
            "family_a_commands_01_05",
            "family_a_closure",
            "family_b_command_01",
            "family_b_command_02",
        )
    )
    governance = result["governance"]
    assert governance["live_signals_generated"] == 0
    assert governance["live_orders_placed"] == 0
    assert governance["broker_calls"] == 0
    assert governance["remote_migrations"] == 0
    assert governance["supabase_persistence"] == 0
    assert governance["network_writes"] == 0
    assert governance["database_writes"] == 0
