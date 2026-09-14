from __future__ import annotations

import csv
import json
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
)
from app.research.strategy.family_b_b002_clean_reevaluation import (
    EXPECTED_B002_CLEAN_REEVALUATION_HASH,
    EXPECTED_CLEAN_B002_RESULT_HASH,
    EXPECTED_CLEAN_CONTROL_RESULT_HASH,
    EXPECTED_CLEAN_RUN_MANIFEST_HASH,
)
from app.research.strategy.family_b_development_evaluation import (
    EXPECTED_RESULT_HASHES,
)
from app.research.strategy.family_b_history_remediation import (
    DATA_VERSION,
    EXPECTED_ADJUSTED_EXTENSION_HASH,
    EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
    EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    EXPECTED_RAW_EXTENSION_HASH,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
)
from app.research.strategy.family_b_research_closure import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_FAMILY_B_CLOSURE_HASH,
    FAMILY_B_EVIDENCE_STATUS,
    FAMILY_B_RESEARCH_STATUS,
    FAMILY_B_STRATEGY_V2_STATUS,
    FAMILY_B_VALIDATION_STATUS,
    GOVERNANCE_POLICY_VERSION,
    MOM_B_001_FINAL_STATUS,
    MOM_B_002_FINAL_STATUS,
    NEXT_PLANNED_RESEARCH_FAMILY,
    PROHIBITED_INCREMENTAL_TUNING,
    REPORT_NAMES,
    RESEARCH_LESSON_ID,
    family_b_baseline_snapshot,
    family_c_planning_note,
    output_root,
    research_lesson,
    verify_family_b_closure_inputs,
)
from app.research.strategy.family_a_momentum import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_closure_v1_summary.json"
OUTPUT_ROOT = output_root(REPO_ROOT)


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_exact_command_identity_and_family_statuses() -> None:
    assert COMMAND_VERSION == "FAMILY_B_RESEARCH_CLOSURE_V1"
    assert COMMAND_PROFILE == "RELATIVE_ABSOLUTE_MOMENTUM_CLOSURE_V1"
    assert FAMILY_B_RESEARCH_STATUS == "PAUSED_NO_VALIDATION_CANDIDATE"
    assert FAMILY_B_EVIDENCE_STATUS == "NO_CLEAR_INCREMENTAL_EDGE_OVER_RELATIVE_MOMENTUM"
    assert FAMILY_B_VALIDATION_STATUS == "NOT_ACCESSED"
    assert FAMILY_B_STRATEGY_V2_STATUS == "NOT_CREATED"


def test_all_frozen_family_b_input_hashes_verify() -> None:
    verified = verify_family_b_closure_inputs(REPO_ROOT)
    assert verified["status"] == "VERIFIED"
    assert all(verified["checks"].values())
    assert verified["clean_gate"]["snapshot"]["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH
    assert verified["clean_gate"]["snapshot"]["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert {
        record_id: result["development_result_hash"]
        for record_id, result in verified["command_02_results"].items()
    } == EXPECTED_RESULT_HASHES


def test_attribution_and_remediation_hashes_are_exact() -> None:
    closure = summary()["closure"]
    assert closure["attribution_audit_hash"] == EXPECTED_ATTRIBUTION_AUDIT_HASH
    assert closure["history_remediation"] == {
        "data_version": DATA_VERSION,
        "preservation_status": "PRESERVED_SHARED_RESEARCH_INFRASTRUCTURE",
        "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
        "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
        "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
        "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
        "history_remediation_manifest_hash": EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    }


def test_clean_b002_and_control_hashes_are_exact() -> None:
    closure = summary()["closure"]
    assert closure["control"]["clean_control_result_hash"] == EXPECTED_CLEAN_CONTROL_RESULT_HASH
    assert closure["B002_clean"]["clean_b002_result_hash"] == EXPECTED_CLEAN_B002_RESULT_HASH
    assert closure["B002_clean"]["b002_clean_reevaluation_hash"] == EXPECTED_B002_CLEAN_REEVALUATION_HASH
    assert closure["B002_clean"]["clean_run_manifest_hash"] == EXPECTED_CLEAN_RUN_MANIFEST_HASH


def test_b001_is_closed_as_redundant_with_zero_filter_effect() -> None:
    b001 = summary()["closure"]["B001"]
    assert MOM_B_001_FINAL_STATUS == "CLOSED_REDUNDANT_FILTER"
    assert b001["final_status"] == MOM_B_001_FINAL_STATUS
    assert b001["candidate_count"] == b001["filter_pass_count"] == 302
    assert b001["filter_removed_count"] == 0
    assert b001["distinct_filter_evidence"] == "NONE"
    assert b001["parameter_hash"] == EXPECTED_EXPERIMENT_HASHES["MOM-B-001"]["parameter_hash"]
    assert b001["preregistration_hash"] == EXPECTED_EXPERIMENT_HASHES["MOM-B-001"]["preregistration_hash"]


def test_b002_is_closed_for_insufficient_distinct_evidence() -> None:
    closure = summary()["closure"]
    original = closure["B002_original"]
    clean = closure["B002_clean"]
    assert MOM_B_002_FINAL_STATUS == "CLOSED_INSUFFICIENT_DISTINCT_EVIDENCE"
    assert original["trend_filter_evidence"] == "CONFOUNDED_BY_HISTORY_AVAILABILITY"
    assert original["development_advantage_attribution"] == "PRIMARILY_HISTORY_AVAILABILITY"
    assert clean["clean_result"] == "SUPPORTED"
    assert clean["trend_filter_evidence"] == "WEAK"
    assert clean["development_attribution"] == "EVIDENCE_TOO_SPARSE"
    assert clean["true_below_SMA200_removals"] == 1
    assert clean["top_decile_candidates"] == 302
    assert clean["final_status"] == MOM_B_002_FINAL_STATUS


def test_validation_and_strategy_v2_are_not_accessed_or_created() -> None:
    result = summary()
    assert result["statuses"]["FAMILY_B_VALIDATION_STATUS"] == "NOT_ACCESSED"
    assert result["statuses"]["FAMILY_B_STRATEGY_V2_STATUS"] == "NOT_CREATED"
    assert result["governance"]["validation_accessed"] is False
    assert result["governance"]["validation_rows_loaded"] == 0
    assert result["governance"]["strategy_v2_created"] is False


def test_no_performance_run_new_experiment_or_alternate_filter() -> None:
    governance = summary()["governance"]
    assert governance["performance_recomputed"] is False
    assert governance["new_performance_experiments"] == 0
    assert governance["alternate_MA_tested"] is False
    assert governance["alternate_absolute_threshold_tested"] is False
    assert governance["B003_created"] is False
    assert governance["combined_filter_tested"] is False
    assert governance["family_b_incremental_parameter_tuning_authorized"] is False
    assert tuple(governance["prohibited_without_independently_justified_new_hypothesis"]) == PROHIBITED_INCREMENTAL_TUNING


def test_research_lesson_is_scoped_to_the_two_tested_definitions() -> None:
    lesson = summary()["research_lesson"]
    assert lesson == research_lesson()
    assert lesson["lesson_id"] == RESEARCH_LESSON_ID
    assert "B001 removed zero" in lesson["interpretation"]
    assert "one genuine" in lesson["interpretation"]
    assert lesson["generalization_to_all_absolute_momentum_prohibited"] is True


def test_daily_history_v2_is_preserved_as_shared_infrastructure() -> None:
    preservation = summary()["daily_history_preservation"]
    assert preservation["data_version"] == "DAILY_HISTORY_PREHISTORY_V2"
    assert preservation["status"] == "PRESERVED_SHARED_RESEARCH_INFRASTRUCTURE"
    assert preservation["family_b_only_disposable"] is False
    assert preservation["raw_extension_hash"] == EXPECTED_RAW_EXTENSION_HASH
    assert preservation["adjusted_extension_hash"] == EXPECTED_ADJUSTED_EXTENSION_HASH


def test_closure_manifest_hash_recomputes_and_is_frozen() -> None:
    manifest_path = OUTPUT_ROOT / "manifest/family_b_closure_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in manifest.items() if key != "family_b_closure_hash"}
    assert manifest["family_b_closure_hash"] == EXPECTED_FAMILY_B_CLOSURE_HASH
    assert canonical_hash(body) == EXPECTED_FAMILY_B_CLOSURE_HASH


def test_closure_artifact_manifest_recomputes_and_all_files_match() -> None:
    path = OUTPUT_ROOT / "manifest/closure_artifact_hashes_v1.json"
    artifact_manifest = json.loads(path.read_text(encoding="utf-8"))
    body = {
        key: value
        for key, value in artifact_manifest.items()
        if key != "closure_artifact_manifest_hash"
    }
    assert canonical_hash(body) == artifact_manifest["closure_artifact_manifest_hash"]
    assert artifact_manifest["family_b_closure_hash"] == EXPECTED_FAMILY_B_CLOSURE_HASH
    for relative_path, expected_hash in artifact_manifest["artifact_hashes"].items():
        artifact = REPO_ROOT / relative_path
        assert artifact.is_file()
        if relative_path == "docs/strategy-family-research-roadmap-v1.md":
            roadmap = artifact.read_text(encoding="utf-8")
            assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
            assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
            assert any(
                state in roadmap
                for state in (
                    "| Family C | Breakout Continuation | NEXT_PLANNED |",
                    "| Family C | Breakout Continuation | ACTIVE_PREREGISTRATION |",
                    "| Family C | Breakout Continuation | ACTIVE_CONTROLLED_IMPLEMENTATION_RESEARCH |",
                    "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
                )
            )
            continue
        assert file_sha256(artifact) == expected_hash


def test_roadmap_preserves_family_b_closure_after_later_family_handoffs() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert any(
        status in roadmap
        for status in (
            "| Family C | Breakout Continuation | NEXT_PLANNED |",
            "| Family C | Breakout Continuation | ACTIVE_PREREGISTRATION |",
            "| Family C | Breakout Continuation | ACTIVE_CONTROLLED_IMPLEMENTATION_RESEARCH |",
            "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
        )
    )
    assert "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |" in roadmap
    for family in "EFG":
        line = next(row for row in roadmap.splitlines() if row.startswith(f"| Family {family} |"))
        assert "PLANNED_NOT_STARTED" in line


def test_family_c_is_a_parameter_free_planning_note_only() -> None:
    note = summary()["family_c_handoff"]
    assert note == family_c_planning_note()
    assert note["NEXT_PLANNED_RESEARCH_FAMILY"] == NEXT_PLANNED_RESEARCH_FAMILY
    assert note["status"] == "NEXT_PLANNED"
    assert note["parameters_defined"] is False
    assert note["numeric_thresholds_defined"] is False
    assert note["experiments_registered"] == 0
    assert note["implementation_started"] is False
    assert note["performance_run"] is False
    assert note["validation_accessed"] is False
    assert note["authorized_to_start"] is False
    assert note["governance_policy_version"] == GOVERNANCE_POLICY_VERSION


def test_baseline_snapshot_is_stable_and_all_prior_records_unchanged() -> None:
    result = summary()
    before = family_b_baseline_snapshot(REPO_ROOT)
    after = family_b_baseline_snapshot(REPO_ROOT)
    assert before == after
    assert result["regression"]["before_snapshot_hash"] == before["snapshot_hash"]
    assert result["regression"]["after_snapshot_hash"] == after["snapshot_hash"]
    assert result["regression"]["baseline_unchanged"] is True
    assert all(
        value == "UNCHANGED"
        for key, value in result["regression"].items()
        if key not in {"before_snapshot_hash", "after_snapshot_hash", "baseline_unchanged"}
    )


def test_evidence_report_contains_control_b001_original_and_clean_b002() -> None:
    rows = csv_rows(REPO_ROOT / "data/reports/family_b_closure_v1_evidence.csv")
    assert [row["evidence_id"] for row in rows] == [
        "CONTROL-B-000",
        "MOM-B-001",
        "MOM-B-002",
        "MOM-B-002-CLEAN-REEVALUATION",
    ]
    assert rows[1]["final_status"] == MOM_B_001_FINAL_STATUS
    assert rows[3]["final_status"] == MOM_B_002_FINAL_STATUS


def test_required_reports_documentation_and_storage_exist() -> None:
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    assert (REPO_ROOT / "docs/strategy-family-b-closure-v1.md").is_file()
    assert {path.name for path in OUTPUT_ROOT.iterdir() if path.is_dir()} == {
        "manifest",
        "governance",
        "handoff",
    }


def test_security_and_external_side_effect_counts_are_zero() -> None:
    governance = summary()["governance"]
    for key in (
        "live_signals_generated",
        "live_orders_placed",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "database_writes",
        "network_calls",
        "secrets_written",
    ):
        assert governance[key] == 0
