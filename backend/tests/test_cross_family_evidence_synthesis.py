from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

from app.research.strategy.cross_family_evidence_synthesis import (
    CANDIDATE_SELECTION_CLASSIFICATION,
    CLASSIFICATION_BUCKETS,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTAMINATION_DISCLOSURE,
    DISCOVERY_CYCLE_STATUS,
    FAMILY_A_VALIDATION_CANDIDACY,
    FAMILY_CLASSIFICATIONS,
    FAMILY_CLOSURE_HASHES,
    FAMILY_FINAL_STATUSES,
    FAMILY_H_STATUS,
    INPUT_FILE_HASHES,
    MANIFEST_VERSION,
    MILESTONE_COMMIT,
    NEXT_PLANNED_PHASE,
    PRIMARY_QUESTION_RESULT,
    PROVISIONAL_CANDIDATE_ID,
    PROVISIONAL_CANDIDATE_STATUS,
    REPORT_NAMES,
    STRATEGY_V2_STATUS,
    SYNTHESIS_ROADMAP_COMPONENT_HASH,
    VALIDATION_DESIGN_READINESS,
    synthesis_component_hash_matches,
    verify_git_milestone,
    verify_synthesis_inputs,
)
from app.research.strategy.family_a_momentum import file_sha256
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHESIS_ROOT = REPO_ROOT / "data/research/cross_family_synthesis/v1"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = (
    SYNTHESIS_ROOT / "manifests/cross_family_evidence_synthesis_manifest_v1.json"
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


def test_command_profile_and_milestone_ancestry_are_exact() -> None:
    assert COMMAND_VERSION == "CROSS_FAMILY_EVIDENCE_SYNTHESIS_V1"
    assert COMMAND_PROFILE == "STRATEGY_DISCOVERY_A_TO_G_SYNTHESIS_V1"
    assert MANIFEST_VERSION == "CROSS_FAMILY_EVIDENCE_SYNTHESIS_MANIFEST_V1"
    git = verify_git_milestone(REPO_ROOT)
    assert git["milestone_commit"] == MILESTONE_COMMIT
    assert git["milestone_is_ancestor"] is True
    assert git["branch"] == "main"
    assert git["upstream"] == "origin/main"


def test_all_frozen_input_files_closures_and_statuses_are_verified() -> None:
    verification = verify_synthesis_inputs(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert all(verification["checks"].values())
    assert verification["source_file_hashes"] == INPUT_FILE_HASHES
    assert verification["family_closure_hashes"] == FAMILY_CLOSURE_HASHES
    assert verification["family_final_statuses"] == FAMILY_FINAL_STATUSES
    assert verification["source_snapshot_hash"] == canonical_hash(INPUT_FILE_HASHES)


def test_strategy_v1_and_cap4_context_preserve_required_classifications() -> None:
    rows = {row["entity"]: row for row in _summary()["family_matrix"]}
    assert rows["STRATEGY_V1"]["final_status"] == "WEAK_AND_REQUIRES_RESEARCH"
    assert rows["STRATEGY_V1"]["decision"] == "DO_NOT_SELECT"
    assert rows["CAP4"]["primary_classification"] == "REJECTED_VALIDATION"
    assert rows["CAP4"]["performance_status"] == (
        "DEVELOPMENT_PROMISING_VALIDATION_FAILED"
    )
    assert rows["CAP4"]["final_status"] == "DOES_NOT_GENERALIZE_REJECTED"


def test_each_family_has_exactly_one_allowed_primary_classification() -> None:
    assert len(CLASSIFICATION_BUCKETS) == len(set(CLASSIFICATION_BUCKETS)) == 8
    rows = {
        row["entity"].removeprefix("FAMILY_"): row
        for row in _summary()["family_matrix"]
        if row["entity_type"] == "DISCOVERY_FAMILY"
    }
    assert set(rows) == set("ABCDEFG")
    assert {family: row["primary_classification"] for family, row in rows.items()} == (
        FAMILY_CLASSIFICATIONS
    )
    assert all(row["primary_classification"] in CLASSIFICATION_BUCKETS for row in rows.values())


def test_evidence_dimensions_cover_twelve_dimensions_for_every_family() -> None:
    rows = _summary()["evidence_dimensions"]
    assert len(rows) == 7 * 12
    assert {row["family"] for row in rows} == set("ABCDEFG")
    assert all(
        len([row for row in rows if row["family"] == family]) == 12
        for family in "ABCDEFG"
    )
    assert {row["rating"] for row in rows} <= {
        "STRONG",
        "MODERATE",
        "WEAK",
        "NOT_AVAILABLE",
        "BLOCKED",
    }


def test_family_a_frozen_references_metrics_and_reproduction_are_exact() -> None:
    summary = _summary()
    candidate = summary["candidate_selection"]["provisional_candidate"]
    assert candidate["architecture_reference"] == "MOM-A-002"
    assert candidate["implementation_reference"] == "A2-002"
    assert candidate["reference_capital_inr"] == "500000"
    assert candidate["frozen_references"]["mom_a_002"]["parameter_hash"] == (
        "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8"
    )
    assert candidate["frozen_references"]["a2_002_preregistration"][
        "preregistration_hash"
    ] == "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897"
    assert candidate["frozen_references"]["a2_002_result"]["result_hash"] == (
        "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27"
    )
    assert summary["input_verification"]["checks"]["family_a_result_exact"] is True
    assert summary["input_verification"]["checks"][
        "family_g_reproduced_family_a"
    ] is True


def test_family_f_and_g_closure_hashes_are_exact() -> None:
    manifest = _manifest()
    assert manifest["family_closure_hashes"]["F"] == (
        "515bd3dc996c1e119e3e422f182ba82abfa8f2d312346df2c7a5751322d7716d"
    )
    assert manifest["family_closure_hashes"]["G"] == (
        "2cb2102b207da24b4730cd673869aab1c00534ae8fa09c281639aafaaee6c179"
    )


def test_positive_and_negative_evidence_registries_are_complete() -> None:
    summary = _summary()
    positives = {row["evidence_id"]: row for row in summary["positive_evidence"]}
    assert len(positives) >= 6
    assert {row["level"] for row in positives.values()} == {
        "STRATEGY_LEVEL",
        "SIGNAL_LEVEL",
        "DATA_INFRASTRUCTURE_LEVEL",
    }
    assert "EDGE-EVIDENCE-C-COMPRESSION-001" in positives
    assert "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001" in positives
    negatives = {row["evidence_id"] for row in summary["negative_evidence"]}
    assert {
        "CAP4-VALIDATION-FAILURE",
        "EDGE-NEGATIVE-B-POSITIVE-RETURN-001",
        "EDGE-NEGATIVE-B-SMA200-001",
        "EDGE-NEGATIVE-C-VOLUME-001",
        "IMPLEMENTATION-NEGATIVE-C-COMPRESSION-RANK-001",
        "EDGE-NEGATIVE-E-PULLBACK-RECLAIM-001",
        "EDGE-NEGATIVE-E-SMA50-STRUCTURE-001",
        "EDGE-NEGATIVE-G-SMA200-GATE-001",
    } <= negatives


def test_blocked_research_is_distinguished_from_failed_strategy_evidence() -> None:
    rows = {row["family"]: row for row in _summary()["blocked_research"]}
    assert set(rows) == {"D", "F"}
    assert rows["D"]["classification"] == "DATA_BLOCKED"
    assert "77.826177" in rows["D"]["evidence"]
    assert rows["F"]["classification"] == "SOURCE_BLOCKED"
    assert rows["D"]["failed_strategy"] == "False"
    assert rows["F"]["failed_strategy"] == "False"
    assert all(row["strategy_result"] == "NOT_PERFORMANCE_EVALUATED" for row in rows.values())


def test_family_a_passes_all_ten_candidate_gates_and_no_alternative_passes() -> None:
    selection = _summary()["candidate_selection"]
    gates = selection["family_a_gate_results"]
    assert [row["gate_number"] for row in gates] == list(range(1, 11))
    assert all(row["result"] == "PASS" for row in gates)
    assert selection["all_ten_gates_pass"] is True
    assert selection["FAMILY_A_VALIDATION_CANDIDACY"] == (
        FAMILY_A_VALIDATION_CANDIDACY
    ) == "PASS"
    assert all(
        row["result"] == "FAIL"
        for row in selection["alternative_candidate_results"]
    )
    assert selection["ALTERNATIVE_VALIDATION_CANDIDATE"] == "NONE"


def test_provisional_candidate_is_reference_only_and_not_a_hybrid() -> None:
    candidate = _summary()["candidate_selection"]["provisional_candidate"]
    assert candidate["candidate_id"] == PROVISIONAL_CANDIDATE_ID
    assert candidate["status"] == PROVISIONAL_CANDIDATE_STATUS
    assert candidate["candidate_selection_classification"] == (
        CANDIDATE_SELECTION_CLASSIFICATION
    ) == "SINGLE_LEADING_CANDIDATE"
    assert candidate["strategy_v2"] is False
    assert candidate["validation_run_authorized"] is False
    assert candidate["excluded_overlays"] == [
        "NO_FAMILY_B_FILTER",
        "NO_FAMILY_C_COMPRESSION_OVERLAY",
        "NO_FAMILY_G_REGIME_GATE",
        "NO_CROSS_FAMILY_HYBRID",
    ]


def test_readiness_contamination_win_rate_and_future_statuses_are_explicit() -> None:
    readiness = _summary()["validation_readiness"]
    assert PRIMARY_QUESTION_RESULT == readiness["primary_question_result"] == "YES"
    assert readiness["VALIDATION_DESIGN_READINESS"] == (
        VALIDATION_DESIGN_READINESS
    ) == "YES"
    assert readiness["NEXT_PLANNED_PHASE"] == NEXT_PLANNED_PHASE
    assert readiness["FAMILY_H_STATUS"] == FAMILY_H_STATUS == "NOT_PLANNED"
    assert readiness["STRATEGY_V2_STATUS"] == STRATEGY_V2_STATUS == "NOT_CREATED"
    assert readiness["contamination_disclosure"] == CONTAMINATION_DISCLOSURE
    assert readiness["win_rate_assessment"]["trade_level_win_rate_claimed"] is False
    assert readiness["win_rate_assessment"]["terminology"] == (
        "PORTFOLIO_REBALANCE_PERIOD_NOT_TRADE_WIN_RATE"
    )


def test_no_holdout_access_performance_rerun_new_strategy_or_external_activity() -> None:
    safety = _summary()["safety"]
    assert safety["validation_accessed"] is False
    assert safety["validation_rows_loaded"] == 0
    assert safety["performance_rerun"] is False
    assert safety["new_strategy_created"] is False
    assert safety["hybrid_strategy_created"] is False
    assert safety["family_h_created"] is False
    assert safety["strategy_v2_created"] is False
    assert safety["network_accessed"] is False
    assert safety["credentials_written"] is False
    assert safety["live_signals"] == 0
    assert safety["live_orders"] == 0
    assert safety["broker_calls"] == 0
    assert safety["remote_migrations"] == 0
    assert safety["supabase_persistence"] == 0
    assert safety["external_writes"] == 0


def test_synthesis_source_contains_no_family_performance_or_validation_runner() -> None:
    source_path = (
        REPO_ROOT / "backend/app/research/strategy/cross_family_evidence_synthesis.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("development_evaluation" in name for name in imported)
    assert not any("holdout_validation" in name for name in imported)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not any(name.startswith(("run_", "evaluate_", "validate_")) for name in calls)


def test_reports_storage_manifest_and_component_hashes_are_complete() -> None:
    required_directories = {
        "family_matrix",
        "positive_evidence",
        "negative_evidence",
        "blocked_research",
        "candidate_selection",
        "validation_readiness",
        "manifests",
    }
    assert required_directories <= {
        path.name for path in SYNTHESIS_ROOT.iterdir() if path.is_dir()
    }
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    manifest = _manifest()
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["cross_family_synthesis_hash"] == canonical_hash(
        {
            key: value
            for key, value in manifest.items()
            if key != "cross_family_synthesis_hash"
        }
    )
    assert all((REPO_ROOT / relative).is_file() for relative in manifest["component_hashes"])
    assert all(
        synthesis_component_hash_matches(
            relative, expected, file_sha256(REPO_ROOT / relative)
        )
        for relative, expected in manifest["component_hashes"].items()
    )
    assert manifest["component_hashes"]["docs/strategy-family-research-roadmap-v2.md"] == (
        SYNTHESIS_ROADMAP_COMPONENT_HASH
    )
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[1])) == 9
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[2])) == 84


def test_documentation_roadmap_and_regressions_are_preserved() -> None:
    documentation = (
        REPO_ROOT / "docs/cross-family-evidence-synthesis-a-to-g-v1.md"
    ).read_text(encoding="utf-8")
    assert "What worked" in documentation
    assert "What failed" in documentation
    assert "What was blocked" in documentation
    assert "PROVISIONAL_VALIDATION_CANDIDATE_V1" in documentation
    assert "philosophically pristine laboratory-grade unseen data" in documentation
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v2.md").read_text(
        encoding="utf-8"
    )
    assert "A_TO_G_DISCOVERY_STATUS = COMPLETE" in roadmap
    assert "CROSS_FAMILY_EVIDENCE_SYNTHESIS_STATUS = COMPLETE" in roadmap
    assert "FAMILY_H_STATUS = NOT_PLANNED" in roadmap
    assert "VALIDATION_DESIGN_STATUS = SEALED_COMPLETE" in roadmap
    assert "FAMILY_A_VALIDATION_STATUS = EVALUATED" in roadmap
    assert "NEXT_PLANNED_PHASE = GOVERNANCE_REVIEW_FAMILY_A_INCONCLUSIVE_VALIDATION" in roadmap
    assert DISCOVERY_CYCLE_STATUS == "COMPLETE_FOR_CURRENT_RESEARCH_CYCLE"
    regressions = _summary()["regressions"]
    assert regressions["all_closure_hashes_unchanged"] is True
    assert all(value == "PRESERVED" for key, value in regressions.items() if key != "all_closure_hashes_unchanged")
