from __future__ import annotations

import json
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_d_data_blocked_closure import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTROL_D_000_STATUS,
    EXPECTED_COMMAND_02_HASHES,
    EXPECTED_COMMAND_02_MANIFEST_HASH,
    EXPECTED_COMMAND_03_HASHES,
    EXPECTED_COMMAND_03_MANIFEST_HASH,
    EXPECTED_FAMILY_D_HASHES,
    FAMILY_D_CONTINUITY_STANDARD,
    FAMILY_D_EVIDENCE_STATUS,
    FAMILY_D_RESEARCH_STATUS,
    FAMILY_D_STRATEGY_V2_STATUS,
    FAMILY_D_VALIDATION_STATUS,
    NEXT_PLANNED_RESEARCH_FAMILY,
    ORB_D_001_STATUS,
    REPORT_NAMES,
    verify_family_d_closure_inputs,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = REPO_ROOT / "data/research/strategy_families/family_d/v1/closure"
SUMMARY_PATH = REPO_ROOT / "data/reports/family_d_closure_v1_summary.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_command_identity_and_all_frozen_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_D_DATA_BLOCKED_CLOSURE_V1"
    assert COMMAND_PROFILE == "OPENING_RANGE_DATA_BLOCKED_RESEARCH_FREEZE_V1"
    assert EXPECTED_FAMILY_D_HASHES == {
        "family_d_config_hash": "87ab7e4b328d7e1c433f99b6997b5b8f9cb9d0439893608f0ac5b7ca247b601a",
        "intraday_scope_hash": "a32faa36a1500d804a5d680ca9cba37a8e822262823cab8e5e2eefe70673d8f3",
        "control_reference_hash": "fb2da529f1936a870fe4eada3c0db3bf5173ba6429e1495792edc92d57ee9cf4",
        "d001_parameter_hash": "d570a5c165b1c10100f329f8bb08d619e84dad97b893484800978f021fc14d5c",
        "d001_preregistration_hash": "1730b3c764aa9d54b8b9719dcecfa3c3763b4b60f49f67819dc6b4a94be2e1d4",
        "family_d_success_criteria_hash": "0b6002f830bd16a6259719ce5ff242c670364ba68cccd4f34e8958e45f3798cb",
    }
    verification = verify_family_d_closure_inputs(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert all(verification["checks"].values())


def test_command_02_hashes_and_manifest_are_frozen() -> None:
    assert EXPECTED_COMMAND_02_HASHES == {
        "continuity_remediation_config_hash": "248a20322ebcb69835fb89727884839f0280f4115657f3aeaf8444382b33ca43",
        "continuity_request_plan_hash": "7efe442118d97708c44db200797771fb754ef31118b1042e6e29113ec66a8422",
        "continuity_raw_extension_hash": "c9f2bf6d44e1c3454c35683e0acf4c814cdae8db6267678b1e8963a865770a30",
        "continuity_normalized_extension_hash": "115572a1291e2e162c9bda8c782f31a8077713aa599766b4d6b7316c3e558b15",
        "continuity_matrix_hash": "b202180a2be523cec8c49c4c872ea87f79905a0effdedeb42a174b79c463ce8d",
        "family_d_activity_readiness_hash": "2200fb3d5dbcb260b6649eb1d014af90f92455a1acd2643d12b0ea86450aba95",
    }
    assert EXPECTED_COMMAND_02_MANIFEST_HASH == (
        "5b3f403823bec3ad4295603a6db6d382f540ba9d636e69989efd19322ad0247c"
    )


def test_command_03_hashes_and_manifest_are_frozen() -> None:
    assert EXPECTED_COMMAND_03_HASHES == {
        "exact_gap_population_hash": "504a0e88f6e4f5399a906d84c562010dbcebc333d4503e04821cc0f646eed2d5",
        "exact_gap_request_plan_hash": "e31bcdb8fff37f2b20b07897757278b3f8840157768b991e23da2b695dfa8d82",
        "exact_gap_raw_hash": "b5d61c5fa3d88951dc117b829351ca515859de05f83d5f5515824ffdc8510e69",
        "exact_gap_normalized_hash": "8a0068a464a3822fdf63b08d227c2667024d0d5ba1de7cd6600b3b6b761002b2",
        "recovered_continuity_matrix_hash": "e5c5f16e27725950a94dcb8ff49e9003fd9cf492d22ba5c5eb1e43f244e65438",
        "family_d_post_recovery_readiness_hash": "2e3350ad99acd6cc63b11da7029fdf337cda44e37457d2ffd86fe70128ab95ee",
    }
    assert EXPECTED_COMMAND_03_MANIFEST_HASH == (
        "17d6205cb3ff0ab2816573a0697739c43635ed73362ed761d271c2516cb7f082"
    )
    assert all(
        verify_family_d_closure_inputs(REPO_ROOT)["command_03_hash_checks"].values()
    )


def test_exact_coverage_and_remaining_gap_counts_are_frozen() -> None:
    summary = _summary()
    assert summary["data_finding"] == {
        "target_sessions": 4821,
        "complete_exact_prior20_continuity": 3752,
        "incomplete": 1069,
        "coverage_pct": "77.826177",
        "coverage_classification": "INSUFFICIENT",
    }
    assert summary["remaining_defect_population"] == {
        "total": 217,
        "counts": {
            "MISSING_OPENING_BARS": 105,
            "GROWW_CONFIRMED_UNAVAILABLE": 48,
            "STRICT_QUALITY_FAILURE": 64,
        },
    }


def test_exact_retry_and_provider_findings_are_frozen() -> None:
    findings = _summary()["provider_findings"]
    assert findings["provider"] == "GROWW"
    assert findings["exact_retry_requests"] == 211
    assert findings["first_attempt_request_successes"] == 211
    assert findings["new_sessions_recovered"] == 0
    assert findings["unexplained_provider_differences"] == 0
    assert findings["remaining_population_persistent_under_approved_source"] is True
    assert findings["approved_alternate_source"] == "NONE"
    assert findings["alternate_provider_contacted"] is False
    assert findings["new_provider_authorized"] is False


def test_final_research_control_and_d001_statuses_are_not_evaluated() -> None:
    statuses = _summary()["final_statuses"]
    assert statuses["FAMILY_D_RESEARCH_STATUS"] == FAMILY_D_RESEARCH_STATUS
    assert statuses["FAMILY_D_EVIDENCE_STATUS"] == FAMILY_D_EVIDENCE_STATUS
    assert statuses["CONTROL_D_000_STATUS"] == CONTROL_D_000_STATUS
    assert statuses["ORB_D_001_STATUS"] == ORB_D_001_STATUS
    assert statuses["FAMILY_D_VALIDATION_STATUS"] == FAMILY_D_VALIDATION_STATUS
    assert statuses["FAMILY_D_STRATEGY_V2_STATUS"] == FAMILY_D_STRATEGY_V2_STATUS
    assert statuses["FAMILY_D_CONTINUITY_STANDARD"] == FAMILY_D_CONTINUITY_STANDARD


def test_pause_is_data_blocked_and_not_a_strategy_rejection() -> None:
    interpretation = _summary()["interpretation"]
    assert interpretation["strategy_rejected_for_failure"] is False
    assert interpretation[
        "paused_because_approved_data_cannot_meet_frozen_continuity_standard"
    ] is True
    assert interpretation["performance_conclusion_allowed"] is False


def test_continuity_standard_is_preserved_without_relaxations() -> None:
    standard = _summary()["continuity_standard"]
    assert standard["status"] == "PRESERVED_NOT_RELAXED"
    assert standard["readiness_target_pct"] == 95
    for field in (
        "sparse_prior_observations_allowed",
        "older_session_substitution_allowed",
        "daily_volume_substitution_allowed",
        "post_hoc_problematic_session_removal_allowed",
        "readiness_target_reduction_allowed",
    ):
        assert standard[field] is False


def test_resume_requirements_and_preregistration_rules_are_complete() -> None:
    resume = _json(CLOSURE_ROOT / "handoff/family_d_resume_requirement_v1.json")
    assert resume["version"] == "FAMILY_D_RESUME_REQUIREMENT_V1"
    assert resume["all_conditions_required"] is True
    assert set(resume["conditions"]) == {"A", "B", "C", "D", "E"}
    assert "GTE_95_PERCENT" in resume["conditions"]["D"]
    assert resume["data_only_resume"]["existing_preregistration_may_remain_valid"] is True
    assert resume["data_only_resume"]["required_versioning"] == (
        "NEW_DATA_SOURCE_OR_REMEDIATION_VERSION_NOT_NEW_STRATEGY_VERSION"
    )
    assert set(resume["new_strategy_preregistration_required_if_changed"]) == {
        "OPENING_RANGE",
        "ACTIVITY_DEFINITION",
        "THRESHOLD",
        "ENTRY",
        "STOP",
        "EXIT",
        "RISK",
        "CAPACITY",
        "UNIVERSE",
        "RANKING",
        "SUCCESS_CRITERIA",
    }


def test_data_and_provider_lessons_are_scope_correct() -> None:
    data = _json(CLOSURE_ROOT / "data_lessons/family_d_data_lesson_v1.json")
    provider = _json(CLOSURE_ROOT / "data_lessons/family_d_provider_lesson_v1.json")
    assert "Sparse event-oriented intraday ingestion" in data["lesson"]
    assert "continuous rolling intraday-session history" in data["lesson"]
    assert "before ingestion scope is frozen" in data["future_planning_requirement"]
    assert "reliable for available data" in provider["lesson"]
    assert "persistent gaps" in provider["lesson"]
    assert provider["interpretation_prohibited"] == (
        "DO_NOT_INTERPRET_AS_GENERAL_PROVIDER_UNRELIABILITY"
    )


def test_closure_manifest_and_hash_are_canonical() -> None:
    manifest = _json(CLOSURE_ROOT / "manifest/family_d_closure_manifest_v1.json")
    body = {
        key: value for key, value in manifest.items() if key != "family_d_closure_hash"
    }
    assert canonical_hash(body) == manifest["family_d_closure_hash"]
    assert manifest["family_d_hashes"] == EXPECTED_FAMILY_D_HASHES
    assert manifest["command_02_hashes"] == EXPECTED_COMMAND_02_HASHES
    assert manifest["command_02_manifest_hash"] == EXPECTED_COMMAND_02_MANIFEST_HASH
    assert manifest["command_03_hashes"] == EXPECTED_COMMAND_03_HASHES
    assert manifest["command_03_manifest_hash"] == EXPECTED_COMMAND_03_MANIFEST_HASH
    assert manifest["closure_timestamp"].endswith("Z")


def test_closure_artifact_manifest_recomputes_and_files_match() -> None:
    manifest = _json(
        CLOSURE_ROOT / "manifest/family_d_closure_artifact_manifest_v1.json"
    )
    body = {key: value for key, value in manifest.items() if key != "artifact_manifest_hash"}
    assert canonical_hash(body) == manifest["artifact_manifest_hash"]
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_roadmap_update_and_family_e_planning_note_only() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert f"| Family D | Opening Range / Stocks-in-Play | {FAMILY_D_RESEARCH_STATUS} |" in roadmap
    assert "| Family E | Pullback / Reclaim | NEXT_PLANNED |" in roadmap
    assert "| Family F | Catalyst Momentum | PLANNED_NOT_STARTED |" in roadmap
    assert "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |" in roadmap

    note = _json(CLOSURE_ROOT / "handoff/family_e_planning_note_v1.json")
    assert note["NEXT_PLANNED_RESEARCH_FAMILY"] == NEXT_PLANNED_RESEARCH_FAMILY
    assert note["status"] == "NEXT_PLANNED"
    assert note["high_level_idea"] == [
        "STRONG_PRIOR_TREND",
        "CONTROLLED_PULLBACK",
        "RECLAIM_OR_CONTINUATION",
    ]
    assert note["parameters_defined"] is False
    assert note["implementation_started"] is False
    assert note["performance_run"] is False


def test_no_performance_validation_strategy_v2_or_external_effects() -> None:
    governance = _summary()["governance"]
    assert governance["performance_run"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["family_e_implementation_started"] is False
    assert governance["new_provider_configured"] is False
    assert governance["new_provider_contacted"] is False
    for field in (
        "live_signals",
        "live_orders",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "secrets_written",
    ):
        assert governance[field] == 0
    source = (
        REPO_ROOT / "backend/app/research/strategy/family_d_data_blocked_closure.py"
    ).read_text(encoding="utf-8")
    assert "simulate_strategy(" not in source
    assert "run_family_d_exact_gap_recovery(" not in source
    assert "retrieve_exact_gaps(" not in source


def test_prior_command_artifacts_are_immutable_and_reverified() -> None:
    summary = _summary()
    verification = verify_family_d_closure_inputs(REPO_ROOT)
    assert summary["immutability"]["prior_artifacts_unchanged"] is True
    assert summary["immutability"]["command_02_artifact_count"] == 1086
    assert summary["immutability"]["command_03_artifact_count"] == 348
    assert summary["immutability"]["snapshot_hash"] == (
        verification["prior_artifact_snapshot"]["snapshot_hash"]
    )


def test_reports_and_documentation_exist() -> None:
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    assert (REPO_ROOT / "docs/strategy-family-d-data-blocked-closure-v1.md").is_file()
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[1])) == 1
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[2])) == 1
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[3])) == 4
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[4])) == 2


def test_closure_is_ready_for_review() -> None:
    summary = _summary()
    assert summary["ready_for_review"] is True
    assert summary["recommended_next_action"].startswith("PLAN_FAMILY_E_ONLY")
