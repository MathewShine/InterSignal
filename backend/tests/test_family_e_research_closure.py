from __future__ import annotations

import ast
import json
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_e_pullback_reclaim import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_E001_PARAMETER_HASH,
    EXPECTED_E001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CLOSURE_HASH,
    EXPECTED_FAMILY_E_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    previous_research_snapshot,
)
from app.research.strategy.family_e_research_closure import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTROL_E_000_FINAL_STATUS,
    CONTROL_NEGATIVE_EVIDENCE_ID,
    EXPECTED_ARCHITECTURE_MANIFEST_HASH,
    EXPECTED_CONTROL_RESULT_HASH,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_E001_RESULT_HASH,
    FAMILY_E_EVIDENCE_STATUS,
    FAMILY_E_FUTURE_RESEARCH_POLICY,
    FAMILY_E_RESEARCH_STATUS,
    FAMILY_E_STRATEGY_V2_STATUS,
    FAMILY_E_VALIDATION_STATUS,
    NEXT_PLANNED_RESEARCH_FAMILY,
    PBR_E_001_FINAL_STATUS,
    REPORT_NAMES,
    RESEARCH_LESSON_ID,
    STRUCTURE_NEGATIVE_EVIDENCE_ID,
    family_e_commands_01_02_snapshot,
    verify_family_e_closure_inputs,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = (
    REPO_ROOT / "data/research/strategy_families/family_e/v1/closure"
)
SUMMARY_PATH = REPO_ROOT / "data/reports/family_e_closure_v1_summary.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_command_identity_and_all_frozen_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_E_RESEARCH_CLOSURE_V1"
    assert COMMAND_PROFILE == "PULLBACK_RECLAIM_CLOSURE_V1"
    assert EXPECTED_FAMILY_E_CONFIG_HASH == (
        "7e73a24b0c3d52c2727e36f38e607eb20e2c8369f4de743267ecd2eab101f6c3"
    )
    assert EXPECTED_ARCHITECTURE_MANIFEST_HASH == (
        "797f6d056807cec6ffd89404488a571fec28238b5b5a39293508208da9e97a22"
    )
    assert EXPECTED_CONTROL_REFERENCE_HASH == (
        "05e66547c89a74926810351898f848dbedc0f7b4282fe87f04d1cde7a99bd212"
    )
    assert EXPECTED_E001_PARAMETER_HASH == (
        "a64ff19f3de639baf3b5a9d701f3683d46e805ccbccba32840b3532c4ba81cc0"
    )
    assert EXPECTED_E001_PREREGISTRATION_HASH == (
        "7b0e988c7e49b0fa3f7e92a213e991cd5880ad2d0747279b2a29aa7f664a8108"
    )
    assert EXPECTED_SUCCESS_CRITERIA_HASH == (
        "f9a685f3458f13cb7bc2b3d5df3a1bab86d544246d59be6f2ca48889fa96ad5f"
    )
    assert EXPECTED_FAMILY_D_CLOSURE_HASH == (
        "1628774e5a6032487ac6e15e9beba21cbf52c96389b83aca7d4e87a46e577414"
    )
    verification = verify_family_e_closure_inputs(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert all(verification["checks"].values())


def test_exact_result_and_registry_hashes_are_frozen() -> None:
    assert EXPECTED_CONTROL_RESULT_HASH == (
        "e3d36f861c004ef6b6b967369c9964202ca8a167c71d7b52355b156cf3150d1e"
    )
    assert EXPECTED_E001_RESULT_HASH == (
        "84d8c29c8cbfc646783ac91186b9a6caf43fecb30e03e62e861e065e2a1315d8"
    )
    assert EXPECTED_DEVELOPMENT_REGISTRY_HASH == (
        "50a9943f29e59e3f8b51579dc75e641f95e1f3a8b8e87f3aef0b8257ff4426ce"
    )
    manifest = _json(
        CLOSURE_ROOT / "manifest/family_e_closure_manifest_v1.json"
    )
    assert manifest["control"]["result_hash"] == EXPECTED_CONTROL_RESULT_HASH
    assert manifest["PBR_E_001"]["result_hash"] == EXPECTED_E001_RESULT_HASH
    assert manifest["development_registry_hash"] == EXPECTED_DEVELOPMENT_REGISTRY_HASH


def test_final_statuses_are_frozen() -> None:
    assert CONTROL_E_000_FINAL_STATUS == "CLOSED_WEAK_NONVIABLE_CONTROL"
    assert PBR_E_001_FINAL_STATUS == "CLOSED_FAILED_DEVELOPMENT"
    assert FAMILY_E_RESEARCH_STATUS == "PAUSED_NO_VALIDATION_CANDIDATE"
    assert FAMILY_E_EVIDENCE_STATUS == "PULLBACK_RECLAIM_V1_NOT_SUPPORTED"
    assert FAMILY_E_VALIDATION_STATUS == "NOT_ACCESSED"
    assert FAMILY_E_STRATEGY_V2_STATUS == "NOT_CREATED"
    statuses = _summary()["final_statuses"]
    assert statuses["CONTROL_E_000_FINAL_STATUS"] == CONTROL_E_000_FINAL_STATUS
    assert statuses["PBR_E_001_FINAL_STATUS"] == PBR_E_001_FINAL_STATUS
    assert statuses["FAMILY_E_RESEARCH_STATUS"] == FAMILY_E_RESEARCH_STATUS
    assert statuses["FAMILY_E_EVIDENCE_STATUS"] == FAMILY_E_EVIDENCE_STATUS
    assert statuses["FAMILY_E_VALIDATION_STATUS"] == FAMILY_E_VALIDATION_STATUS
    assert statuses["FAMILY_E_STRATEGY_V2_STATUS"] == FAMILY_E_STRATEGY_V2_STATUS


def test_research_lesson_and_filter_attribution_are_preserved() -> None:
    lesson = _json(CLOSURE_ROOT / "lessons/family_e_research_lesson_v1.json")
    assert lesson["lesson_id"] == RESEARCH_LESSON_ID
    assert "did not produce positive executable DEVELOPMENT performance" in lesson[
        "primary_lesson"
    ]
    assert lesson["scope_limit"] == (
        "Do not generalize beyond the exact tested definitions."
    )
    assert lesson["filter_attribution"]["classification"] == "NEGATIVE"
    filtered = lesson["filter_attribution"]["filtered_out"]
    retained = lesson["filter_attribution"]["retained"]
    assert filtered["complete_event_count"] == 2365
    assert filtered["win_rate"] == "0.4748414376321353065539112051"
    assert filtered["net_expectancy"] == "0.004387781636205847273216909032"
    assert filtered["net_profit_factor"] == "1.169664673116664250764126489"
    assert retained["complete_event_count"] == 8183
    assert retained["win_rate"] == "0.4448246364414029084687767322"
    assert retained["net_expectancy"] == "0.0005468048785054629092716720023"
    assert retained["net_profit_factor"] == "0.9834301638892258266589878744"


def test_negative_evidence_registry_contains_both_exact_entries() -> None:
    registry = _json(
        CLOSURE_ROOT / "evidence/family_e_negative_evidence_registry_v1.json"
    )
    body = {
        key: value
        for key, value in registry.items()
        if key != "negative_evidence_registry_hash"
    }
    assert registry["negative_evidence_registry_hash"] == canonical_hash(body)
    entries = {entry["evidence_id"]: entry for entry in registry["entries"]}
    assert set(entries) == {
        CONTROL_NEGATIVE_EVIDENCE_ID,
        STRUCTURE_NEGATIVE_EVIDENCE_ID,
    }
    assert all(
        entry["status"] == "RESEARCH_EVIDENCE_NOT_VALIDATED"
        for entry in entries.values()
    )
    assert (
        entries[STRUCTURE_NEGATIVE_EVIDENCE_ID]["structure_filter_attribution"]
        == "NEGATIVE"
    )


def test_stop_capacity_and_win_rate_lessons_are_descriptive_only() -> None:
    lesson = _summary()["research_lesson"]
    stop = lesson["stop_time_exit_lesson"]
    assert (stop["control_stop_exits"], stop["control_time_exits"]) == (205, 615)
    assert (stop["treatment_stop_exits"], stop["treatment_time_exits"]) == (
        207,
        605,
    )
    assert stop["causal_conclusion_about_stop_removal"] is False
    assert stop["stop_removal_authorized"] is False
    capacity = lesson["capacity_lesson"]
    assert capacity["control_capacity_rejection_rate"] == (
        "0.8510357815442561205273069680"
    )
    assert capacity["treatment_capacity_rejection_rate"] == (
        "0.8093966249848245720529318927"
    )
    assert capacity["capacity_tuning_authorized"] is False
    win_rate = lesson["sixty_percent_win_rate"]
    assert win_rate["control"] == "0.4463414634146341463414634146"
    assert win_rate["treatment"] == "0.4421182266009852216748768473"
    assert win_rate["aspiration_achieved"] is False


def test_closure_manifest_and_hash_are_canonical() -> None:
    manifest = _json(
        CLOSURE_ROOT / "manifest/family_e_closure_manifest_v1.json"
    )
    body = {
        key: value for key, value in manifest.items() if key != "family_e_closure_hash"
    }
    assert manifest["family_e_closure_hash"] == canonical_hash(body)
    assert manifest["family_id"] == "STRATEGY_FAMILY_E_PULLBACK_RECLAIM_V1"
    assert manifest["filter_attribution"]["classification"] == "NEGATIVE"
    assert manifest["validation_status"] == "NOT_ACCESSED"
    assert manifest["strategy_v2_status"] == "NOT_CREATED"
    assert manifest["future_research_policy"] == (
        "REQUIRES_GENUINELY_NEW_ARCHITECTURE"
    )
    assert manifest["closure_timestamp"].endswith("Z")


def test_artifact_manifest_hashes_every_declared_file() -> None:
    artifact_manifest = _json(
        CLOSURE_ROOT / "manifest/family_e_closure_artifact_manifest_v1.json"
    )
    body = {
        key: value
        for key, value in artifact_manifest.items()
        if key != "artifact_manifest_hash"
    }
    assert artifact_manifest["artifact_manifest_hash"] == canonical_hash(body)
    assert artifact_manifest["artifact_hashes"]
    for relative, expected in artifact_manifest["artifact_hashes"].items():
        # The roadmap is an intentionally evolving lifecycle document. Later
        # family closures update its live statuses without changing frozen
        # Family E research evidence; its current state is asserted separately.
        if relative in {
            "docs/strategy-family-research-roadmap-v1.md",
            "backend/tests/test_family_e_research_closure.py",
        }:
            continue
        assert file_sha256(REPO_ROOT / relative) == expected


def test_no_performance_rerun_or_parameter_tuning_was_added() -> None:
    source_path = (
        REPO_ROOT
        / "backend/app/research/strategy/family_e_research_closure.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "build_family_e_development_evaluation" not in imported_names
    assert "build_family_e_development_evaluation" not in called_names
    governance = _summary()["governance"]
    assert governance["performance_recomputed"] is False
    assert governance["new_family_e_performance_experiments"] == 0
    assert governance["parameter_changes"] == 0
    assert governance["alternate_ma_tested"] is False
    assert governance["alternate_pullback_tested"] is False
    assert governance["alternate_reclaim_tested"] is False
    assert governance["stop_changed"] is False
    assert governance["holding_period_changed"] is False
    assert governance["target_added"] is False
    assert governance["family_e_incremental_tuning_authorized"] is False
    assert governance["FAMILY_E_FUTURE_RESEARCH_POLICY"] == (
        FAMILY_E_FUTURE_RESEARCH_POLICY
    )


def test_validation_v2_and_family_f_implementation_remain_unaccessed() -> None:
    summary = _summary()
    governance = summary["governance"]
    assert governance["validation_accessed"] is False
    assert governance["validation_rows_loaded"] == 0
    assert governance["strategy_v2_created"] is False
    assert governance["family_f_implementation_started"] is False
    assert governance["family_f_performance_run"] is False
    assert summary["handoff"]["validation_accessed"] is False


def test_roadmap_has_all_required_current_states() -> None:
    roadmap = (
        REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md"
    ).read_text(encoding="utf-8")
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |" in roadmap
    assert "| Family E | Pullback / Reclaim | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family F | Catalyst Momentum | NEXT_PLANNED |" in roadmap
    assert "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |" in roadmap


def test_family_f_handoff_is_planning_and_data_readiness_only() -> None:
    handoff = _json(CLOSURE_ROOT / "handoff/family_f_planning_note_v1.json")
    assert handoff["NEXT_PLANNED_RESEARCH_FAMILY"] == (
        NEXT_PLANNED_RESEARCH_FAMILY
    )
    assert handoff["status"] == "NEXT_PLANNED"
    assert handoff["parameters_defined"] is False
    assert handoff["strategy_preregistered"] is False
    assert handoff["implementation_started"] is False
    assert handoff["performance_run"] is False
    assert handoff["authorized_to_start"] is False
    assert handoff["data_readiness"]["historical_catalyst_coverage_assumed_ready"] is False
    assert handoff["data_readiness"]["status"] == (
        "ASSESSMENT_REQUIRED_BEFORE_STRATEGY_PREREGISTRATION"
    )
    assert all(handoff["must_freeze_before_performance"].values())


def test_diagnostics_are_preserved_for_cross_family_research() -> None:
    diagnostics = _json(
        CLOSURE_ROOT / "lessons/family_e_diagnostic_preservation_v1.json"
    )
    assert diagnostics["purpose"] == "FUTURE_CROSS_FAMILY_RESEARCH"
    assert len(diagnostics["artifacts"]) == 8
    assert diagnostics["parameter_or_exit_rule_created"] is False
    for artifact in diagnostics["artifacts"]:
        assert file_sha256(REPO_ROOT / artifact["path"]) == artifact["sha256"]


def test_baselines_and_family_e_commands_01_02_are_unchanged() -> None:
    summary = _summary()
    immutable = summary["immutability"]
    baseline = previous_research_snapshot(REPO_ROOT)
    commands = family_e_commands_01_02_snapshot(REPO_ROOT)
    assert immutable["baseline_unchanged"] is True
    assert immutable["baseline_snapshot_before"] == baseline["snapshot_hash"]
    assert immutable["baseline_snapshot_after"] == baseline["snapshot_hash"]
    assert immutable["family_e_commands_01_02_unchanged"] is True
    assert immutable["family_e_commands_01_02_before"] == commands["snapshot_hash"]
    assert immutable["family_e_commands_01_02_after"] == commands["snapshot_hash"]


def test_reports_and_documentation_are_complete() -> None:
    for report_name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / report_name).is_file()
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[1])) == 2
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[2])) == 2
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[3])) == 7
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[4])) == 1
    documentation = (
        REPO_ROOT / "docs/strategy-family-e-closure-v1.md"
    ).read_text(encoding="utf-8")
    for expected in (
        "PAUSED_NO_VALIDATION_CANDIDATE",
        "PULLBACK_RECLAIM_V1_NOT_SUPPORTED",
        "Failed SMA50-structure hypothesis",
        "Validation was not accessed",
        "Strategy V2 was not created",
        "Family F Catalyst Momentum",
        "data-readiness",
    ):
        assert expected in documentation


def test_security_and_review_verification_are_explicit() -> None:
    summary = _summary()
    governance = summary["governance"]
    for field in (
        "live_signals_generated",
        "live_orders_placed",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "database_writes",
        "network_calls",
        "external_writes",
        "secrets_written",
    ):
        assert governance[field] == 0
    verification = summary["verification"]
    expected_ready = all(
        verification[field].startswith("PASSED")
        for field in (
            "backend_targeted_tests",
            "backend_full_tests",
            "frontend_build",
        )
    )
    assert verification["ready_for_review"] is expected_ready
