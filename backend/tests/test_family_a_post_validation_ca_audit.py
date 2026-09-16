from __future__ import annotations

import inspect
import json
from pathlib import Path

from app.research.strategy import family_a_post_validation_ca_audit as audit
from app.research.strategy.family_a_momentum import file_sha256
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = (
    ROOT / "data/research/validation/family_a/v1/post_validation_ca_audit"
)
SUMMARY = json.loads(
    (ROOT / "data/reports/family_a_ca_audit_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        AUDIT_ROOT
        / "manifests/family_a_post_validation_ca_audit_manifest_v1.json"
    ).read_text(encoding="utf-8")
)


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_profile_and_audit_manifest_are_exact() -> None:
    assert audit.COMMAND_VERSION == "FAMILY_A_POST_VALIDATION_CA_ELIGIBILITY_AUDIT_V1"
    assert audit.COMMAND_PROFILE == "CORPORATE_ACTION_ELIGIBILITY_ROOT_CAUSE_V1"
    assert MANIFEST["manifest_version"] == "FAMILY_A_POST_VALIDATION_CA_AUDIT_MANIFEST_V1"
    assert _hash_without(MANIFEST, "family_a_post_validation_ca_audit_manifest_hash") == (
        MANIFEST["family_a_post_validation_ca_audit_manifest_hash"]
    )


def test_formal_validation_manifest_hash_and_current_state_remain_exact() -> None:
    verified = audit.verify_formal_validation(ROOT)
    assert verified["formal_validation_manifest_hash"] == (
        "e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8"
    )
    assert verified["formal_validation_result_hash"] == (
        "be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9"
    )
    assert verified["VALIDATION_RESULT"] == "INCONCLUSIVE"
    assert verified["FAMILY_A_GENERALIZATION_RESULT"] == "INCONCLUSIVE"
    assert verified["STRATEGY_V2_ADVANCEMENT_STATUS"] == "NO_DECISION"
    assert verified["completed_valid_formal_runs"] == 1
    assert verified["remaining_formal_runs"] == 0


def test_audited_and_development_dates_are_frozen() -> None:
    assert MANIFEST["audited_dates"] == [
        "2024-12-31",
        "2025-03-28",
        "2025-06-30",
        "2025-09-30",
    ]
    assert MANIFEST["development_comparison_dates"] == [
        "2023-03-31",
        "2024-03-28",
        "2024-09-30",
    ]


def test_ca_source_and_derived_coverage_boundaries_are_exact() -> None:
    source = SUMMARY["source_coverage"]
    layers = {row["layer"]: row for row in source["layers"]}
    assert source["source_data_status"] == "RAW_DATA_PRESENT"
    assert source["pre_validation_dataset_boundary_found"] is False
    assert (layers["RAW_CORPORATE_ACTIONS"]["earliest_date"], layers["RAW_CORPORATE_ACTIONS"]["latest_date"]) == (
        "2021-09-07",
        "2026-09-07",
    )
    assert (layers["NORMALIZED_CORPORATE_ACTIONS"]["earliest_date"], layers["NORMALIZED_CORPORATE_ACTIONS"]["latest_date"]) == (
        "2021-09-07",
        "2026-09-07",
    )
    assert (layers["PRICE_ADJUSTMENT_FACTORS"]["earliest_date"], layers["PRICE_ADJUSTMENT_FACTORS"]["latest_date"]) == (
        "2021-09-08",
        "2026-09-04",
    )
    derived = SUMMARY["derived_coverage"]
    assert derived["derived_layer_status"] == "SOURCE_PRESENT_DERIVED_PRESENT"
    assert derived["source_present_derived_missing"] is False
    assert derived["methodology_version"] == "PRICE_ADJUSTED_STRUCTURAL_V1"
    assert derived["exclusion_policy_version"] == "CORPORATE_ACTION_EXCLUSIONS_V1"


def test_first_three_fail_globally_and_recovery_is_exact() -> None:
    by_date = {row["formation_date"]: row for row in SUMMARY["date_evidence"]}
    for formation in ("2024-12-31", "2025-03-28", "2025-06-30"):
        row = by_date[formation]
        assert row["ptit_member_count"] == 500
        assert row["ca_eligible_count"] == 0
        assert row["ca_excluded_count"] == 500
        assert row["dominant_exclusion_reason"] == "NO_LOOKBACK_START"
        assert row["global_boundary_hit"] is True
    recovery = by_date["2025-09-30"]
    assert recovery["ptit_member_count"] == 500
    assert recovery["ca_eligible_count"] == 481
    assert recovery["final_candidate_universe_count"] == 340
    assert recovery["lookback_start"] == "2025-03-27"
    assert recovery["global_boundary_hit"] is False


def test_exclusion_classification_keeps_exact_reasons_distinct() -> None:
    exclusions = json.loads(
        (AUDIT_ROOT / "exclusions/exclusion_breakdown_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert exclusions["all_rows_explained"] is True
    assert exclusions["detail_row_count"] == 1519
    allowed = set(exclusions["category_allowlist"])
    assert allowed == set(audit.EXCLUSION_CATEGORIES)
    observed = {
        (row["formation_date"], row["exclusion_category"]): row[
            "excluded_security_count"
        ]
        for row in exclusions["breakdown"]
    }
    assert observed[("2024-12-31", "OTHER")] == 500
    assert observed[("2025-03-28", "OTHER")] == 500
    assert observed[("2025-06-30", "OTHER")] == 500
    assert observed[("2025-09-30", "MANUAL_REVIEW_REQUIRED")] == 16
    assert observed[("2025-09-30", "STRUCTURAL_EXCLUSION")] == 3


def test_identity_mapping_resolves_all_audited_members() -> None:
    identity = SUMMARY["identity_audit"]
    assert identity["identity_defect_found"] is False
    validation_rows = [
        row for row in identity["formations"] if row["period"] == "VALIDATION"
    ]
    assert len(validation_rows) == 4
    assert all(row["ptit_member_count"] == 500 for row in validation_rows)
    assert all(row["identity_resolved_members"] == 500 for row in validation_rows)
    assert all(row["unresolved"] == 0 for row in validation_rows)


def test_development_and_validation_use_same_ca_helpers_but_inconsistent_calendar_inputs() -> None:
    code = SUMMARY["code_path"]
    assert code["development_and_validation_share_ca_helpers"] is True
    assert code["same_exclusion_policy_version"] is True
    assert code["same_source_semantics"] is True
    assert code["session_input_semantics_consistent"] is False
    assert code["policy_consistency"] == "POLICY_INCONSISTENCY"
    development = SUMMARY["development_comparison"]
    assert [row["ca_eligible_count"] for row in development] == [489, 490, 483]
    assert all(row["global_boundary_hit"] is False for row in development)


def test_missing_data_policy_is_partial_and_global_failure_is_fail_closed() -> None:
    assert SUMMARY["code_path"]["missing_data_policy"] == "PARTIAL"
    root_cause = SUMMARY["root_cause"]
    assert root_cause["all_500_failure_mechanism"] == (
        "ONE_GLOBAL_CALENDAR_BOUNDARY_FAILURE_PROPAGATED_TO_ALL_MEMBERS"
    )
    assert root_cause["independent_security_level_failures"] is False
    assert root_cause["CA_FAILURE_SCOPE"] == "GLOBAL_INFRASTRUCTURE_FAILURE"


def test_root_cause_severity_and_fixability_mapping_are_exact() -> None:
    root_cause = SUMMARY["root_cause"]
    assert root_cause["FAMILY_A_CA_VALIDATION_ROOT_CAUSE"] == "IMPLEMENTATION_LOGIC_DEFECT"
    assert root_cause["CA_VALIDATION_DEFECT_SEVERITY"] == "FATAL_TO_VALIDATION_INTEGRITY"
    assert root_cause["CA_ROOT_CAUSE_FIXABILITY"] == "CODE_FIX_ONLY"
    assert root_cause["source_coverage_gap"] is False
    assert root_cause["derived_layer_coverage_gap"] is False
    assert root_cause["identity_mapping_defect"] is False


def test_replacement_governance_is_not_authorized_and_all_criteria_are_recorded() -> None:
    governance = SUMMARY["governance"]
    assert governance["replacement_validation_governance_status"] == "NOT_AUTHORIZED"
    assert {row["criterion"]: row["status"] for row in governance["criteria"]} == {
        "A": "PASS",
        "B": "PASS",
        "C": "PASS",
        "D": "PASS",
        "E": "PASS",
        "F": "PASS",
    }
    assert governance["automatic_second_validation_allowed"] is False
    assert "POST_OUTCOME_REMEDIATED_VALIDATION" in governance["post_outcome_contamination"]


def test_audit_hashes_and_frozen_ca_source_hashes_are_exact() -> None:
    hashes = SUMMARY["hashes"]
    assert set(hashes) == {
        "family_a_ca_audit_config_hash",
        "family_a_ca_source_coverage_hash",
        "family_a_ca_derived_coverage_hash",
        "family_a_ca_exclusion_breakdown_hash",
        "family_a_ca_root_cause_hash",
        "family_a_ca_governance_assessment_hash",
    }
    assert all(len(value) == 64 for value in hashes.values())
    assert MANIFEST["hashes"] == hashes
    expected = {
        "backend/app/research/strategy/family_a_momentum.py": "1976c9e98ab5ec3a5a2d2b05dcbe51a40180d6745f5c7ec7c8755a9eb6ac9901",
        "backend/app/research/strategy/family_a_one_shot_validation.py": "ef3a7ac4b9c143a3c6f3690565866743d54fa5555708778a50a7001ab38f709a",
        "backend/app/services/nifty500_ca_final_readiness.py": "7201dbab612ba997ad2a00bf16958e653f94fd3475341654a938f22cb106e3e0",
    }
    assert all(file_sha256(ROOT / path) == digest for path, digest in expected.items())


def test_no_validation_rerun_or_mutating_research_call_is_present() -> None:
    source = inspect.getsource(audit.run_post_validation_ca_audit)
    assert "execute_one_shot_validation" not in source
    assert "build_validation_schedules" not in source
    assert "simulate_validation_executable" not in source
    constraints = SUMMARY["constraints"]
    assert constraints["validation_rerun_performed"] is False
    assert constraints["family_a_changed"] is False
    assert constraints["ca_rules_changed"] is False
    assert constraints["ca_data_extended"] is False
    assert constraints["ca_derived_layer_rebuilt"] is False


def test_no_strategy_or_criteria_change_and_no_strategy_v2() -> None:
    constraints = SUMMARY["constraints"]
    assert constraints["validation_criteria_changed"] is False
    assert constraints["strategy_v2_created"] is False
    assert MANIFEST["validation_result"] == "INCONCLUSIVE"
    assert MANIFEST["generalization_result"] == "INCONCLUSIVE"
    assert MANIFEST["strategy_v2_advancement_status"] == "NO_DECISION"


def test_no_live_or_persistent_side_effects() -> None:
    constraints = SUMMARY["constraints"]
    assert constraints["live_signals"] == 0
    assert constraints["live_orders"] == 0
    assert constraints["broker_calls"] == 0
    assert constraints["migrations"] == 0
    assert constraints["supabase_persistence"] == 0
    assert constraints["external_writes"] == 0


def test_no_performance_fields_drive_the_audit() -> None:
    serialized = json.dumps(SUMMARY).lower()
    for prohibited in (
        "ending_equity",
        "cagr",
        "drawdown",
        "interval_return",
        "positive_interval",
        "negative_interval",
    ):
        assert prohibited not in serialized
