from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_a_validation_design import (
    A2_002_IMPLEMENTATION_HASH,
    A2_002_PREREGISTRATION_HASH,
    ARCHITECTURE_ID,
    CANDIDATE_ID,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTAMINATION_DISCLOSURE,
    CORE_GATE_IDS,
    FAMILY_A_CLOSURE_HASH,
    FAMILY_CONFIG_HASH,
    IMPLEMENTATION_ID,
    LIFECYCLE,
    MANIFEST_VERSION,
    MOM_A_002_PARAMETER_HASH,
    MOM_A_002_PREREGISTRATION_HASH,
    QUALITY_DIMENSION_IDS,
    REPORT_NAMES,
    SOURCE_FILE_HASHES,
    SYNTHESIS_HASH,
    VALIDATION_END,
    VALIDATION_RUN_COUNT,
    VALIDATION_START,
    classify_validation_result,
    derive_validation_schedule,
    fatal_condition_classification,
    verify_frozen_candidate,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROOT = REPO_ROOT / "data/research/validation/family_a/v1/design"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = (
    DESIGN_ROOT / "manifests/family_a_one_shot_validation_design_manifest_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _manifest() -> dict:
    return _json(MANIFEST_PATH)


def _core(**overrides: bool) -> dict[str, bool]:
    values = {gate: True for gate in "ABCDEFG"}
    values.update(overrides)
    return values


def test_command_profile_manifest_and_synthesis_hash_are_exact() -> None:
    assert COMMAND_VERSION == "FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_V1"
    assert COMMAND_PROFILE == "MOM_A_002_GOVERNED_VALIDATION_PROTOCOL_V1"
    assert MANIFEST_VERSION == "FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_MANIFEST_V1"
    manifest = _manifest()
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["cross_family_synthesis_hash"] == SYNTHESIS_HASH
    synthesis = _json(
        REPO_ROOT
        / "data/research/cross_family_synthesis/v1/manifests/cross_family_evidence_synthesis_manifest_v1.json"
    )
    assert synthesis["cross_family_synthesis_hash"] == SYNTHESIS_HASH
    assert canonical_hash(
        {key: value for key, value in synthesis.items() if key != "cross_family_synthesis_hash"}
    ) == SYNTHESIS_HASH


def test_frozen_candidate_identity_and_all_source_file_hashes_are_exact() -> None:
    verification = verify_frozen_candidate(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert all(verification["checks"].values())
    assert verification["source_file_hashes"] == SOURCE_FILE_HASHES
    assert all(file_sha256(REPO_ROOT / path) == expected for path, expected in SOURCE_FILE_HASHES.items())
    identity = _summary()["candidate_identity"]
    assert identity["candidate_id"] == CANDIDATE_ID
    assert identity["architecture_reference"] == ARCHITECTURE_ID
    assert identity["implementation_reference"] == IMPLEMENTATION_ID
    assert identity["reference_capital_inr"] == "500000"
    assert identity["frozen_hashes"]["family_a_family_config_hash"] == FAMILY_CONFIG_HASH
    assert identity["frozen_hashes"]["mom_a_002_parameter_hash"] == MOM_A_002_PARAMETER_HASH
    assert identity["frozen_hashes"]["mom_a_002_preregistration_hash"] == MOM_A_002_PREREGISTRATION_HASH
    assert identity["frozen_hashes"]["a2_002_implementation_config_hash"] == A2_002_IMPLEMENTATION_HASH
    assert identity["frozen_hashes"]["a2_002_preregistration_hash"] == A2_002_PREREGISTRATION_HASH
    assert identity["frozen_hashes"]["family_a_closure_hash"] == FAMILY_A_CLOSURE_HASH


def test_candidate_architecture_is_immutable_and_has_no_overlays() -> None:
    identity = _summary()["candidate_identity"]
    architecture = identity["architecture"]
    assert architecture == {
        "universe": "POINT_IN_TIME_NIFTY_500",
        "direction": "LONG_ONLY",
        "signal": "6M_CROSS_SECTIONAL_RELATIVE_MOMENTUM",
        "lookback_trading_sessions": 126,
        "skip_most_recent_trading_sessions": 0,
        "minimum_price_inr": "100",
        "liquidity_window_sessions": 20,
        "minimum_median_traded_value_inr": "100000000",
        "selection": "TOP_DECILE",
        "selection_fraction": "0.10",
        "minimum_portfolio_size": 20,
        "tie_break": "SYMBOL_ASCENDING",
        "rebalance": "QUARTERLY",
        "weighting": "EQUAL_WEIGHT",
        "capital_inr": "500000",
        "execution": "NEXT_ELIGIBLE_SESSION_OPEN",
        "whole_shares": True,
        "leverage_allowed": False,
        "shorting_allowed": False,
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "cost_scenario": "COST-SCENARIO-002",
        "slippage_bps_per_side": "5",
        "corporate_action_return_layer": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "unsafe_corporate_action_windows": "EXCLUDE_USING_RESEARCH_ELIGIBILITY_V1",
    }
    prohibited = set(identity["prohibited_additions"])
    assert {"FAMILY_B_OVERLAY", "FAMILY_C_OVERLAY", "FAMILY_G_OVERLAY", "CROSS_FAMILY_HYBRID"} <= prohibited
    assert identity["candidate_parameters_changed"] is False


def test_development_reference_and_validation_window_are_exact() -> None:
    summary = _summary()
    development = summary["success_criteria"]["development_comparison_reference"]
    assert development == {
        "starting_equity_inr": "500000",
        "net_ending_equity_inr": "955331.6799",
        "net_total_return_pct": "91.06633598",
        "net_cagr_pct": "24.10585067",
        "max_drawdown_magnitude_pct": "22.92216992",
        "period_start": "2022-01-01",
        "period_end": "2024-12-31",
        "use": "PREREGISTERED_DEGRADATION_COMPARISONS_ONLY",
    }
    assert VALIDATION_START.isoformat() == "2025-01-01"
    assert VALIDATION_END.isoformat() == "2026-08-13"
    assert summary["design_config"]["validation_window"] == {
        "start": "2025-01-01",
        "end": "2026-08-13",
    }


def test_quarterly_schedule_is_derived_from_date_only_calendar_metadata() -> None:
    persisted = _summary()["schedule"]
    derived = derive_validation_schedule(REPO_ROOT)
    assert derived == persisted
    assert [
        (row["formation_date"], row["execution_date"])
        for row in persisted["prospective_rebalances"]
    ] == [
        ("2024-12-31", "2025-01-01"),
        ("2025-03-28", "2025-04-01"),
        ("2025-06-30", "2025-07-01"),
        ("2025-09-30", "2025-10-01"),
        ("2025-12-31", "2026-01-01"),
        ("2026-03-30", "2026-04-01"),
        ("2026-06-30", "2026-07-01"),
    ]
    assert all(row["same_close_execution"] is False for row in persisted["prospective_rebalances"])


def test_completed_and_terminal_interval_policies_are_exact() -> None:
    schedule = _summary()["schedule"]
    assert schedule["expected_completed_interval_count"] == 6
    assert schedule["expected_sample_classification"] == "VALIDATION_SAMPLE_ACCEPTABLE"
    assert sum(row["included_in_primary_metrics"] for row in schedule["prospective_intervals"]) == 6
    terminal = schedule["prospective_intervals"][-1]
    assert terminal["entry_execution_date"] == "2026-07-01"
    assert terminal["required_exit_or_rebalance_endpoint"] is None
    assert terminal["primary_status"] == "TERMINAL_INCOMPLETE_EXCLUDED"
    assert schedule["post_holdout_data_to_complete_interval_allowed"] is False
    assert schedule["terminal_interval_policy"]["diagnostic_status"] == "UNCOMPUTED"
    assert schedule["terminal_interval_policy"]["may_alter_primary_classification"] is False


def test_exactly_seven_core_gates_have_frozen_thresholds() -> None:
    criteria = _summary()["success_criteria"]
    core = {row["criterion"]: row for row in criteria["core_criteria"]}
    assert tuple(row["criterion_id"] for row in criteria["core_criteria"]) == CORE_GATE_IDS
    assert len(core) == 7
    assert core["A"]["threshold"] == "BOTH_REQUIRED"
    assert core["B"]["threshold"] == "12.052925335"
    assert core["C"]["threshold"] == "30"
    assert core["D"]["expected_minimum_positive_intervals"] == 4
    assert core["E"]["material_degradation_threshold_pct"] == "4.0421728943211638281245344025"
    assert core["F"]["threshold"] == "ALL_REQUIRED_MATERIAL_FAILURE_IS_FAIL"
    assert core["G"]["threshold"] == "GTE_5_ACCEPTABLE__EQ_4_MIXED_LIMITED_SAMPLE__LT_4_INCONCLUSIVE"


def test_exactly_four_quality_dimensions_have_frozen_thresholds() -> None:
    criteria = _summary()["success_criteria"]
    quality = {row["dimension"]: row for row in criteria["quality_dimensions"]}
    assert tuple(row["dimension_id"] for row in criteria["quality_dimensions"]) == QUALITY_DIMENSION_IDS
    assert len(quality) == 4
    assert quality["H"]["threshold"] == "BOTH_NONNEGATIVE"
    assert quality["I"]["threshold"] == "0.5_EXCLUSIVE"
    assert quality["J"]["threshold"] == "26.36049541"
    assert quality["K"]["threshold"] == "14.463510402"


def test_strong_pass_and_pass_mapping_are_deterministic() -> None:
    common = dict(
        core_pass=_core(),
        completed_intervals=6,
        net_ending_equity_gt_start=True,
        cumulative_after_cost_positive=True,
    )
    assert classify_validation_result(
        **common, quality_pass_count=3, net_cagr_pct=14.463510402, max_drawdown_magnitude_pct=26.36049541
    ) == "STRONG_PASS"
    assert classify_validation_result(
        **common, quality_pass_count=2, net_cagr_pct=13, max_drawdown_magnitude_pct=27
    ) == "PASS"


def test_mixed_and_limited_sample_mapping_are_deterministic() -> None:
    assert classify_validation_result(
        core_pass=_core(B=False),
        quality_pass_count=2,
        completed_intervals=6,
        net_ending_equity_gt_start=True,
        net_cagr_pct=10,
        max_drawdown_magnitude_pct=25,
        cumulative_after_cost_positive=True,
    ) == "MIXED"
    assert classify_validation_result(
        core_pass=_core(G=False),
        quality_pass_count=4,
        completed_intervals=4,
        net_ending_equity_gt_start=True,
        net_cagr_pct=20,
        max_drawdown_magnitude_pct=20,
        cumulative_after_cost_positive=True,
    ) == "MIXED_LIMITED_SAMPLE"


def test_fail_and_inconclusive_mapping_are_deterministic() -> None:
    assert classify_validation_result(
        core_pass=_core(A=False),
        quality_pass_count=0,
        completed_intervals=6,
        net_ending_equity_gt_start=False,
        net_cagr_pct=-1,
        max_drawdown_magnitude_pct=20,
        cumulative_after_cost_positive=False,
    ) == "FAIL"
    assert classify_validation_result(
        core_pass=_core(),
        quality_pass_count=4,
        completed_intervals=3,
        net_ending_equity_gt_start=True,
        net_cagr_pct=20,
        max_drawdown_magnitude_pct=20,
        cumulative_after_cost_positive=True,
    ) == "INCONCLUSIVE"


def test_fatal_condition_mapping_is_deterministic() -> None:
    assert all(
        fatal_condition_classification(fatal_id, "IMPLEMENTATION_OR_ARTIFACT_DEFECT") == "FAIL"
        for fatal_id in "ABC"
    )
    assert all(
        fatal_condition_classification(fatal_id, "IMPLEMENTATION_OR_ARTIFACT_DEFECT") == "INCONCLUSIVE"
        for fatal_id in "DEF"
    )
    assert all(
        fatal_condition_classification(fatal_id, "CANDIDATE_OR_GOVERNANCE") == "FAIL"
        for fatal_id in "ABCDEF"
    )


def test_generalization_and_strategy_v2_advancement_mappings_are_exact() -> None:
    criteria = _summary()["success_criteria"]
    assert criteria["generalization_mapping"] == {
        "STRONG_PASS": "STRONG_GENERALIZATION",
        "PASS": "GENERALIZES",
        "MIXED": "MIXED_GENERALIZATION",
        "MIXED_LIMITED_SAMPLE": "MIXED_GENERALIZATION",
        "FAIL": "DOES_NOT_GENERALIZE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }
    advancement = criteria["strategy_v2_advancement_mapping"]
    assert advancement["STRONG_PASS"] == advancement["PASS"] == "ELIGIBLE_FOR_STRATEGY_V2_CANDIDATE_REVIEW"
    assert advancement["MIXED"].startswith("NOT_ELIGIBLE")
    assert advancement["FAIL"] == "REJECT_VALIDATION_CANDIDATE"
    assert advancement["INCONCLUSIVE"] == "NO_DECISION"
    assert criteria["strategy_v2_auto_creation_allowed"] is False


def test_lifecycle_run_count_authorization_and_contamination_are_sealed() -> None:
    governance = _summary()["governance"]
    assert LIFECYCLE == governance["current_lifecycle"] == "SEALED_DESIGN"
    assert VALIDATION_RUN_COUNT == governance["validation_run_count"] == 0
    assert governance["maximum_formal_run_count"] == 1
    assert governance["authorization_granted"] is False
    assert governance["FAMILY_A_ONE_SHOT_VALIDATION_READINESS"] == "YES"
    assert all(governance["one_shot_readiness_checks"].values())
    assert governance["next_transition_requires_explicit_user_authorization"] is True
    assert governance["contamination_disclosure"] == CONTAMINATION_DISCLOSURE
    assert governance["replacement_run_exception"]["original_run_must_be_invalidated_before_replacement"] is True


def test_structural_data_readiness_is_available_with_disclosed_limitations() -> None:
    readiness = _summary()["data_readiness"]
    assert readiness["FAMILY_A_VALIDATION_DATA_READINESS"] == "READY_WITH_LIMITATIONS"
    assert readiness["structural_data_sufficient"] is True
    assert readiness["calendar"]["first_eligible_validation_session"] == "2025-01-01"
    assert readiness["calendar"]["last_eligible_validation_session"] == "2026-08-13"
    assert readiness["adjusted_data"]["missing_required_session_partition_count"] == 0
    assert readiness["adjusted_data"]["rows_read"] == 0
    assert set(readiness["point_in_time_membership"]["formation_date_member_counts"].values()) == {500}
    assert len(readiness["limitations"]) == 3


def test_no_validation_outcomes_holdings_or_performance_were_accessed() -> None:
    summary = _summary()
    governance = summary["governance"]
    readiness = summary["data_readiness"]
    assert governance["validation_outcomes_accessed"] is False
    assert governance["validation_holdings_generated"] is False
    assert governance["validation_performance_calculated"] is False
    assert readiness["validation_price_values_read"] is False
    assert readiness["validation_returns_read"] is False
    assert readiness["validation_holdings_read"] is False
    assert readiness["validation_performance_read"] is False
    assert governance["future_validation_output_contract"]["status"] == "UNPOPULATED_DESIGN_ONLY"


def test_source_contains_no_validation_runner_or_price_loader() -> None:
    source_path = REPO_ROOT / "backend/app/research/strategy/family_a_validation_design.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_load_adjusted_bars" not in names
    assert "run_backtest" not in names
    assert "evaluate_strategy" not in names
    source = source_path.read_text(encoding="utf-8")
    assert "holdout_validation" not in source


def test_reports_are_present_and_performance_cells_are_unpopulated() -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    candidate_rows = _csv(REPORT_ROOT / REPORT_NAMES[1])
    criteria_rows = _csv(REPORT_ROOT / REPORT_NAMES[3])
    assert len(candidate_rows) == 1
    assert candidate_rows[0]["validation_outcome"] == "UNPOPULATED"
    assert len(criteria_rows) == 11
    assert {row["validation_value"] for row in criteria_rows} == {"UNPOPULATED"}
    schedule_rows = _csv(REPORT_ROOT / REPORT_NAMES[2])
    assert len(schedule_rows) == 7
    assert not any(any("return" in key.lower() for key in row) for row in schedule_rows)


def test_manifest_all_design_hashes_and_component_hashes_recompute() -> None:
    manifest = _manifest()
    summary = _summary()
    assert manifest["family_a_validation_design_hash"] == canonical_hash(
        {key: value for key, value in manifest.items() if key != "family_a_validation_design_hash"}
    )
    assert summary["family_a_validation_design_hash"] == manifest["family_a_validation_design_hash"]
    docs = {
        "family_a_validation_candidate_identity_hash": summary["candidate_identity"],
        "family_a_validation_schedule_hash": summary["schedule"],
        "family_a_validation_success_criteria_hash": summary["success_criteria"],
        "family_a_validation_data_readiness_hash": summary["data_readiness"],
        "family_a_validation_design_config_hash": summary["design_config"],
    }
    for hash_field, document in docs.items():
        assert document[hash_field] == canonical_hash(
            {key: value for key, value in document.items() if key != hash_field}
        )
        assert manifest["design_hashes"][hash_field] == document[hash_field]
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["component_hashes"].items()
    )


def test_regression_statuses_and_safety_counters_are_preserved() -> None:
    synthesis = _json(REPORT_ROOT / "cross_family_synthesis_v1_summary.json")
    assert synthesis["cross_family_synthesis_hash"] == SYNTHESIS_HASH
    regressions = synthesis["regressions"]
    assert regressions["all_closure_hashes_unchanged"] is True
    assert all(
        regressions[name] == "PRESERVED"
        for name in (
            "Strategy_V1",
            "CAP4",
            "Family_A",
            "Family_B",
            "Family_C",
            "Family_D",
            "Family_E",
            "Family_F",
            "Family_G",
        )
    )
    safety = _manifest()["safety"]
    assert safety == {
        "network_accessed": False,
        "credentials_written": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "external_writes": 0,
    }


def test_documentation_and_roadmap_show_design_only_state() -> None:
    documentation = (
        REPO_ROOT / "docs/family-a-one-shot-validation-design-v1.md"
    ).read_text(encoding="utf-8")
    assert "SEALED_DESIGN" in documentation
    assert "TERMINAL_MARK_TO_MARKET_DIAGNOSTIC" in documentation
    assert CONTAMINATION_DISCLOSURE in documentation
    assert "No validation run has occurred" in documentation
    roadmap = (
        REPO_ROOT / "docs/strategy-family-research-roadmap-v2.md"
    ).read_text(encoding="utf-8")
    assert "A_TO_G_DISCOVERY_STATUS = COMPLETE" in roadmap
    assert "CROSS_FAMILY_EVIDENCE_SYNTHESIS_STATUS = COMPLETE" in roadmap
    assert "PROVISIONAL_CANDIDATE = FAMILY_A_MOM_A_002_A2_002" in roadmap
    assert "VALIDATION_DESIGN_STATUS = ACTIVE" in roadmap
    assert "VALIDATION_EXECUTION_STATUS = NOT_AUTHORIZED" in roadmap
    assert "STRATEGY_V2_STATUS = NOT_CREATED" in roadmap
    assert "FAMILY_H_STATUS = NOT_PLANNED" in roadmap
