from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from app.research.strategy import family_a_post_validation_closure as closure
from app.research.strategy.family_a_momentum import file_sha256
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = closure.output_root(ROOT)
SUMMARY = json.loads(
    (ROOT / "data/reports/family_a_post_validation_closure_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        ARTIFACT_ROOT
        / "manifests/family_a_post_validation_closure_manifest_v1.json"
    ).read_text(encoding="utf-8")
)


def _json(relative: str) -> dict:
    return json.loads((ARTIFACT_ROOT / relative).read_text(encoding="utf-8"))


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_profile_and_manifest_hash_are_exact() -> None:
    assert closure.COMMAND_VERSION == "FAMILY_A_POST_VALIDATION_CLOSURE_V1"
    assert closure.COMMAND_PROFILE == "MOM_A_002_CANDIDATE_REJECTION_GOVERNANCE_V1"
    assert MANIFEST["manifest_version"] == "FAMILY_A_POST_VALIDATION_CLOSURE_MANIFEST_V1"
    assert _hash_without(MANIFEST, "family_a_post_validation_closure_hash") == MANIFEST[
        "family_a_post_validation_closure_hash"
    ]
    assert MANIFEST["family_a_post_validation_closure_hash"] == (
        "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"
    )


def test_formal_validation_is_immutable_and_remains_inconclusive() -> None:
    formal = MANIFEST["formal_validation"]
    assert formal["manifest_hash"] == closure.FORMAL_MANIFEST_HASH
    assert formal["result_hash"] == closure.FORMAL_RESULT_HASH
    assert formal["FAMILY_A_FORMAL_VALIDATION_STATUS"] == "INCONCLUSIVE"
    assert formal["formal_generalization_result"] == "INCONCLUSIVE"
    assert formal["formal_strategy_v2_advancement"] == "NO_DECISION"
    assert formal["rewritten"] is False
    proof = MANIFEST["proof_protected_artifacts_unchanged"]
    assert proof["unchanged"] is True
    assert proof["file_hashes_before"] == proof["file_hashes_after"]
    assert {
        relative: file_sha256(ROOT / relative)
        for relative in proof["file_hashes_after"]
    } == proof["file_hashes_after"]


def test_post_outcome_fail_and_caveat_are_preserved_separately() -> None:
    post = MANIFEST["post_outcome_remediated"]
    assert post["manifest_hash"] == closure.POST_OUTCOME_MANIFEST_HASH
    assert post["result_hash"] == closure.POST_OUTCOME_RESULT_HASH
    assert post["evidence_class"] == "POST_OUTCOME_REMEDIATED_VALIDATION"
    assert post["result"] == "FAIL"
    assert post["generalization_indication"] == "UNSUPPORTIVE"
    assert post["strategy_v2_review_status"] == "DOES_NOT_SUPPORT_CANDIDATE_REVIEW"
    assert post["pristine_holdout"] is False
    assert post["formal_replacement"] is False


def test_family_a_final_status_and_generalization_conclusion_are_frozen() -> None:
    status = _json("governance/family_a_final_status_v1.json")
    assert status["FAMILY_A_VALIDATION_CANDIDATE_STATUS"] == "CLOSED_NOT_ADVANCED"
    assert status["FAMILY_A_STRATEGY_V2_CANDIDACY"] == "REJECTED_FOR_CURRENT_CYCLE"
    assert status["FAMILY_A_FORMAL_VALIDATION_STATUS"] == "INCONCLUSIVE"
    assert status["FAMILY_A_POST_OUTCOME_EVIDENCE_STATUS"] == "UNSUPPORTIVE"
    assert status["FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION"] == (
        "INSUFFICIENT_SUPPORT_FOR_ADVANCEMENT"
    )
    assert "not a pristine validation failure" in status["decision_reason"]


def test_known_holdout_and_no_salvage_policy_are_frozen() -> None:
    holdout = _json("governance/holdout_status_v1.json")
    salvage = _json("governance/no_salvage_policy_v1.json")
    assert holdout["FAMILY_A_2025_2026_HOLDOUT_STATUS"] == (
        "CONTAMINATED_FOR_FUTURE_MODEL_SELECTION"
    )
    assert holdout["permitted_uses"] == ["DIAGNOSTICS", "DOCUMENTATION"]
    assert holdout["prohibited_use"] == "UNSEEN_VALIDATION_FOR_CANDIDATE_SELECTION"
    assert holdout["future_model_selection_requirement"] == (
        "NEW_TEMPORALLY_UNSEEN_PERIOD"
    )
    assert holdout["future_dates_defined"] is False
    assert salvage["FAMILY_A_POST_VALIDATION_TUNING"] == (
        "PROHIBITED_ON_CURRENT_HOLDOUT"
    )
    assert len(salvage["prohibited_on_known_holdout"]) == 12
    assert salvage["variant_tested_by_closure"] is False
    assert salvage["performance_rerun_by_closure"] is False


def test_positive_evidence_and_new_negative_evidence_are_registered() -> None:
    registry = _json("evidence/final_evidence_registry_v1.json")
    rows = {row["evidence_id"]: row for row in registry["rows"]}
    assert rows["EDGE-POSITIVE-A-DEVELOPMENT-001"]["status"] == (
        "HISTORICALLY_STRONG_DEVELOPMENT_EVIDENCE_NOT_GENERALIZED"
    )
    assert rows["EDGE-POSITIVE-A-FAMILY-G-REPRODUCTION-001"]["status"] == (
        "PRESERVED"
    )
    assert rows["EDGE-POSITIVE-A-IMPLEMENTATION-REALISM-001"]["status"] == (
        "PRESERVED"
    )
    negative = rows[closure.NEGATIVE_EVIDENCE_ID]
    assert negative["status"] == "POST_OUTCOME_REMEDIATED_EVIDENCE"
    assert negative["source_hash"] == closure.POST_OUTCOME_RESULT_HASH
    assert registry["frozen_family_artifacts_changed"] is False


def test_development_validation_performance_and_win_rate_lessons_are_exact() -> None:
    development = _json("lessons/family_a_development_lesson_v1.json")
    validation = _json("lessons/family_a_validation_lesson_v1.json")
    performance = _json("lessons/family_a_performance_lesson_v1.json")
    win_rate = _json("lessons/no_win_rate_chasing_v1.json")
    assert development["development_cagr_pct"] == "24.10585067"
    assert "independent temporal validation" in development["lesson"]
    assert "causal prehistory" in validation["lesson"]
    assert performance["post_outcome_remediated_cagr_pct"] == "-2.438579367208471"
    assert performance["interpretation"] == "DESCRIPTIVE_POST_OUTCOME_EVIDENCE"
    assert performance["post_outcome_caveat"] == closure.POST_OUTCOME_CAVEAT
    assert win_rate["desired_win_rate_pct"] == "60_TO_65_ASPIRATION_ONLY"
    assert win_rate["threshold_or_selection_gate"] is False


def test_a_to_g_cycle_is_complete_with_no_validated_strategy() -> None:
    cycle = _json("cycle_closure/a_to_g_final_status_v1.json")
    assert cycle["STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS"] == (
        "COMPLETE_NO_VALIDATED_STRATEGY"
    )
    expected = {
        "A": "STRONG_DEVELOPMENT_NOT_ADVANCED_AFTER_LATER_PERIOD_EVIDENCE",
        "B": "NO_INCREMENTAL_EDGE",
        "C": "REUSABLE_COMPRESSION_SIGNAL_ONLY",
        "D": "DATA_BLOCKED",
        "E": "NEGATIVE_DEVELOPMENT_EVIDENCE",
        "F": "SOURCE_LICENSING_BLOCKED",
        "G": "NEGATIVE_REGIME_OVERLAY_EVIDENCE",
    }
    assert {row["family"]: row["summary"] for row in cycle["families"]} == expected
    assert cycle["STRATEGY_V2_STATUS"] == "NOT_CREATED"
    assert cycle["FAMILY_H_STATUS"] == "NOT_PLANNED"


def test_no_strategy_v2_paper_live_or_production_readiness() -> None:
    status = _json("governance/family_a_final_status_v1.json")
    assert status["STRATEGY_V2_STATUS"] == "NOT_CREATED"
    assert status["INTERSIGNAL_AUTOMATED_STRATEGY_PRODUCTION_READINESS"] == "NO"
    assert status["INTERSIGNAL_STRATEGY_PAPER_TRADING_READINESS"] == (
        "NO_VALIDATED_CANDIDATE"
    )
    assert status["INTERSIGNAL_LIVE_TRADING_READINESS"] == "NOT_READY"
    assert status["FAMILY_H_STATUS"] == "NOT_PLANNED"
    assert status["strategy_v2_created"] is False
    assert status["paper_trading_started"] is False
    assert status["live_trading_started"] is False


def test_next_program_review_handoff_does_not_select_or_start_an_option() -> None:
    handoff = _json("handoff/next_research_cycle_policy_v1.json")
    assert handoff["policy_version"] == "NEXT_RESEARCH_CYCLE_POLICY_V1"
    assert handoff["NEXT_PLANNED_PHASE"] == "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW"
    assert handoff["new_cycle_requirement"] == (
        "EXPLICIT_RESEARCH_HYPOTHESIS_BASED_ON_A_TO_G_LESSONS"
    )
    assert handoff["sequential_family_extension_default"] == "PROHIBITED"
    assert handoff["future_validation_data_policy"] == (
        "NEW_TEMPORALLY_UNSEEN_PERIOD_REQUIRED"
    )
    assert [row["option"] for row in handoff["options"]] == ["A", "B", "C", "D"]
    assert handoff["option_selected"] is None
    assert handoff["next_phase_started"] is False


def test_closure_has_no_performance_execution_call_path() -> None:
    tree = ast.parse(inspect.getsource(closure))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not called & {
        "execute_one_shot_validation",
        "execute_post_outcome_remediated_validation",
        "build_validation_schedules",
        "simulate_validation_executable",
        "calculate_validation_metrics",
        "evaluate_criteria",
    }
    assert MANIFEST["performance_rerun"] is False
    assert MANIFEST["strategy_mutation"] is False
    assert MANIFEST["new_strategy_created"] is False


def test_storage_reports_documentation_roadmap_and_security_are_complete() -> None:
    assert all(
        (ARTIFACT_ROOT / name).is_dir()
        for name in (
            "evidence",
            "governance",
            "lessons",
            "cycle_closure",
            "handoff",
            "manifests",
        )
    )
    assert all((ROOT / "data/reports" / name).is_file() for name in closure.REPORT_NAMES)
    assert (ROOT / "docs/family-a-post-validation-closure-v1.md").is_file()
    assert (ROOT / "docs/post-validation-governance-roadmap-v1.md").is_file()
    assert MANIFEST["security"] == {
        "network_required": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "external_writes": 0,
        "credentials_written": 0,
        "migrations": 0,
        "supabase_writes": 0,
    }
