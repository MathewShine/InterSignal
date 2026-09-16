from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from app.research.strategy import family_a_ca_lookback_remediation as remediation
from app.research.strategy import family_a_one_shot_validation as validation
from app.research.strategy.family_a_momentum import LOOKBACK_SESSIONS, file_sha256
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = (
    ROOT / "data/research/validation/family_a/v1/ca_remediation"
)
SUMMARY = json.loads(
    (ROOT / "data/reports/family_a_ca_remediation_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        ARTIFACT_ROOT
        / "manifests/family_a_ca_lookback_remediation_manifest_v1.json"
    ).read_text(encoding="utf-8")
)


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_profile_checkpoint_and_manifest_are_exact() -> None:
    assert remediation.COMMAND_VERSION == "FAMILY_A_CA_LOOKBACK_REMEDIATION_V1"
    assert remediation.COMMAND_PROFILE == "VALIDATION_PREHISTORY_SEMANTICS_FIX_V1"
    assert remediation.REQUIRED_CHECKPOINT == (
        "f41801acf01b69fa55353ebb07ae01ae86fc02b0"
    )
    checkpoint = SUMMARY["repository_checkpoint"]
    assert checkpoint["head"] == remediation.REQUIRED_CHECKPOINT
    assert checkpoint["branch"] == "main"
    assert checkpoint["validation_source_hash_at_checkpoint"] == (
        remediation.EXPECTED_VALIDATION_SOURCE_HASH_BEFORE_REMEDIATION
    )
    assert checkpoint["status"] == "VERIFIED"
    assert MANIFEST["manifest_version"] == (
        "FAMILY_A_CA_LOOKBACK_REMEDIATION_MANIFEST_V1"
    )
    assert _hash_without(
        MANIFEST, "family_a_ca_lookback_remediation_manifest_hash"
    ) == MANIFEST["family_a_ca_lookback_remediation_manifest_hash"]


def test_root_cause_audit_and_formal_validation_hashes_are_unchanged() -> None:
    assert MANIFEST["root_cause_audit_hash"] == (
        "a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793"
    )
    assert MANIFEST["formal_validation_manifest_hash"] == (
        "e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8"
    )
    assert MANIFEST["formal_validation_result_hash"] == (
        "be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9"
    )
    formal = SUMMARY["formal_validation"]
    assert formal["VALIDATION_RESULT"] == "INCONCLUSIVE"
    assert formal["FAMILY_A_GENERALIZATION_RESULT"] == "INCONCLUSIVE"
    assert formal["STRATEGY_V2_ADVANCEMENT_STATUS"] == "NO_DECISION"
    assert formal["completed_valid_formal_runs"] == 1
    assert formal["remaining_formal_runs"] == 0
    assert SUMMARY["formal_validation_file_hashes_before"] == (
        SUMMARY["formal_validation_file_hashes_after"]
    )


def test_exact_126_session_semantics_and_window_separation() -> None:
    causal, performance = validation.prepare_validation_session_windows(ROOT)
    assert LOOKBACK_SESSIONS["6M"] == 126
    assert causal[0].isoformat() == "2021-09-07"
    assert causal[-1].isoformat() == "2026-08-13"
    assert performance[0].isoformat() == "2025-01-01"
    assert performance[-1].isoformat() == "2026-08-13"
    assert all(validation.VALIDATION_START <= row <= validation.VALIDATION_END for row in performance)
    assert all(row <= validation.VALIDATION_END for row in causal)


def test_before_after_fixture_reproduces_original_failure_and_fix() -> None:
    rows = SUMMARY["before_after_fixture"]["rows"]
    assert rows[0]["state"] == "BEFORE_VALIDATION_TRUNCATED_CALENDAR"
    assert rows[0]["lookback_start"] is None
    assert rows[0]["corporate_action_safe"] is False
    assert rows[0]["corporate_action_reasons"] == ["NO_LOOKBACK_START"]
    assert rows[1]["state"] == "AFTER_FULL_CAUSAL_HISTORY"
    assert rows[1]["lookback_start"] == "2024-06-28"
    assert rows[1]["lookback_session_count"] == 126
    assert rows[1]["corporate_action_safe"] is True


def test_all_validation_formations_have_causal_history_and_no_global_failure() -> None:
    rows = SUMMARY["structural_eligibility"]["formations"]
    assert len(rows) == 7
    assert all(row["point_in_time_member_count"] == 500 for row in rows)
    assert all(row["lookback_session_count"] == 126 for row in rows)
    assert all(row["no_lookback_start_count"] == 0 for row in rows)
    assert SUMMARY["structural_eligibility"]["POST_REMEDIATION_CA_FAILURE_SCOPE"] == (
        "NORMAL_SYMBOL_LEVEL_ELIGIBILITY"
    )


def test_first_three_ca_counts_are_normal_symbol_level_outcomes() -> None:
    rows = {
        row["formation_date"]: row
        for row in SUMMARY["structural_eligibility"]["formations"]
    }
    assert (rows["2024-12-31"]["ca_eligible_count"], rows["2024-12-31"]["ca_excluded_count"]) == (487, 13)
    assert (rows["2025-03-28"]["ca_eligible_count"], rows["2025-03-28"]["ca_excluded_count"]) == (493, 7)
    assert (rows["2025-06-30"]["ca_eligible_count"], rows["2025-06-30"]["ca_excluded_count"]) == (486, 14)


def test_2025_09_30_ca_regression_is_exact() -> None:
    row = next(
        row
        for row in SUMMARY["structural_eligibility"]["formations"]
        if row["formation_date"] == "2025-09-30"
    )
    assert row["ca_eligible_count"] == 481
    assert row["ca_excluded_count"] == 19
    assert row["ca_exclusion_reasons"] == {
        "complex_restructuring_exclusion_v1": 3,
        "rights_exclusion_v1": 2,
        "special_dividend_exclusion_v1": 14,
    }


def test_development_dates_are_unchanged() -> None:
    regression = SUMMARY["development_regression"]
    assert regression["all_development_dates_unchanged"] is True
    assert [row["current_ca_eligible_count"] for row in regression["rows"]] == [
        489,
        490,
        483,
    ]
    assert all(row["unchanged"] is True for row in regression["rows"])


def test_ca_rules_candidate_strategy_and_criteria_are_immutable() -> None:
    frozen = SUMMARY["frozen_semantics"]
    assert frozen["ca_rules_unchanged"] is True
    assert frozen["strategy_unchanged"] is True
    assert frozen["criteria_unchanged"] is True
    assert frozen["ca_rule_source_hash"] == (
        "1976c9e98ab5ec3a5a2d2b05dcbe51a40180d6745f5c7ec7c8755a9eb6ac9901"
    )
    assert frozen["family_config_hash"] == (
        "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3"
    )
    assert frozen["validation_criteria_hash"] == (
        "89bec4f0b213c0b7a9bf8d1f67e0cf5c853fb3775e1ce9120bbb7933d1bc1ad4"
    )


def test_only_session_input_plumbing_changed_in_validation_source() -> None:
    assert SUMMARY["root_cause_audit"]["manifest_hash"] == remediation.ROOT_CAUSE_AUDIT_HASH
    assert SUMMARY["frozen_semantics"]["frozen_function_hashes"] == (
        remediation.EXPECTED_FROZEN_FUNCTION_HASHES
    )
    assert file_sha256(
        ROOT / "backend/app/research/strategy/family_a_momentum.py"
    ) == remediation.EXPECTED_CA_RULE_SOURCE_HASH


def test_scope_guard_contains_no_prohibited_classification() -> None:
    scope = SUMMARY["scope_guard"]
    assert scope["scope_compliant"] is True
    assert scope["strategy_change"] is False
    assert scope["performance_change"] is False
    assert scope["criteria_change"] is False
    assert scope["result_change"] is False
    observed = {row["classification"] for row in scope["rows"]}
    assert observed <= remediation.ALLOWED_SCOPE_CLASSIFICATIONS
    assert not observed & remediation.PROHIBITED_SCOPE_CLASSIFICATIONS


def test_remediation_never_calls_validation_or_performance_execution() -> None:
    tree = ast.parse(inspect.getsource(remediation))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not called & {
        "execute_one_shot_validation",
        "build_validation_schedules",
        "simulate_validation_executable",
        "calculate_validation_metrics",
        "evaluate_criteria",
        "select_top_decile",
    }
    structural = SUMMARY["structural_eligibility"]
    assert structural["momentum_ranking_performed"] is False
    assert structural["holdings_generated"] is False
    assert structural["performance_calculated"] is False


def test_technical_readiness_is_yes_but_governance_is_not_authorized() -> None:
    readiness = SUMMARY["readiness"]
    assert readiness["FAMILY_A_CA_REMEDIATION_RESULT"] == "FIX_VERIFIED_STRUCTURALLY"
    assert readiness["POST_OUTCOME_REMEDIATED_VALIDATION_TECHNICAL_READINESS"] == "YES"
    assert readiness["REPLACEMENT_VALIDATION_GOVERNANCE_STATUS"] == "NOT_AUTHORIZED"
    assert readiness["technical_readiness_is_authorization"] is False
    assert all(row["passed"] is True for row in readiness["checks"])
    assert "POST_OUTCOME_REMEDIATED_VALIDATION" in readiness["post_outcome_disclosure"]


def test_all_six_remediation_hashes_are_present_and_linked() -> None:
    hashes = SUMMARY["hashes"]
    assert set(hashes) == {
        "family_a_ca_remediation_config_hash",
        "family_a_ca_calendar_fix_hash",
        "family_a_ca_structural_eligibility_hash",
        "family_a_ca_development_regression_hash",
        "family_a_ca_scope_guard_hash",
        "family_a_ca_remediation_readiness_hash",
    }
    assert all(len(value) == 64 for value in hashes.values())
    assert MANIFEST["hashes"] == hashes


def test_reports_and_artifacts_are_complete() -> None:
    required_artifacts = (
        "fixtures/before_after_v1.json",
        "fixtures/before_after_v1.csv",
        "calendar/session_boundary_v1.json",
        "eligibility/formation_structural_results_v1.json",
        "eligibility/formation_structural_results_v1.csv",
        "regression/development_regression_v1.json",
        "regression/development_regression_v1.csv",
        "scope_guard/change_scope_v1.json",
        "scope_guard/change_scope_v1.csv",
        "readiness/technical_readiness_v1.json",
        "readiness/technical_readiness_v1.csv",
        "manifests/family_a_ca_lookback_remediation_manifest_v1.json",
    )
    assert all((ARTIFACT_ROOT / relative).is_file() for relative in required_artifacts)
    required_reports = (
        "family_a_ca_remediation_v1_summary.json",
        "family_a_ca_remediation_v1_before_after.csv",
        "family_a_ca_remediation_v1_formations.csv",
        "family_a_ca_remediation_v1_development_regression.csv",
        "family_a_ca_remediation_v1_scope_guard.csv",
        "family_a_ca_remediation_v1_readiness.csv",
    )
    assert all((ROOT / "data/reports" / name).is_file() for name in required_reports)


def test_no_security_database_or_external_side_effects() -> None:
    constraints = SUMMARY["constraints"]
    assert constraints["validation_holdings_generated"] is False
    assert constraints["validation_performance_calculated"] is False
    assert constraints["validation_rerun_performed"] is False
    assert constraints["strategy_v2_created"] is False
    assert constraints["live_signals"] == 0
    assert constraints["live_orders"] == 0
    assert constraints["broker_calls"] == 0
    assert constraints["migrations"] == 0
    assert constraints["supabase_persistence"] == 0
    assert constraints["external_writes"] == 0
