from __future__ import annotations

import json
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_c_research_closure import (
    BRK_C_001_FINAL_STATUS,
    BRK_C_002_FINAL_STATUS,
    C001_COMPRESSION_SIGNAL_STATUS,
    C001_FUTURE_RESEARCH_POLICY,
    C1_IMP_001_FINAL_STATUS,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTROL_C_000_FINAL_STATUS,
    EXPECTED_C001_ATTRIBUTION_HASH,
    EXPECTED_C001_RESULT_HASH,
    EXPECTED_C002_RESULT_HASH,
    EXPECTED_C1_IMP_001_RESULT_HASH,
    EXPECTED_CONTROL_RESULT_HASH,
    EXPECTED_FAMILY_C_CLOSURE_HASH,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_C_EVIDENCE_STATUS,
    FAMILY_C_RESEARCH_STATUS,
    FAMILY_C_STRATEGY_V2_STATUS,
    FAMILY_C_VALIDATION_STATUS,
    NEXT_PLANNED_RESEARCH_FAMILY,
    POSITIVE_EVIDENCE_ID,
    RANKING_NEGATIVE_EVIDENCE_ID,
    REPORT_NAMES,
    VOLUME_NEGATIVE_EVIDENCE_ID,
    family_c_baseline_snapshot,
    family_c_commands_01_05_snapshot,
    verify_family_c_closure_inputs,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = (
    REPO_ROOT / "data/research/strategy_families/family_c/v1/closure"
)
SUMMARY_PATH = REPO_ROOT / "data/reports/family_c_closure_v1_summary.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_command_identity_and_all_required_frozen_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_C_RESEARCH_CLOSURE_V1"
    assert COMMAND_PROFILE == "BREAKOUT_CONTINUATION_CLOSURE_V1"
    assert EXPECTED_FAMILY_C_CONFIG_HASH == "5ecb5604939e1230ba176dbb339ebaf15418482da7a68bbbea24370c805961a6"
    assert EXPECTED_SUCCESS_CRITERIA_HASH == "7bb950274ebe47ec7fafeb7e8659e07a457a4ddb169171aa97fe9ff9d0860a77"
    assert EXPECTED_CONTROL_RESULT_HASH == "efdf9ccdf70f4c58d1ce40e2f1e1ccb7e7fa8ad83c5fb3832ce0994d323b991f"
    assert EXPECTED_C001_RESULT_HASH == "8adc1aec00041256748a8fa086b4dae562a6841b844875fc39b3dd19b61680e4"
    assert EXPECTED_C002_RESULT_HASH == "49afe8ee5d766afa9a0e01195fa49041605c71483df0de9ac4c354b469a9a240"
    assert EXPECTED_C001_ATTRIBUTION_HASH == "26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b"
    assert EXPECTED_C1_IMP_001_RESULT_HASH == "013ce88f6b87ee6611065774a898345fd3e7bdf941002025195b844693dc15ee"
    assert EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH == "a56210f2bb06cde7cd867a4549771c113369ea27b958433ef3090c67736ef5e8"
    assert verify_family_c_closure_inputs(REPO_ROOT)["status"] == "VERIFIED"


def test_family_c_final_statuses_are_frozen() -> None:
    statuses = _summary()["final_statuses"]
    assert statuses["FAMILY_C_RESEARCH_STATUS"] == FAMILY_C_RESEARCH_STATUS
    assert statuses["FAMILY_C_EVIDENCE_STATUS"] == FAMILY_C_EVIDENCE_STATUS
    assert statuses["CONTROL_C_000_FINAL_STATUS"] == CONTROL_C_000_FINAL_STATUS
    assert statuses["BRK_C_001_FINAL_STATUS"] == BRK_C_001_FINAL_STATUS
    assert statuses["C001_COMPRESSION_SIGNAL_STATUS"] == C001_COMPRESSION_SIGNAL_STATUS
    assert statuses["C1_IMP_001_FINAL_STATUS"] == C1_IMP_001_FINAL_STATUS
    assert statuses["BRK_C_002_FINAL_STATUS"] == BRK_C_002_FINAL_STATUS
    assert statuses["FAMILY_C_VALIDATION_STATUS"] == FAMILY_C_VALIDATION_STATUS
    assert statuses["FAMILY_C_STRATEGY_V2_STATUS"] == FAMILY_C_STRATEGY_V2_STATUS
    assert statuses["C001_FUTURE_RESEARCH_POLICY"] == C001_FUTURE_RESEARCH_POLICY


def test_positive_compression_evidence_is_preserved_exactly() -> None:
    registry = _json(CLOSURE_ROOT / "evidence/positive_evidence_registry_v1.json")
    entry = registry["entries"][0]
    assert entry["evidence_id"] == POSITIVE_EVIDENCE_ID
    assert entry["status"] == "RESEARCH_EVIDENCE_NOT_VALIDATED"
    assert entry["compression_pass"]["event_count"] == 4247
    assert entry["compression_fail"]["event_count"] == 7961
    assert entry["compression_pass"]["win_rate"] == "0.5142453496585825288438898046"
    assert entry["compression_fail"]["win_rate"] == "0.4803416656198969978645898756"
    assert entry["pass_minus_fail"]["win_rate"] == "0.0339036840386855309792999290"
    assert entry["pass_minus_fail"]["net_expectancy"] == "0.002935644934899161157254801241"
    assert entry["pass_minus_fail"]["net_profit_factor"] == "0.160593522405937677433931612"
    assert entry["pass_minus_fail"]["median_MFE"] == "-0.01172561689486965035058256100"
    assert entry["pass_minus_fail"]["median_MAE"] == "0.01366596117381726075107283910"
    assert entry["temporal_consistency"] == "MOSTLY_CONSISTENT"
    assert canonical_hash(
        {key: value for key, value in registry.items() if key != "positive_evidence_registry_hash"}
    ) == registry["positive_evidence_registry_hash"]


def test_negative_evidence_records_volume_and_failed_ranking() -> None:
    registry = _json(CLOSURE_ROOT / "evidence/negative_evidence_registry_v1.json")
    entries = {entry["evidence_id"]: entry for entry in registry["entries"]}
    assert set(entries) == {
        VOLUME_NEGATIVE_EVIDENCE_ID,
        RANKING_NEGATIVE_EVIDENCE_ID,
    }
    assert entries[VOLUME_NEGATIVE_EVIDENCE_ID]["result"] == "FAILED"
    assert entries[VOLUME_NEGATIVE_EVIDENCE_ID]["net_total_return"] == "-0.1437381646"
    assert entries[VOLUME_NEGATIVE_EVIDENCE_ID]["net_profit_factor"] == "0.9172192606131329318801608309"
    assert entries[RANKING_NEGATIVE_EVIDENCE_ID]["result"] == "FAILED"
    assert entries[RANKING_NEGATIVE_EVIDENCE_ID]["replacement_quality"] == "WORSE"
    assert entries[RANKING_NEGATIVE_EVIDENCE_ID]["quality_dimensions_passed"] == 0
    assert entries[RANKING_NEGATIVE_EVIDENCE_ID]["standard_criteria_passed"] == 5
    assert canonical_hash(
        {key: value for key, value in registry.items() if key != "negative_evidence_registry_hash"}
    ) == registry["negative_evidence_registry_hash"]


def test_research_and_sixty_percent_lessons_are_exact() -> None:
    lesson = _summary()["research_lesson"]
    assert lesson["lesson"] == (
        "A compact pre-breakout range improved 10-session breakout event quality "
        "in DEVELOPMENT, but frequent overlapping signals and portfolio-capacity/"
        "admission mechanics prevented the current implementation from converting "
        "that signal edge into a sufficiently robust executable strategy."
    )
    assert lesson["volume_lesson"] == (
        "Volume expansion at the tested 1.5x definition did not improve the strategy."
    )
    assert lesson["scope_limit"] == "Do not generalize beyond tested definitions."
    win_rate = lesson["sixty_percent_win_rate"]
    assert win_rate["achieved"] is False
    assert win_rate["control"].startswith("0.463924")
    assert win_rate["C001_portfolio"].startswith("0.497435")
    assert win_rate["C001_event_cohort"].startswith("0.514245")
    assert win_rate["C1_IMP_001"].startswith("0.492716")


def test_closure_manifest_and_closure_hash_are_canonical() -> None:
    manifest = _json(CLOSURE_ROOT / "manifest/family_c_closure_manifest_v1.json")
    body = {
        key: value for key, value in manifest.items() if key != "family_c_closure_hash"
    }
    assert canonical_hash(body) == manifest["family_c_closure_hash"]
    assert manifest["family_c_closure_hash"] == EXPECTED_FAMILY_C_CLOSURE_HASH
    assert manifest["family_config_hash"] == EXPECTED_FAMILY_C_CONFIG_HASH
    assert manifest["control"]["result_hash"] == EXPECTED_CONTROL_RESULT_HASH
    assert manifest["C001"]["result_hash"] == EXPECTED_C001_RESULT_HASH
    assert manifest["C001"]["attribution_hash"] == EXPECTED_C001_ATTRIBUTION_HASH
    assert manifest["C002"]["result_hash"] == EXPECTED_C002_RESULT_HASH
    assert manifest["implementation_experiment"]["result_hash"] == EXPECTED_C1_IMP_001_RESULT_HASH
    assert manifest["implementation_experiment"]["development_registry_hash"] == EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH
    assert manifest["validation_status"] == "NOT_ACCESSED"
    assert manifest["strategy_v2_status"] == "NOT_CREATED"
    assert manifest["closure_timestamp"].endswith("Z")


def test_artifact_manifest_recomputes_and_files_match() -> None:
    manifest = _json(
        CLOSURE_ROOT / "manifest/family_c_closure_artifact_manifest_v1.json"
    )
    body = {key: value for key, value in manifest.items() if key != "artifact_manifest_hash"}
    assert canonical_hash(body) == manifest["artifact_manifest_hash"]
    assert manifest["family_c_closure_hash"] == EXPECTED_FAMILY_C_CLOSURE_HASH
    lifecycle_files = {
        "backend/tests/test_family_c_research_closure.py",
        "docs/strategy-family-research-roadmap-v1.md",
    }
    lifecycle_files = {
        "backend/tests/test_family_c_research_closure.py",
        "docs/strategy-family-research-roadmap-v1.md",
    }
    assert all(
        (REPO_ROOT / relative).is_file()
        and (relative in lifecycle_files or file_sha256(REPO_ROOT / relative) == expected)
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_no_performance_recomputation_or_new_family_c_experiment() -> None:
    governance = _summary()["governance"]
    assert governance["performance_recomputed"] is False
    assert governance["new_family_c_performance_experiments"] == 0
    assert governance["new_ranking_tested"] is False
    assert governance["compression_threshold_tested"] is False
    assert governance["capacity_changed"] is False
    assert governance["position_sizing_changed"] is False
    assert governance["holding_period_changed"] is False
    assert governance["stop_added"] is False
    assert governance["target_added"] is False
    source = (
        REPO_ROOT / "backend/app/research/strategy/family_c_research_closure.py"
    ).read_text(encoding="utf-8")
    assert "simulate_strategy(" not in source
    assert "build_family_c_development_evaluation(" not in source
    assert "build_c1_imp_001_development_evaluation(" not in source


def test_validation_and_strategy_v2_remain_unaccessed() -> None:
    summary = _summary()
    assert summary["final_statuses"]["FAMILY_C_VALIDATION_STATUS"] == "NOT_ACCESSED"
    assert summary["final_statuses"]["FAMILY_C_STRATEGY_V2_STATUS"] == "NOT_CREATED"
    assert summary["governance"]["validation_accessed"] is False
    assert summary["governance"]["validation_rows_loaded"] == 0
    assert summary["governance"]["strategy_v2_created"] is False


def test_roadmap_is_closed_and_family_d_is_next_planned() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert any(
        status in roadmap
        for status in (
            "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |",
            "| Family D | Opening Range / Stocks-in-Play | ACTIVE_PREREGISTRATION |",
        )
    )
    for family in "EFG":
        line = next(row for row in roadmap.splitlines() if row.startswith(f"| Family {family} |"))
        assert "PLANNED_NOT_STARTED" in line


def test_family_d_is_a_high_level_planning_note_only() -> None:
    note = _json(CLOSURE_ROOT / "handoff/family_d_planning_note_v1.json")
    assert note["NEXT_PLANNED_RESEARCH_FAMILY"] == NEXT_PLANNED_RESEARCH_FAMILY
    assert note["status"] == "NEXT_PLANNED"
    assert note["high_level_concept"] == [
        "UNUSUAL_EARLY_SESSION_ACTIVITY",
        "OPENING_RANGE_STRUCTURE",
        "INTRADAY_BREAKOUT_OR_CONTINUATION",
    ]
    assert note["potential_existing_infrastructure"] == "REAL_5_MINUTE_DATASET"
    assert note["parameters_defined"] is False
    assert note["implementation_started"] is False
    assert note["performance_run"] is False
    assert note["performance_claims"] == []
    assert all(note["preregistration_required_before_performance"].values())


def test_reports_and_documentation_exist() -> None:
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    assert (REPO_ROOT / "docs/strategy-family-c-closure-v1.md").is_file()
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[1])) == 1
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[2])) == 2
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[3])) == 4
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[4])) == 1


def test_baseline_and_family_c_commands_01_05_are_immutable() -> None:
    summary = _summary()
    baseline = family_c_baseline_snapshot(REPO_ROOT)
    command_chain = family_c_commands_01_05_snapshot(REPO_ROOT)
    assert summary["immutability"]["baseline_unchanged"] is True
    assert summary["immutability"]["baseline_snapshot_before"] == baseline["snapshot_hash"]
    assert summary["immutability"]["baseline_snapshot_after"] == baseline["snapshot_hash"]
    assert summary["immutability"]["family_c_commands_01_05_unchanged"] is True
    assert summary["immutability"]["family_c_commands_01_05_before"] == command_chain["snapshot_hash"]
    assert summary["immutability"]["family_c_commands_01_05_after"] == command_chain["snapshot_hash"]
    assert baseline["daily_history_version"] == "DAILY_HISTORY_PREHISTORY_V2"


def test_security_and_live_counters_are_zero() -> None:
    governance = _summary()["governance"]
    for field in (
        "live_signals_generated",
        "live_orders_placed",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "database_writes",
        "network_calls",
        "secrets_written",
    ):
        assert governance[field] == 0


def test_verification_is_ready_for_review() -> None:
    verification = _summary()["verification"]
    assert verification == {
        "backend_targeted_tests": "PASSED",
        "backend_full_tests": "PASSED",
        "frontend_build": "PASSED",
        "ready_for_review": True,
    }
