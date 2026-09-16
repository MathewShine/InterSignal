from __future__ import annotations

import json
from pathlib import Path

from app.research.strategy import family_a_one_shot_validation as validation
from app.research.strategy import family_a_post_outcome_remediated_validation as post
from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = post.artifact_root(ROOT)
SUMMARY = json.loads(
    (ROOT / "data/reports/family_a_post_outcome_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
RESULT = json.loads(
    (ARTIFACT_ROOT / "results/post_outcome_result_v1.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        ARTIFACT_ROOT
        / "manifests/family_a_post_outcome_remediated_validation_manifest_v1.json"
    ).read_text(encoding="utf-8")
)
AUTHORIZATION = json.loads(
    (ARTIFACT_ROOT / "authorization/authorization_record_v1.json").read_text(
        encoding="utf-8"
    )
)
INPUT_SNAPSHOT = json.loads(
    (ARTIFACT_ROOT / "inputs/input_snapshot_v1.json").read_text(encoding="utf-8")
)
CRITERIA = json.loads(
    (ARTIFACT_ROOT / "criteria/criteria_results_v1.json").read_text(
        encoding="utf-8"
    )
)


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_checkpoint_and_separate_evidence_class_are_exact() -> None:
    assert post.COMMAND_VERSION == "FAMILY_A_POST_OUTCOME_REMEDIATED_VALIDATION_V1"
    assert post.COMMAND_PROFILE == "MOM_A_002_CA_REMEDIATED_EVALUATION_V1"
    assert post.REQUIRED_CHECKPOINT == "a01023be642f1f3f5728bbc60b949e876cb9d1c3"
    checkpoint = AUTHORIZATION["repository_checkpoint"]
    assert checkpoint["head"] == post.REQUIRED_CHECKPOINT
    assert checkpoint["branch"] == "main"
    assert checkpoint["upstream"] == "origin/main"
    assert checkpoint["status"] == "VERIFIED"
    assert RESULT["EVIDENCE_CLASS"] == "POST_OUTCOME_REMEDIATED_VALIDATION"
    assert RESULT["PRISTINE_HOLDOUT_EVIDENCE"] == "NO"
    assert RESULT["FORMAL_ONE_SHOT_REPLACEMENT"] == "NO"


def test_authorization_is_canonical_and_records_known_outcomes() -> None:
    field = "family_a_post_outcome_remediated_authorization_hash"
    assert AUTHORIZATION["authorization_version"] == (
        "FAMILY_A_POST_OUTCOME_REMEDIATED_AUTHORIZATION_V1"
    )
    assert _hash_without(AUTHORIZATION, field) == AUTHORIZATION[field]
    assert AUTHORIZATION["reason"] == "PROVEN_IMPLEMENTATION_DEFECT_REMOVED"
    assert AUTHORIZATION["prior_outcomes_known"] == "YES"
    assert AUTHORIZATION["strategy_changed"] == "NO"
    assert AUTHORIZATION["criteria_changed"] == "NO"
    assert AUTHORIZATION["CA_rules_changed"] == "NO"
    assert AUTHORIZATION["performance_window_changed"] == "NO"


def test_governance_dependency_hashes_are_exact() -> None:
    assert MANIFEST["original_formal_manifest_hash"] == post.FORMAL_MANIFEST_HASH
    assert MANIFEST["original_formal_result_hash"] == post.FORMAL_RESULT_HASH
    assert MANIFEST["root_cause_audit_hash"] == post.ROOT_CAUSE_AUDIT_HASH
    assert MANIFEST["CA_remediation_hash"] == post.CA_REMEDIATION_HASH
    assert AUTHORIZATION["root_cause_audit_hash"] == post.ROOT_CAUSE_AUDIT_HASH
    assert AUTHORIZATION["CA_remediation_hash"] == post.CA_REMEDIATION_HASH


def test_original_formal_artifacts_are_byte_identical() -> None:
    proof = MANIFEST["proof_original_formal_artifacts_unchanged"]
    assert proof["unchanged"] is True
    assert proof["file_hashes_before"] == proof["file_hashes_after"]
    assert {
        relative: file_sha256(ROOT / relative)
        for relative in proof["file_hashes_after"]
    } == proof["file_hashes_after"]
    formal = json.loads(
        (
            ROOT
            / "data/research/validation/family_a/v1/evaluation/results/validation_result_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert formal["family_a_validation_result_hash"] == post.FORMAL_RESULT_HASH
    assert formal["VALIDATION_RESULT"] == "INCONCLUSIVE"
    assert formal["FAMILY_A_GENERALIZATION_RESULT"] == "INCONCLUSIVE"
    assert formal["STRATEGY_V2_ADVANCEMENT_STATUS"] == "NO_DECISION"


def test_exact_candidate_and_sealed_design_hashes_are_unchanged() -> None:
    candidate = SUMMARY["candidate"]
    assert candidate["research_candidate_id"] == "MOM-A-002"
    assert candidate["implementation_id"] == "A2-002"
    assert candidate["source_candidate"]["starting_capital_inr"] == "500000"
    assert candidate["source_candidate"]["frozen_hashes"] == post.EXPECTED_CANDIDATE_HASHES
    assert candidate["candidate_parameter_changed"] is False
    assert CRITERIA["sealed_design_hashes"] == post.EXPECTED_DESIGN_HASHES
    assert CRITERIA["criteria_changed"] is False


def test_corrected_causal_prehistory_and_holdout_boundary_are_exact() -> None:
    causal, performance = validation.prepare_validation_session_windows(ROOT)
    assert causal[0].isoformat() == "2021-09-07"
    assert causal[-1].isoformat() == "2026-08-13"
    assert performance[0].isoformat() == "2025-01-01"
    assert performance[-1].isoformat() == "2026-08-13"
    assert INPUT_SNAPSHOT["performance_window"] == {
        "start": "2025-01-01",
        "end": "2026-08-13",
    }
    assert INPUT_SNAPSHOT["last_loaded_date"] == "2026-08-13"
    assert INPUT_SNAPSHOT["post_holdout_files_loaded"] == 0
    assert INPUT_SNAPSHOT["performance_outside_window_permitted"] is False


def test_structural_remediation_counts_and_126_sessions_are_exact() -> None:
    rows = {row["formation_date"]: row for row in MANIFEST["structural_eligibility"]}
    assert len(rows) == 7
    assert all(row["lookback_session_count"] == 126 for row in rows.values())
    assert all(row["no_lookback_start_count"] == 0 for row in rows.values())
    for formation, counts in post.EXPECTED_STRUCTURAL_COUNTS.items():
        assert (
            rows[formation]["ca_eligible_count"],
            rows[formation]["ca_excluded_count"],
        ) == counts


def test_six_primary_intervals_and_terminal_exclusion_are_exact() -> None:
    intervals = RESULT["completed_intervals"]
    assert len(intervals) == 6
    assert [row["interval_number"] for row in intervals] == list(range(1, 7))
    assert all(row["scope"] == "PRIMARY" for row in intervals)
    assert all(row["included_in_primary_metrics"] is True for row in intervals)
    terminal = RESULT["terminal_mark_to_market_diagnostic"]
    assert terminal["period_start"] == "2026-07-01"
    assert terminal["period_end"] == "2026-08-13"
    assert terminal["included_in_primary_classification"] is False
    assert terminal["data_after_validation_end_used"] is False


def test_first_three_holding_changes_are_reported_without_interpretive_claims() -> None:
    rows = RESULT["completed_intervals"][:3]
    assert [row["candidate_count"] for row in rows] == [339, 338, 356]
    assert [row["selected_count"] for row in rows] == [34, 34, 36]
    assert [row["newly_active_holding_count"] for row in rows] == [33, 32, 34]
    assert all(row["original_formal_candidate_count"] == 0 for row in rows)
    assert all(
        row["holding_change_context"]
        == "ORIGINAL_FORMAL_UNIVERSE_STRUCTURALLY_DISABLED"
        for row in rows
    )


def test_exact_cost_model_reconciliations_and_result_hashes() -> None:
    costs = read_csv(ARTIFACT_ROOT / "ledgers/cost_ledger_v1.csv")
    assert costs
    assert all(row["cost_model"] == "INDIA_EQUITY_COST_MODEL_V1" for row in costs)
    assert all(row["cost_profile"] == "NSE_CASH_DELIVERY_RESEARCH_V1" for row in costs)
    assert all(row["cost_config_hash"] == post.EXPECTED_CANDIDATE_HASHES["cost_config_hash"] for row in costs)
    assert all(row["cost_scenario"] == "COST-SCENARIO-002" for row in costs)
    assert RESULT["metrics"]["cash_reconciliation_violations"] == 0
    assert RESULT["metrics"]["equity_reconciliation_violations"] == 0
    assert RESULT["metrics"]["transaction_costs_inr"] == "7594.37"
    assert set(MANIFEST["result_hashes"]) == {
        "family_a_post_outcome_authorization_hash",
        "family_a_post_outcome_input_snapshot_hash",
        "family_a_post_outcome_candidate_hash",
        "family_a_post_outcome_holdings_hash",
        "family_a_post_outcome_portfolio_ledger_hash",
        "family_a_post_outcome_cost_ledger_hash",
        "family_a_post_outcome_criteria_hash",
        "family_a_post_outcome_result_hash",
    }


def test_sealed_criteria_a_to_g_and_quality_h_to_k_are_applied() -> None:
    core = CRITERIA["core_criteria_A_to_G"]
    quality = CRITERIA["quality_dimensions_H_to_K"]
    assert {key: row["passed"] for key, row in core.items()} == {
        "A": False,
        "B": False,
        "C": True,
        "D": False,
        "E": False,
        "F": True,
        "G": True,
    }
    assert {key: row["passed"] for key, row in quality.items()} == {
        "H": False,
        "I": False,
        "J": True,
        "K": False,
    }
    assert core["B"]["threshold"] == "12.052925335"
    assert core["C"]["threshold"] == "30"
    assert core["D"]["threshold"] == 4
    assert quality["I"]["threshold"] == "GT_0.5"
    assert quality["J"]["threshold"] == "26.36049541"
    assert quality["K"]["threshold"] == "14.463510402"


def test_post_outcome_classification_and_strategy_v2_status_are_separate() -> None:
    assert RESULT["POST_OUTCOME_REMEDIATED_RESULT"] == "FAIL"
    assert RESULT["POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"] == "UNSUPPORTIVE"
    assert RESULT["POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"] == (
        "DOES_NOT_SUPPORT_CANDIDATE_REVIEW"
    )
    assert "VALIDATION_RESULT" not in RESULT
    assert RESULT["strategy_v2_created"] is False
    assert RESULT["original_formal_record"]["VALIDATION_RESULT"] == "INCONCLUSIVE"
    assert RESULT["original_formal_record"]["overwritten_or_reinterpreted"] is False


def test_permanent_disclosures_are_exact_and_retained() -> None:
    assert RESULT["permanent_post_outcome_disclosure"] == post.PERMANENT_DISCLOSURE
    assert AUTHORIZATION["permanent_disclosure"] == post.PERMANENT_DISCLOSURE
    assert RESULT["original_contamination_disclosure"] == (
        validation.CONTAMINATION_DISCLOSURE
    )


def test_result_and_manifest_are_canonical_and_single_use() -> None:
    assert _hash_without(RESULT, "family_a_post_outcome_result_hash") == RESULT[
        "family_a_post_outcome_result_hash"
    ]
    assert _hash_without(
        MANIFEST, "family_a_post_outcome_remediated_validation_manifest_hash"
    ) == MANIFEST["family_a_post_outcome_remediated_validation_manifest_hash"]
    assert MANIFEST["post_outcome_run_number"] == 1
    assert MANIFEST["additional_post_outcome_runs_authorized"] == 0


def test_reports_namespace_documentation_and_security_are_complete() -> None:
    assert all((ROOT / "data/reports" / name).is_file() for name in post.REPORT_NAMES)
    assert all(
        (ARTIFACT_ROOT / relative).is_dir()
        for relative in (
            "authorization",
            "inputs",
            "holdings",
            "ledgers",
            "criteria",
            "results",
            "comparison",
            "manifests",
        )
    )
    assert (ROOT / "docs/family-a-post-outcome-remediated-validation-v1.md").is_file()
    assert (
        ROOT
        / "docs/strategy-family-research-roadmap-v2-post-validation-governance.md"
    ).is_file()
    assert RESULT["security"] == {
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "migrations": 0,
        "supabase_persistence": 0,
        "external_writes": 0,
    }
    assert RESULT["strategy_v2_created"] is False
