from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import (
    file_sha256,
    frozen_project_snapshot,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_closure import (
    closure_baseline_snapshot as family_a_closure_snapshot,
)
from app.research.strategy.family_b_history_remediation import DATA_VERSION
from app.research.strategy.family_b_research_closure import (
    family_b_baseline_snapshot,
)


COMMAND = "Step 03.03 / Command 06"
COMMAND_VERSION = "FAMILY_C_RESEARCH_CLOSURE_V1"
COMMAND_PROFILE = "BREAKOUT_CONTINUATION_CLOSURE_V1"
FAMILY_ID = "STRATEGY_FAMILY_C_BREAKOUT_CONTINUATION_V1"

FAMILY_C_RESEARCH_STATUS = "PAUSED_NO_VALIDATION_CANDIDATE"
FAMILY_C_EVIDENCE_STATUS = "POSITIVE_COMPRESSION_SIGNAL_NOT_PORTFOLIO_READY"
CONTROL_C_000_FINAL_STATUS = "CLOSED_NONVIABLE_CONTROL"
BRK_C_001_FINAL_STATUS = "PAUSED_POSITIVE_SIGNAL_INSUFFICIENT_IMPLEMENTATION"
C001_COMPRESSION_SIGNAL_STATUS = "PRESERVE_AS_POSITIVE_RESEARCH_EVIDENCE"
C1_IMP_001_FINAL_STATUS = "CLOSED_FAILED_IMPLEMENTATION_HYPOTHESIS"
BRK_C_002_FINAL_STATUS = "CLOSED_FAILED_DEVELOPMENT"
FAMILY_C_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_C_STRATEGY_V2_STATUS = "NOT_CREATED"
C001_FUTURE_RESEARCH_POLICY = (
    "REQUIRES_GENUINELY_NEW_ARCHITECTURE_OR_MULTI_STRATEGY_USE"
)

RESEARCH_LESSON_ID = "FAMILY_C_RESEARCH_LESSON_V1"
POSITIVE_EVIDENCE_ID = "EDGE-EVIDENCE-C-COMPRESSION-001"
VOLUME_NEGATIVE_EVIDENCE_ID = "EDGE-NEGATIVE-C-VOLUME-001"
RANKING_NEGATIVE_EVIDENCE_ID = "IMPLEMENTATION-NEGATIVE-C-COMPRESSION-RANK-001"
GOVERNANCE_POLICY_VERSION = "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_D_OPENING_RANGE_STOCKS_IN_PLAY"

EXPECTED_FAMILY_C_CONFIG_HASH = (
    "5ecb5604939e1230ba176dbb339ebaf15418482da7a68bbbea24370c805961a6"
)
EXPECTED_SUCCESS_CRITERIA_HASH = (
    "7bb950274ebe47ec7fafeb7e8659e07a457a4ddb169171aa97fe9ff9d0860a77"
)
EXPECTED_CONTROL_RESULT_HASH = (
    "efdf9ccdf70f4c58d1ce40e2f1e1ccb7e7fa8ad83c5fb3832ce0994d323b991f"
)
EXPECTED_C001_RESULT_HASH = (
    "8adc1aec00041256748a8fa086b4dae562a6841b844875fc39b3dd19b61680e4"
)
EXPECTED_C002_RESULT_HASH = (
    "49afe8ee5d766afa9a0e01195fa49041605c71483df0de9ac4c354b469a9a240"
)
EXPECTED_C001_ATTRIBUTION_HASH = (
    "26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b"
)
EXPECTED_C1_IMP_001_RESULT_HASH = (
    "013ce88f6b87ee6611065774a898345fd3e7bdf941002025195b844693dc15ee"
)
EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH = (
    "a56210f2bb06cde7cd867a4549771c113369ea27b958433ef3090c67736ef5e8"
)
EXPECTED_IMPLEMENTATION_CONFIG_HASH = (
    "d9de8dbbf0e288066565fcf9a4ef2b4cd494ed3f07760529298669226a119662"
)
EXPECTED_IMPLEMENTATION_PARAMETER_HASH = (
    "6a5b49423e3fb30c708c9e1ae6a7cf5a5c0cf7306666d4f35f7428123d36915c"
)
EXPECTED_IMPLEMENTATION_PREREGISTRATION_HASH = (
    "a5939b4d11282d0c8e40a2e1d9cebde79d8b62bf5d4a315adfcb8f853c366c7a"
)
EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH = (
    "90365ad9e45328a918bb714e03df78dfc049c0e335e9c6893216594c690978c0"
)
EXPECTED_IMPLEMENTATION_SIGNAL_SET_HASH = (
    "096a11a85a72138176fb02b28efec52030e00c819c1bc67bca6fd8ae41abce9f"
)
EXPECTED_FAMILY_C_CLOSURE_HASH = (
    "e1146522bed8e81b87af8123f481045697a788c3af9e3f7654279b20724910d1"
)

REPORT_NAMES = (
    "family_c_closure_v1_summary.json",
    "family_c_closure_v1_evidence.csv",
    "family_c_closure_v1_negative_evidence.csv",
    "family_c_closure_v1_lessons.csv",
    "family_c_closure_v1_handoff.csv",
)

PROHIBITED_INCREMENTAL_TUNING = (
    "COMPRESSION_6_7_9_10_PERCENT",
    "CAPACITY_10_15_25_30_40",
    "ALTERNATE_SAME_DAY_RANKING",
    "DIFFERENT_FIXED_POSITION_SIZE",
    "DIFFERENT_FIXED_HOLDING_PERIOD",
    "SIMPLE_STOP_OR_TARGET_ADDITION",
    "GAP_FILTERS",
    "VOLUME_PLUS_COMPRESSION_COMBINATION",
)


class FamilyCClosureInputMismatch(RuntimeError):
    pass


class FamilyCClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_c/v1/closure"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(document: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != hash_field}


def _require_hash(
    document: Mapping[str, Any], hash_field: str, expected_hash: str
) -> bool:
    return document.get(hash_field) == expected_hash and canonical_hash(
        _without_hash(document, hash_field)
    ) == expected_hash


def _input_paths(root: Path) -> dict[str, Path]:
    family_root = root / "data/research/strategy_families/family_c/v1"
    development = family_root / "development_evaluation"
    implementation = family_root / "implementation_research"
    implementation_development = implementation / "development_evaluation"
    return {
        "family_config": family_root / "registry/family_c_config_v1.json",
        "success_criteria": family_root / "governance/success_criteria_v1.json",
        "control": development / "control/control_c_000_development_result_v1.json",
        "C001": development / "brk_c_001/brk_c_001_development_result_v1.json",
        "C002": development / "brk_c_002/brk_c_002_development_result_v1.json",
        "attribution": family_root
        / "c001_attribution_audit/manifests/family_c_c001_attribution_result_v1.json",
        "implementation_config": implementation
        / "registry/implementation_research_config_v1.json",
        "implementation_preregistration": implementation
        / "registry/c1_imp_001_preregistration_v1.json",
        "implementation_criteria": implementation
        / "governance/implementation_success_criteria_v1.json",
        "implementation_signal_set": implementation / "ranking/c001_signal_set_v1.json",
        "implementation_result": implementation_development
        / "treatment/c1_imp_001_development_result_v1.json",
        "implementation_registry": implementation_development
        / "comparison/implementation_development_registry_v1.json",
        "implementation_manifest": implementation_development
        / "manifests/c1_imp_001_development_manifest_v1.json",
        "implementation_summary": root
        / "data/reports/family_c_imp001_dev_v1_summary.json",
    }


def verify_family_c_closure_inputs(root: Path) -> dict[str, Any]:
    try:
        paths = _input_paths(root)
        documents = {name: _read_json(path) for name, path in paths.items()}
        control = documents["control"]
        c001 = documents["C001"]
        c002 = documents["C002"]
        attribution = documents["attribution"]
        implementation = documents["implementation_result"]
        registry = documents["implementation_registry"]
        implementation_manifest = documents["implementation_manifest"]
        implementation_summary = documents["implementation_summary"]
        artifact_mismatches = [
            relative
            for relative, expected in implementation_manifest["artifact_hashes"].items()
            if not (root / relative).is_file()
            or file_sha256(root / relative) != expected
        ]
        checks = {
            "family_config_hash": _require_hash(
                documents["family_config"],
                "family_c_config_hash",
                EXPECTED_FAMILY_C_CONFIG_HASH,
            ),
            "success_criteria_hash": _require_hash(
                documents["success_criteria"],
                "success_criteria_hash",
                EXPECTED_SUCCESS_CRITERIA_HASH,
            ),
            "control_result_hash": _require_hash(
                control, "control_c_000_result_hash", EXPECTED_CONTROL_RESULT_HASH
            ),
            "C001_result_hash": _require_hash(
                c001, "brk_c_001_result_hash", EXPECTED_C001_RESULT_HASH
            ),
            "C002_result_hash": _require_hash(
                c002, "brk_c_002_result_hash", EXPECTED_C002_RESULT_HASH
            ),
            "C001_attribution_hash": _require_hash(
                attribution,
                "family_c_c001_attribution_hash",
                EXPECTED_C001_ATTRIBUTION_HASH,
            ),
            "implementation_config_hash": _require_hash(
                documents["implementation_config"],
                "implementation_research_config_hash",
                EXPECTED_IMPLEMENTATION_CONFIG_HASH,
            ),
            "implementation_parameter_hash": documents[
                "implementation_preregistration"
            ]["parameter_hash"]
            == EXPECTED_IMPLEMENTATION_PARAMETER_HASH,
            "implementation_preregistration_hash": _require_hash(
                documents["implementation_preregistration"],
                "preregistration_hash",
                EXPECTED_IMPLEMENTATION_PREREGISTRATION_HASH,
            ),
            "implementation_success_criteria_hash": _require_hash(
                documents["implementation_criteria"],
                "implementation_success_criteria_hash",
                EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
            ),
            "implementation_signal_set_hash": _require_hash(
                documents["implementation_signal_set"],
                "c001_signal_set_hash",
                EXPECTED_IMPLEMENTATION_SIGNAL_SET_HASH,
            ),
            "C1_IMP_001_result_hash": _require_hash(
                implementation,
                "c1_imp_001_result_hash",
                EXPECTED_C1_IMP_001_RESULT_HASH,
            ),
            "implementation_development_registry_hash": _require_hash(
                registry,
                "implementation_development_registry_hash",
                EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH,
            ),
            "control_nonviable": control["evaluation"]["CONTROL_VIABLE"] is False
            and control["evaluation"]["classification"]
            == "CONTROL_NOT_VIABLE_NONFATAL",
            "C001_partially_supported": c001["evaluation"]["classification"]
            == "PARTIALLY_SUPPORTED",
            "C002_failed": c002["evaluation"]["classification"] == "FAILED",
            "compression_signal_positive": attribution["signal_cohort"][
                "C001_SIGNAL_QUALITY_ATTRIBUTION"
            ]
            == "CLEAR_POSITIVE"
            and attribution["signal_cohort"]["C001_SIGNAL_TEMPORAL_CONSISTENCY"]
            == "MOSTLY_CONSISTENT"
            and attribution["attribution"]["C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"]
            == "PRIMARILY_COMPRESSION_SIGNAL",
            "capacity_issue_material": attribution["capacity"][
                "C001_CAPACITY_SELECTION_QUALITY"
            ]
            == "SELECTED_WORSE"
            and attribution["capacity"]["BREAKOUT_STRENGTH_CAPACITY_RANKING_RESULT"]
            == "NO_DISCRIMINATION"
            and attribution["capacity"]["C001_CAPACITY_EFFECT_MATERIALITY"]
            == "MATERIAL",
            "failed_implementation": implementation[
                "C1_IMP_001_DEVELOPMENT_RESULT"
            ]
            == "FAILED"
            and implementation["COMPRESSION_PRIORITY_REPLACEMENT_QUALITY"] == "WORSE"
            and implementation["evaluation"]["quality_pass_count"] == 0
            and implementation["evaluation"]["criteria_pass_count"] == 5,
            "one_implementation_experiment_only": registry["experiment_count"] == 1
            and registry["experiments"][0]["experiment_id"] == "C1-IMP-001"
            and registry["experiments"][0]["result_hash"]
            == EXPECTED_C1_IMP_001_RESULT_HASH,
            "implementation_manifest_clean": canonical_hash(
                _without_hash(
                    implementation_manifest, "c1_imp_001_development_manifest_hash"
                )
            )
            == implementation_manifest["c1_imp_001_development_manifest_hash"]
            and implementation_manifest["summary_hash"]
            == file_sha256(paths["implementation_summary"])
            and not artifact_mismatches,
            "command_05_review_ready": implementation_summary["verification"][
                "ready_for_review"
            ]
            is True,
            "development_only_validation_not_accessed": all(
                document["development_partition"]["validation_accessed"] is False
                for document in (control, c001, c002, attribution, implementation)
            )
            and implementation["governance"]["validation_accessed"] is False,
            "strategy_v2_not_created": implementation["governance"][
                "strategy_v2_created"
            ]
            is False,
        }
        if not all(checks.values()):
            failed = {key: value for key, value in checks.items() if not value}
            raise ValueError(failed)
        return {"status": "VERIFIED", "checks": checks, **documents}
    except FamilyCClosureInputMismatch:
        raise
    except Exception as error:  # noqa: BLE001 - normalize the closure gate
        raise FamilyCClosureInputMismatch(
            f"FAMILY_C_CLOSURE_INPUT_MISMATCH: {error}"
        ) from error


def family_c_commands_01_05_snapshot(root: Path) -> dict[str, Any]:
    family_root = root / "data/research/strategy_families/family_c/v1"
    closure_root = output_root(root)
    paths = [
        path
        for path in family_root.rglob("*")
        if path.is_file() and closure_root not in path.parents
    ]
    paths.extend(
        path
        for path in (root / "data/reports").glob("family_c_*")
        if not path.name.startswith("family_c_closure_v1_")
    )
    for relative in (
        "backend/app/research/strategy/family_c_breakout_continuation.py",
        "backend/app/research/strategy/family_c_development_evaluation.py",
        "backend/app/research/strategy/family_c_c001_attribution_audit.py",
        "backend/app/research/strategy/family_c_c001_implementation_research.py",
        "backend/app/research/strategy/family_c_c001_implementation_development.py",
        "backend/scripts/run_family_c_breakout_continuation.py",
        "backend/scripts/run_family_c_development_evaluation.py",
        "backend/scripts/run_family_c_c001_attribution_audit.py",
        "backend/scripts/run_family_c_c001_implementation_research.py",
        "backend/scripts/run_family_c_c001_implementation_development.py",
        "backend/tests/test_family_c_breakout_continuation.py",
        "backend/tests/test_family_c_development_evaluation.py",
        "backend/tests/test_family_c_c001_attribution_audit.py",
        "backend/tests/test_family_c_c001_implementation_research.py",
        "backend/tests/test_family_c_c001_implementation_development.py",
        "docs/strategy-family-c-breakout-continuation-v1.md",
        "docs/strategy-family-c-development-evaluation-v1.md",
        "docs/strategy-family-c-c001-attribution-audit-v1.md",
        "docs/strategy-family-c-c001-implementation-research-v1.md",
        "docs/strategy-family-c-c001-implementation-development-v1.md",
    ):
        path = root / relative
        if path.is_file():
            paths.append(path)
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }
    return {"artifact_hashes": hashes, "snapshot_hash": canonical_hash(hashes)}


def family_c_baseline_snapshot(root: Path) -> dict[str, Any]:
    inputs = verify_family_c_closure_inputs(root)
    project = frozen_project_snapshot(root)
    family_a = family_a_closure_snapshot(root)
    family_b = family_b_baseline_snapshot(root)
    command_chain = family_c_commands_01_05_snapshot(root)
    semantic = {
        "strategy_v1_foundation_hash": project["foundation_hash"],
        "cap4_validation_state": project["cap4_validation_state"],
        "cap4_validation_run_count": project["cap4_validation_run_count"],
        "cap4_validation_result_hash": project["cap4_validation_result_hash"],
        "family_a_closure_snapshot_hash": family_a["snapshot_hash"],
        "family_b_baseline_snapshot_hash": family_b["snapshot_hash"],
        "family_c_commands_01_05_snapshot_hash": command_chain["snapshot_hash"],
        "daily_history_version": DATA_VERSION,
        "verified_input_count": len(inputs["checks"]),
        "validation_accessed": False,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def _positive_evidence(inputs: Mapping[str, Any]) -> dict[str, Any]:
    attribution = inputs["attribution"]
    cohorts = {
        row["cohort"]: row for row in attribution["signal_cohort"]["compression"]
    }
    difference = attribution["signal_cohort"]["compression_pass_minus_fail"]
    entry = {
        "evidence_id": POSITIVE_EVIDENCE_ID,
        "family_id": FAMILY_ID,
        "status": "RESEARCH_EVIDENCE_NOT_VALIDATED",
        "finding": (
            "10-session compression <=8% before a strict 20-session close breakout "
            "demonstrated positive event-level discrimination in DEVELOPMENT."
        ),
        "definition": {
            "compression_window_sessions": 10,
            "compression_threshold_maximum": "0.08",
            "breakout_window_sessions": 20,
            "breakout_rule": "STRICT_CLOSE_ABOVE_PRIOR_WINDOW_HIGH",
            "holding_sessions": 10,
        },
        "compression_pass": cohorts["COMPRESSION_PASS"],
        "compression_fail": cohorts["COMPRESSION_FAIL"],
        "pass_minus_fail": {
            "win_rate": difference["win_rate"],
            "net_expectancy": difference["net_expectancy"],
            "net_profit_factor": difference["net_profit_factor"],
            "median_MFE": difference["median_MFE"],
            "median_MAE": difference["median_MAE"],
        },
        "temporal_consistency": attribution["signal_cohort"][
            "C001_SIGNAL_TEMPORAL_CONSISTENCY"
        ],
        "signal_quality_attribution": attribution["signal_cohort"][
            "C001_SIGNAL_QUALITY_ATTRIBUTION"
        ],
        "development_advantage_attribution": attribution["attribution"][
            "C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"
        ],
        "source_attribution_hash": EXPECTED_C001_ATTRIBUTION_HASH,
        "limitations": [
            "DEVELOPMENT_ONLY_VALIDATION_NOT_ACCESSED",
            "EVENT_LEVEL_NORMALIZED_FIXED_NOTIONAL_EVIDENCE",
            "PORTFOLIO_CAPACITY_AND_ADMISSION_EFFECTS_REMAIN_MATERIAL",
            "CURRENT_EXECUTABLE_IMPLEMENTATION_NOT_ROBUST_ENOUGH",
            "NO_OUT_OF_SAMPLE_OR_LIVE_CLAIM",
            "DO_NOT_GENERALIZE_BEYOND_TESTED_DEFINITIONS",
        ],
    }
    body = {"registry_version": "FAMILY_C_POSITIVE_EVIDENCE_REGISTRY_V1", "entries": [entry]}
    return {**body, "positive_evidence_registry_hash": canonical_hash(body)}


def _negative_evidence(inputs: Mapping[str, Any]) -> dict[str, Any]:
    c002 = inputs["C002"]
    implementation = inputs["implementation_result"]
    entries = [
        {
            "evidence_id": VOLUME_NEGATIVE_EVIDENCE_ID,
            "status": "CLOSED_NEGATIVE_RESEARCH_EVIDENCE",
            "finding": (
                "1.5x breakout-day volume expansion did not improve the tested "
                "Family C architecture."
            ),
            "experiment_id": "BRK-C-002",
            "result": c002["evaluation"]["classification"],
            "result_hash": EXPECTED_C002_RESULT_HASH,
            "net_total_return": c002["executable_metrics"]["net_total_return"],
            "net_CAGR": c002["executable_metrics"]["net_CAGR"],
            "net_expectancy": c002["executable_metrics"]["net_expectancy"],
            "net_profit_factor": c002["executable_metrics"]["net_profit_factor"],
            "scope_limit": "ONLY_THE_TESTED_1_5X_VOLUME_DEFINITION",
        },
        {
            "evidence_id": RANKING_NEGATIVE_EVIDENCE_ID,
            "status": "CLOSED_NEGATIVE_IMPLEMENTATION_EVIDENCE",
            "finding": "Tightest-compression-first capacity ranking failed.",
            "experiment_id": "C1-IMP-001",
            "result": implementation["C1_IMP_001_DEVELOPMENT_RESULT"],
            "replacement_quality": implementation[
                "COMPRESSION_PRIORITY_REPLACEMENT_QUALITY"
            ],
            "quality_dimensions_passed": implementation["evaluation"][
                "quality_pass_count"
            ],
            "standard_criteria_passed": implementation["evaluation"][
                "criteria_pass_count"
            ],
            "result_hash": EXPECTED_C1_IMP_001_RESULT_HASH,
            "scope_limit": "ONLY_THE_PREREGISTERED_COMPRESSION_PRIORITY_RANKING",
        },
    ]
    body = {"registry_version": "FAMILY_C_NEGATIVE_EVIDENCE_REGISTRY_V1", "entries": entries}
    return {**body, "negative_evidence_registry_hash": canonical_hash(body)}


def _research_lesson() -> dict[str, Any]:
    body = {
        "lesson_id": RESEARCH_LESSON_ID,
        "family_id": FAMILY_ID,
        "lesson": (
            "A compact pre-breakout range improved 10-session breakout event quality "
            "in DEVELOPMENT, but frequent overlapping signals and portfolio-capacity/"
            "admission mechanics prevented the current implementation from converting "
            "that signal edge into a sufficiently robust executable strategy."
        ),
        "volume_lesson": (
            "Volume expansion at the tested 1.5x definition did not improve the strategy."
        ),
        "scope_limit": "Do not generalize beyond tested definitions.",
        "sixty_percent_win_rate": {
            "achieved": False,
            "control": "0.4639249639249639249639249639",
            "C001_portfolio": "0.4974358974358974358974358974",
            "C001_event_cohort": "0.5142453496585825288438898046",
            "C1_IMP_001": "0.4927163667523564695801199657",
            "policy": "DO_NOT_ALTER_RESEARCH_CONCLUSIONS_SOLELY_TO_TARGET_60_PERCENT",
        },
    }
    return {**body, "research_lesson_hash": canonical_hash(body)}


def _final_status_record() -> dict[str, Any]:
    body = {
        "family_id": FAMILY_ID,
        "FAMILY_C_RESEARCH_STATUS": FAMILY_C_RESEARCH_STATUS,
        "FAMILY_C_EVIDENCE_STATUS": FAMILY_C_EVIDENCE_STATUS,
        "CONTROL_C_000_FINAL_STATUS": CONTROL_C_000_FINAL_STATUS,
        "BRK_C_001_FINAL_STATUS": BRK_C_001_FINAL_STATUS,
        "C001_COMPRESSION_SIGNAL_STATUS": C001_COMPRESSION_SIGNAL_STATUS,
        "C1_IMP_001_FINAL_STATUS": C1_IMP_001_FINAL_STATUS,
        "BRK_C_002_FINAL_STATUS": BRK_C_002_FINAL_STATUS,
        "FAMILY_C_VALIDATION_STATUS": FAMILY_C_VALIDATION_STATUS,
        "FAMILY_C_STRATEGY_V2_STATUS": FAMILY_C_STRATEGY_V2_STATUS,
        "C001_FUTURE_RESEARCH_POLICY": C001_FUTURE_RESEARCH_POLICY,
    }
    return {**body, "family_c_final_status_hash": canonical_hash(body)}


def _governance_record() -> dict[str, Any]:
    body = {
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        "policy_remains_active": True,
        "incremental_family_c_tuning_authorized": False,
        "prohibited_incremental_tuning": list(PROHIBITED_INCREMENTAL_TUNING),
        "future_family_c_requirement": {
            "new_conceptual_hypothesis": True,
            "new_experiment_id": True,
            "preregistration": True,
            "justification_beyond_threshold_or_ranking_tweak": True,
        },
        "performance_recomputed": False,
        "new_family_c_performance_experiments": 0,
        "new_ranking_tested": False,
        "compression_threshold_tested": False,
        "capacity_changed": False,
        "position_sizing_changed": False,
        "holding_period_changed": False,
        "stop_added": False,
        "target_added": False,
        "validation_accessed": False,
        "validation_rows_loaded": 0,
        "strategy_v2_created": False,
        "family_d_implementation_started": False,
        "family_d_performance_run": False,
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "database_writes": 0,
        "network_calls": 0,
        "secrets_written": 0,
    }
    return {**body, "family_c_closure_governance_hash": canonical_hash(body)}


def _family_d_planning_note() -> dict[str, Any]:
    body = {
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "NEXT_PLANNED",
        "high_level_concept": [
            "UNUSUAL_EARLY_SESSION_ACTIVITY",
            "OPENING_RANGE_STRUCTURE",
            "INTRADAY_BREAKOUT_OR_CONTINUATION",
        ],
        "potential_existing_infrastructure": "REAL_5_MINUTE_DATASET",
        "materially_different_from": [
            "MEDIUM_TERM_MOMENTUM",
            "ABSOLUTE_MOMENTUM_FILTERS",
            "DAILY_BREAKOUT_CONTINUATION",
        ],
        "performance_claims": [],
        "parameters_defined": False,
        "implementation_started": False,
        "performance_run": False,
        "validation_accessed": False,
        "authorized_to_start": False,
        "preregistration_required_before_performance": {
            "exact_opening_range": True,
            "activity_definition": True,
            "entry_exit_rules": True,
            "capital_capacity": True,
            "success_criteria": True,
        },
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
    }
    return {**body, "family_d_planning_note_hash": canonical_hash(body)}


def _closure_manifest_body(
    inputs: Mapping[str, Any],
    positive: Mapping[str, Any],
    negative: Mapping[str, Any],
    statuses: Mapping[str, Any],
    governance: Mapping[str, Any],
    handoff: Mapping[str, Any],
    closure_timestamp: str,
) -> dict[str, Any]:
    return {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_ID,
        "family_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "experiment_id": "CONTROL-C-000",
            "result_hash": EXPECTED_CONTROL_RESULT_HASH,
            "development_result": inputs["control"]["evaluation"]["classification"],
            "final_status": CONTROL_C_000_FINAL_STATUS,
        },
        "C001": {
            "experiment_id": "BRK-C-001",
            "result_hash": EXPECTED_C001_RESULT_HASH,
            "development_result": inputs["C001"]["evaluation"]["classification"],
            "attribution_hash": EXPECTED_C001_ATTRIBUTION_HASH,
            "final_status": BRK_C_001_FINAL_STATUS,
            "signal_status": C001_COMPRESSION_SIGNAL_STATUS,
        },
        "C002": {
            "experiment_id": "BRK-C-002",
            "result_hash": EXPECTED_C002_RESULT_HASH,
            "development_result": inputs["C002"]["evaluation"]["classification"],
            "final_status": BRK_C_002_FINAL_STATUS,
        },
        "implementation_experiment": {
            "experiment_id": "C1-IMP-001",
            "implementation_config_hash": EXPECTED_IMPLEMENTATION_CONFIG_HASH,
            "parameter_hash": EXPECTED_IMPLEMENTATION_PARAMETER_HASH,
            "preregistration_hash": EXPECTED_IMPLEMENTATION_PREREGISTRATION_HASH,
            "success_criteria_hash": EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
            "signal_set_hash": EXPECTED_IMPLEMENTATION_SIGNAL_SET_HASH,
            "result_hash": EXPECTED_C1_IMP_001_RESULT_HASH,
            "development_registry_hash": EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH,
            "development_result": inputs["implementation_result"][
                "C1_IMP_001_DEVELOPMENT_RESULT"
            ],
            "replacement_quality": inputs["implementation_result"][
                "COMPRESSION_PRIORITY_REPLACEMENT_QUALITY"
            ],
            "final_status": C1_IMP_001_FINAL_STATUS,
        },
        "final_statuses": _without_hash(statuses, "family_c_final_status_hash"),
        "positive_evidence_id": POSITIVE_EVIDENCE_ID,
        "negative_evidence_ids": [
            VOLUME_NEGATIVE_EVIDENCE_ID,
            RANKING_NEGATIVE_EVIDENCE_ID,
        ],
        "evidence_registry_hashes": {
            "positive": positive["positive_evidence_registry_hash"],
            "negative": negative["negative_evidence_registry_hash"],
        },
        "governance_hash": governance["family_c_closure_governance_hash"],
        "family_d_planning_note_hash": handoff["family_d_planning_note_hash"],
        "validation_status": FAMILY_C_VALIDATION_STATUS,
        "strategy_v2_status": FAMILY_C_STRATEGY_V2_STATUS,
        "closure_timestamp": closure_timestamp,
    }


def _write_immutable_closure_manifest(
    path: Path, body: Mapping[str, Any]
) -> dict[str, Any]:
    document = {**body, "family_c_closure_hash": canonical_hash(body)}
    if path.is_file():
        existing = _read_json(path)
        existing_hash = existing.get("family_c_closure_hash")
        if canonical_hash(_without_hash(existing, "family_c_closure_hash")) != existing_hash:
            raise FamilyCClosureImmutabilityError(
                "Existing Family C closure manifest has an invalid closure hash"
            )
        if existing != document:
            raise FamilyCClosureImmutabilityError(
                "Existing Family C closure manifest differs from the requested closure"
            )
        return existing
    write_json(path, document)
    return document


def _verify_roadmap(root: Path) -> bool:
    roadmap = (root / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    required = (
        "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |",
        "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |",
        "| Family E | Pullback / Reclaim | PLANNED_NOT_STARTED |",
        "| Family F | Catalyst Momentum | PLANNED_NOT_STARTED |",
        "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |",
    )
    return all(line in roadmap for line in required)


def _write_artifact_manifest(root: Path, closure_hash: str) -> dict[str, Any]:
    manifest_path = output_root(root) / "manifest/family_c_closure_artifact_manifest_v1.json"
    paths = [
        path
        for path in output_root(root).rglob("*")
        if path.is_file() and path != manifest_path
    ]
    paths.extend(root / "data/reports" / name for name in REPORT_NAMES)
    paths.extend(
        root / relative
        for relative in (
            "docs/strategy-family-c-closure-v1.md",
            "docs/strategy-family-research-roadmap-v1.md",
            "backend/app/research/strategy/family_c_research_closure.py",
            "backend/scripts/run_family_c_research_closure.py",
            "backend/tests/test_family_c_research_closure.py",
        )
    )
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
        if path.is_file()
    }
    body = {
        "command_version": COMMAND_VERSION,
        "family_c_closure_hash": closure_hash,
        "artifact_hashes": artifact_hashes,
    }
    document = {**body, "artifact_manifest_hash": canonical_hash(body)}
    write_json(manifest_path, document)
    return document


def build_family_c_research_closure(root: Path) -> dict[str, Any]:
    inputs = verify_family_c_closure_inputs(root)
    baseline_before = family_c_baseline_snapshot(root)
    commands_before = family_c_commands_01_05_snapshot(root)
    closure = output_root(root)
    reports = root / "data/reports"
    for directory in ("manifest", "evidence", "governance", "handoff"):
        (closure / directory).mkdir(parents=True, exist_ok=True)

    positive = _positive_evidence(inputs)
    negative = _negative_evidence(inputs)
    lesson = _research_lesson()
    statuses = _final_status_record()
    governance = _governance_record()
    handoff = _family_d_planning_note()
    write_json(closure / "evidence/positive_evidence_registry_v1.json", positive)
    write_json(closure / "evidence/negative_evidence_registry_v1.json", negative)
    write_json(closure / "governance/family_c_research_lesson_v1.json", lesson)
    write_json(closure / "governance/family_c_final_status_v1.json", statuses)
    write_json(closure / "governance/family_c_closure_governance_v1.json", governance)
    write_json(closure / "handoff/family_d_planning_note_v1.json", handoff)

    manifest_path = closure / "manifest/family_c_closure_manifest_v1.json"
    timestamp = (
        _read_json(manifest_path)["closure_timestamp"]
        if manifest_path.is_file()
        else utc_now()
    )
    manifest = _write_immutable_closure_manifest(
        manifest_path,
        _closure_manifest_body(
            inputs, positive, negative, statuses, governance, handoff, timestamp
        ),
    )
    if EXPECTED_FAMILY_C_CLOSURE_HASH and (
        manifest["family_c_closure_hash"] != EXPECTED_FAMILY_C_CLOSURE_HASH
    ):
        raise FamilyCClosureImmutabilityError(
            "Generated Family C closure hash differs from the frozen expected hash"
        )

    positive_entry = positive["entries"][0]
    pass_metrics = positive_entry["compression_pass"]
    fail_metrics = positive_entry["compression_fail"]
    difference = positive_entry["pass_minus_fail"]
    write_csv(
        reports / REPORT_NAMES[1],
        [
            {
                "evidence_id": POSITIVE_EVIDENCE_ID,
                "status": positive_entry["status"],
                "finding": positive_entry["finding"],
                "pass_event_count": pass_metrics["event_count"],
                "fail_event_count": fail_metrics["event_count"],
                "pass_win_rate": pass_metrics["win_rate"],
                "fail_win_rate": fail_metrics["win_rate"],
                "win_rate_difference": difference["win_rate"],
                "pass_net_expectancy": pass_metrics["net_expectancy"],
                "fail_net_expectancy": fail_metrics["net_expectancy"],
                "expectancy_difference": difference["net_expectancy"],
                "pass_net_profit_factor": pass_metrics["net_profit_factor"],
                "fail_net_profit_factor": fail_metrics["net_profit_factor"],
                "profit_factor_difference": difference["net_profit_factor"],
                "median_MFE_difference": difference["median_MFE"],
                "median_MAE_difference": difference["median_MAE"],
                "temporal_consistency": positive_entry["temporal_consistency"],
            }
        ],
    )
    write_csv(
        reports / REPORT_NAMES[2],
        [
            {
                "evidence_id": entry["evidence_id"],
                "status": entry["status"],
                "experiment_id": entry["experiment_id"],
                "finding": entry["finding"],
                "result": entry["result"],
                "result_hash": entry["result_hash"],
                "scope_limit": entry["scope_limit"],
            }
            for entry in negative["entries"]
        ],
    )
    write_csv(
        reports / REPORT_NAMES[3],
        [
            {"lesson_id": RESEARCH_LESSON_ID, "topic": "PRIMARY", "lesson": lesson["lesson"]},
            {"lesson_id": RESEARCH_LESSON_ID, "topic": "VOLUME", "lesson": lesson["volume_lesson"]},
            {"lesson_id": RESEARCH_LESSON_ID, "topic": "SCOPE", "lesson": lesson["scope_limit"]},
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "WIN_RATE",
                "lesson": (
                    "No tested Family C result achieved 60%; do not alter research "
                    "conclusions solely to target 60%."
                ),
            },
        ],
    )
    write_csv(
        reports / REPORT_NAMES[4],
        [
            {
                "next_planned_research_family": NEXT_PLANNED_RESEARCH_FAMILY,
                "status": handoff["status"],
                "concept": " + ".join(handoff["high_level_concept"]),
                "potential_existing_infrastructure": handoff[
                    "potential_existing_infrastructure"
                ],
                "parameters_defined": handoff["parameters_defined"],
                "implementation_started": handoff["implementation_started"],
                "performance_run": handoff["performance_run"],
            }
        ],
    )

    commands_after = family_c_commands_01_05_snapshot(root)
    baseline_after = family_c_baseline_snapshot(root)
    if commands_before != commands_after or baseline_before != baseline_after:
        raise FamilyCClosureImmutabilityError(
            "Family C Commands 01-05 or an earlier research baseline changed"
        )
    if not _verify_roadmap(root):
        raise FamilyCClosureImmutabilityError(
            "Family research roadmap does not contain the required closure states"
        )

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "family_id": FAMILY_ID,
        "freeze_gate": {"status": inputs["status"], "checks": inputs["checks"]},
        "family_c_closure_hash": manifest["family_c_closure_hash"],
        "final_statuses": _without_hash(statuses, "family_c_final_status_hash"),
        "research_lesson": lesson,
        "positive_evidence": positive_entry,
        "negative_evidence": negative["entries"],
        "roadmap": {
            "family_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
            "family_B": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_C": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_D": "NEXT_PLANNED",
            "families_E_G": "PLANNED_NOT_STARTED",
        },
        "handoff": handoff,
        "governance": governance,
        "immutability": {
            "baseline_snapshot_before": baseline_before["snapshot_hash"],
            "baseline_snapshot_after": baseline_after["snapshot_hash"],
            "baseline_unchanged": True,
            "family_c_commands_01_05_before": commands_before["snapshot_hash"],
            "family_c_commands_01_05_after": commands_after["snapshot_hash"],
            "family_c_commands_01_05_unchanged": True,
        },
        "storage": {
            "closure_root": closure.relative_to(root).as_posix(),
            "closure_manifest": manifest_path.relative_to(root).as_posix(),
            "positive_evidence_registry": (
                closure / "evidence/positive_evidence_registry_v1.json"
            ).relative_to(root).as_posix(),
            "negative_evidence_registry": (
                closure / "evidence/negative_evidence_registry_v1.json"
            ).relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        },
        "known_limitations": [
            "DEVELOPMENT_ONLY_VALIDATION_NOT_ACCESSED",
            "POSITIVE_EVIDENCE_IS_EVENT_LEVEL_NOT_PORTFOLIO_READY",
            "CAPACITY_AND_ADMISSION_MECHANICS_REMAIN_UNRESOLVED",
            "ONLY_ONE_ALTERNATIVE_CAPACITY_RANKING_WAS_PREREGISTERED_AND_TESTED",
            "NO_OUT_OF_SAMPLE_OR_LIVE_CLAIM",
            "FAMILY_D_IS_A_PLANNING_NOTE_ONLY",
        ],
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(reports / REPORT_NAMES[0], summary)
    _write_artifact_manifest(root, manifest["family_c_closure_hash"])
    return summary


def finalize_family_c_research_closure(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    passed = all(
        value == "PASSED"
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    _write_artifact_manifest(root, summary["family_c_closure_hash"])
    return summary


__all__ = [
    "BRK_C_001_FINAL_STATUS",
    "BRK_C_002_FINAL_STATUS",
    "C001_COMPRESSION_SIGNAL_STATUS",
    "C001_FUTURE_RESEARCH_POLICY",
    "C1_IMP_001_FINAL_STATUS",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "CONTROL_C_000_FINAL_STATUS",
    "EXPECTED_C001_ATTRIBUTION_HASH",
    "EXPECTED_C001_RESULT_HASH",
    "EXPECTED_C002_RESULT_HASH",
    "EXPECTED_C1_IMP_001_RESULT_HASH",
    "EXPECTED_CONTROL_RESULT_HASH",
    "EXPECTED_FAMILY_C_CLOSURE_HASH",
    "EXPECTED_FAMILY_C_CONFIG_HASH",
    "EXPECTED_IMPLEMENTATION_DEVELOPMENT_REGISTRY_HASH",
    "EXPECTED_SUCCESS_CRITERIA_HASH",
    "FAMILY_C_EVIDENCE_STATUS",
    "FAMILY_C_RESEARCH_STATUS",
    "FAMILY_C_STRATEGY_V2_STATUS",
    "FAMILY_C_VALIDATION_STATUS",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "POSITIVE_EVIDENCE_ID",
    "RANKING_NEGATIVE_EVIDENCE_ID",
    "REPORT_NAMES",
    "VOLUME_NEGATIVE_EVIDENCE_ID",
    "build_family_c_research_closure",
    "family_c_baseline_snapshot",
    "family_c_commands_01_05_snapshot",
    "finalize_family_c_research_closure",
    "verify_family_c_closure_inputs",
]
