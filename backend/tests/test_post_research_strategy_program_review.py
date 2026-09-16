from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from app.research.strategy import post_research_strategy_program_review as review
from app.research.strategy.family_a_momentum import file_sha256
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = review.output_root(ROOT)
SUMMARY = json.loads(
    (ROOT / "data/reports/program_review_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        ARTIFACT_ROOT
        / "manifests/post_research_strategy_program_review_manifest_v1.json"
    ).read_text(encoding="utf-8")
)


def _json(relative: str) -> dict:
    return json.loads((ARTIFACT_ROOT / relative).read_text(encoding="utf-8"))


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_profile_manifest_and_family_a_closure_hash_are_exact() -> None:
    assert review.COMMAND_VERSION == "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_V1"
    assert review.COMMAND_PROFILE == "INTERSIGNAL_NEXT_CYCLE_DECISION_V1"
    assert MANIFEST["manifest_version"] == (
        "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_MANIFEST_V1"
    )
    assert MANIFEST["family_a_post_validation_closure_hash"] == (
        "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"
    )
    assert _hash_without(MANIFEST, "post_research_program_review_hash") == MANIFEST[
        "post_research_program_review_hash"
    ]
    assert MANIFEST["post_research_program_review_hash"] == (
        "a152b0e489005ecb506887082c99bee35a8e3c77e199f4c0ada2d7e0089a18cc"
    )


def test_a_to_g_final_status_and_all_current_evidence_inputs_are_present() -> None:
    assert MANIFEST["a_to_g_final_status"] == "COMPLETE_NO_VALIDATED_STRATEGY"
    assert set(MANIFEST["current_evidence_inputs"]) == {
        "FAMILY_A_STRONG_DEVELOPMENT_LATER_UNSUPPORTIVE",
        "FAMILY_C_REUSABLE_COMPRESSION_SIGNAL",
        "FAMILY_D_DATA_BLOCK",
        "FAMILY_F_SOURCE_BLOCK",
        "FAMILY_G_NEGATIVE_REGIME_OVERLAY",
        "CAP4_VALIDATION_FAILURE",
        "CA_VALIDATION_INTEGRITY_LESSONS",
        "KNOWN_HOLDOUT_CONTAMINATION",
    }


def test_four_exact_options_are_assessed_without_weighted_score() -> None:
    options = _json("options/program_options_v1.json")
    assert tuple(row["option_id"] for row in options["options"]) == review.OPTION_IDS
    assert options["rating_scale"] == ["HIGH", "MEDIUM", "LOW"]
    assert options["arbitrary_weighted_score_used"] is False
    required_dimensions = {
        "expected_research_value",
        "scientific_cleanliness",
        "time_to_next_decision",
        "engineering_effort",
        "data_licensing_dependency",
        "cost",
        "reuse_across_intersignal",
        "risk_of_overfitting",
        "strategic_optionality",
        "product_value_without_strategy",
    }
    assert all(required_dimensions <= set(row) for row in options["options"])
    assert all(
        row[key] in {"HIGH", "MEDIUM", "LOW"}
        for row in options["options"]
        for key in required_dimensions
    )


def test_exactly_one_primary_and_one_secondary_direction_are_selected() -> None:
    options = _json("options/program_options_v1.json")["options"]
    decision = _json("decision/program_decision_v1.json")
    assert sum(row["decision"] == "PRIMARY" for row in options) == 1
    assert sum(row["decision"] == "SECONDARY" for row in options) == 1
    assert decision["NEXT_PROGRAM_PRIMARY_DIRECTION"] == "PRODUCT_PLATFORM_PROGRAM"
    assert decision["NEXT_PROGRAM_SECONDARY_DIRECTION"] == "FORWARD_DATA_PROGRAM"
    assert decision["another_strategy_family_currently_justified"] == "NO"
    assert decision["selected_program_started"] is False


def test_program_status_strategy_v2_and_family_h_are_frozen() -> None:
    governance = _json("governance/program_state_v1.json")
    assert governance["STRATEGY_RESEARCH_PROGRAM_STATUS"] == "PRODUCT_PLATFORM_FOCUS"
    assert governance["STRATEGY_DISCOVERY_MODE"] == "PAUSED"
    assert governance["STRATEGY_V2_STATUS"] == "NOT_CREATED"
    assert governance["FAMILY_H_STATUS"] == "NOT_PLANNED"
    assert governance["new_strategy_created"] is False
    assert governance["validation_run_performed"] is False
    assert governance["paper_trading_started"] is False
    assert governance["live_trading_started"] is False
    assert governance["selected_program_started"] is False


def test_forward_observation_is_distinct_from_paper_trading_readiness() -> None:
    policy = _json("governance/forward_observation_policy_v1.json")
    assert policy["paper_observation_mode"] == "RESEARCH_SHADOW_MODE"
    assert policy["paper_trading_readiness"] == "NO_VALIDATED_CANDIDATE"
    assert policy["deployment_rehearsal"] is False
    assert policy["FAMILY_A_FORWARD_USE_STATUS"] == "FROZEN_RESEARCH_BENCHMARK"
    assert policy["family_a_live_candidate"] is False
    assert policy["FAMILY_C_FORWARD_USE_STATUS"] == (
        "SIGNAL_LEVEL_RESEARCH_OBSERVATION_ONLY"
    )
    assert policy["family_c_strategy_created"] is False
    assert policy["performance_thresholds_defined"] is False
    assert policy["forward_observation_started"] is False


def test_family_d_and_f_infrastructure_reuse_is_assessed_without_acquisition() -> None:
    assessment = _json("governance/data_infrastructure_assessment_v1.json")
    assert assessment["FAMILY_D_INFRASTRUCTURE_PRIORITY"] == (
        "TARGETED_FEASIBILITY_SECONDARY"
    )
    assert set(assessment["family_d_reuse"]) == {
        "INTRADAY_EXECUTION_RESEARCH",
        "MARKET_MICROSTRUCTURE",
        "ENTRY_TIMING",
        "FUTURE_STRATEGY_FAMILIES",
        "EXECUTION_QUALITY_ANALYTICS",
    }
    assert assessment["FAMILY_F_INFRASTRUCTURE_PRIORITY"] == (
        "TARGETED_FEASIBILITY_SECONDARY"
    )
    assert "PORTFOLIO_ALERTS" in assessment["family_f_reuse"]
    assert "EVENT_RISK" in assessment["family_f_reuse"]
    assert assessment["data_acquisition_started"] is False
    assert assessment["provider_selected"] is False


def test_three_and_six_month_plans_are_decision_level_only() -> None:
    roadmap = _json("roadmap/program_roadmap_v1.json")
    assert [row["month"] for row in roadmap["three_month_plan"]] == [1, 2, 3]
    assert all(row["implementation_started"] is False for row in roadmap["three_month_plan"])
    assert len(roadmap["six_month_plan"]) == 3
    assert roadmap["six_month_plan"][-1]["decision_point"] == (
        "CHOOSE_CONTINUE_PLATFORM_VALIDATE_FORWARD_EVIDENCE_CHANGE_PROGRAM_OR_PAUSE_ALPHA_RESEARCH"
    )
    assert roadmap["programme_started"] is False


def test_resources_success_criteria_and_stop_conditions_are_program_level() -> None:
    plan = _json("resource_plan/resource_plan_v1.json")
    assert {row["resource"]: row["level"] for row in plan["resources"]} == {
        "ENGINEERING_EFFORT": "HIGH",
        "DATA_EFFORT": "MEDIUM",
        "LICENSING_DATA_COST": "LOW",
        "COMPUTE_STORAGE_IMPACT": "MEDIUM",
        "MANUAL_REVIEW_EFFORT": "MEDIUM",
    }
    assert len(plan["success_criteria"]) == 6
    assert len(plan["stop_conditions"]) == 6
    assert plan["financial_return_target_defined"] is False


def test_product_roadmap_maps_all_six_modules_without_execution() -> None:
    mapping = _json("roadmap/program_roadmap_v1.json")["product_mapping"]
    assert {row["module"] for row in mapping} == {
        "Trade",
        "Invest",
        "Research",
        "Portfolio OS",
        "Broker Connection",
        "Data Layer",
    }
    interactions = {row["module"]: row["interaction"] for row in mapping}
    assert interactions["Trade"] == "DEFERRED"
    assert interactions["Broker Connection"] == "DESIGN_ONLY"
    assert interactions["Research"] == "PRIMARY"
    assert interactions["Portfolio OS"] == "PRIMARY"


def test_review_has_no_strategy_validation_or_performance_execution_path() -> None:
    tree = ast.parse(inspect.getsource(review))
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
    assert MANIFEST["new_strategy_created"] is False
    assert MANIFEST["validation_run_performed"] is False
    assert MANIFEST["data_acquisition_started"] is False
    assert MANIFEST["infrastructure_implementation_started"] is False


def test_protected_research_artifacts_are_byte_identical() -> None:
    proof = MANIFEST["proof_protected_artifacts_unchanged"]
    assert proof["unchanged"] is True
    assert proof["file_hashes_before"] == proof["file_hashes_after"]
    assert {
        relative: file_sha256(ROOT / relative)
        for relative in proof["file_hashes_after"]
    } == proof["file_hashes_after"]


def test_storage_reports_documentation_roadmap_and_security_are_complete() -> None:
    assert all(
        (ARTIFACT_ROOT / name).is_dir()
        for name in (
            "options",
            "decision",
            "roadmap",
            "resource_plan",
            "governance",
            "manifests",
        )
    )
    assert all((ROOT / "data/reports" / name).is_file() for name in review.REPORT_NAMES)
    assert (ROOT / "docs/post-research-strategy-program-review-v1.md").is_file()
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
