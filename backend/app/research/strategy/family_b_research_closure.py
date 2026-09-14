from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_momentum import (
    file_sha256,
    frozen_project_snapshot,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_closure import (
    EXPECTED_CLOSURE_HASH as EXPECTED_FAMILY_A_CLOSURE_HASH,
    closure_baseline_snapshot as family_a_closure_snapshot,
)
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
)
from app.research.strategy.family_b_b002_clean_reevaluation import (
    EXPECTED_B002_CLEAN_REEVALUATION_HASH,
    EXPECTED_CLEAN_B002_RESULT_HASH,
    EXPECTED_CLEAN_CONTROL_RESULT_HASH,
    EXPECTED_CLEAN_RUN_MANIFEST_HASH,
    verify_freeze_gate as verify_clean_reevaluation_inputs,
)
from app.research.strategy.family_b_development_evaluation import (
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
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
    CONTROL_ID,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_VERSION,
)


COMMAND = "Step 03.02 / Command 06"
COMMAND_VERSION = "FAMILY_B_RESEARCH_CLOSURE_V1"
COMMAND_PROFILE = "RELATIVE_ABSOLUTE_MOMENTUM_CLOSURE_V1"

FAMILY_B_RESEARCH_STATUS = "PAUSED_NO_VALIDATION_CANDIDATE"
FAMILY_B_EVIDENCE_STATUS = "NO_CLEAR_INCREMENTAL_EDGE_OVER_RELATIVE_MOMENTUM"
MOM_B_001_FINAL_STATUS = "CLOSED_REDUNDANT_FILTER"
MOM_B_002_FINAL_STATUS = "CLOSED_INSUFFICIENT_DISTINCT_EVIDENCE"
FAMILY_B_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_B_STRATEGY_V2_STATUS = "NOT_CREATED"
RESEARCH_LESSON_ID = "FAMILY_B_RESEARCH_LESSON_V1"
GOVERNANCE_POLICY_VERSION = "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_C_BREAKOUT_CONTINUATION"

EXPECTED_FAMILY_B_CLOSURE_HASH = (
    "32e510424551e01fd54aac4711fa90fa08c711856c80b812d797b3a2f8faf6b0"
)

REPORT_NAMES = (
    "family_b_closure_v1_summary.json",
    "family_b_closure_v1_evidence.csv",
    "family_b_closure_v1_lessons.csv",
    "family_b_closure_v1_handoff.csv",
)

PROHIBITED_INCREMENTAL_TUNING = (
    "SMA100",
    "SMA150",
    "SMA250",
    "50_200_CROSSOVER",
    "POSITIVE_RETURN_BUFFERS",
    "COMBINED_B001_B002_FILTER",
    "ALTERNATIVE_TOP_DECILE_BREADTH",
)


class FamilyBClosureInputMismatch(RuntimeError):
    pass


class FamilyBClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_b/v1/closure"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recompute_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash(
        {key: value for key, value in document.items() if key != hash_field}
    )


def _require_hash(
    document: Mapping[str, Any], hash_field: str, expected_hash: str
) -> bool:
    return (
        document.get(hash_field) == expected_hash
        and _recompute_hash(document, hash_field) == expected_hash
    )


def verify_family_b_closure_inputs(root: Path) -> dict[str, Any]:
    try:
        clean_gate = verify_clean_reevaluation_inputs(root)
        command_02_results = {
            CONTROL_ID: _read_json(
                root
                / "data/research/strategy_families/family_b/v1/"
                "development_evaluation/control/development_result_v1.json"
            ),
            "MOM-B-001": _read_json(
                root
                / "data/research/strategy_families/family_b/v1/"
                "development_evaluation/mom_b_001/development_result_v1.json"
            ),
            "MOM-B-002": _read_json(
                root
                / "data/research/strategy_families/family_b/v1/"
                "development_evaluation/mom_b_002/development_result_v1.json"
            ),
        }
        command_02_registry = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/"
            "development_evaluation/comparison/development_registry_v1.json"
        )
        attribution_manifest = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/attribution_audit/"
            "manifests/family_b_attribution_audit_result_v1.json"
        )
        attribution_summary = _read_json(
            root / "data/reports/family_b_attribution_v1_summary.json"
        )
        history_readiness = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/history_remediation/"
            "manifests/family_b_sma_readiness_v1.json"
        )
        history_manifest = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/history_remediation/"
            "manifests/history_remediation_manifest_v1.json"
        )
        clean_control = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/clean_reevaluation/"
            "control/clean_control_result_v1.json"
        )
        clean_b002 = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/clean_reevaluation/"
            "b002/clean_b002_result_v1.json"
        )
        clean_reevaluation = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/clean_reevaluation/"
            "manifests/b002_clean_reevaluation_v1.json"
        )
        clean_run_manifest = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/clean_reevaluation/"
            "manifests/run_manifest_v1.json"
        )
        clean_summary = _read_json(
            root / "data/reports/family_b_b002_clean_v1_summary.json"
        )
        family_a_manifest = _read_json(
            root
            / "data/research/strategy_families/family_a/v1/closure/manifest/"
            "family_a_closure_manifest_v1.json"
        )

        command_02_hashes_clean = all(
            _require_hash(
                command_02_results[record_id],
                "development_result_hash",
                expected_hash,
            )
            for record_id, expected_hash in EXPECTED_RESULT_HASHES.items()
        )
        clean_artifact_mismatches = [
            relative_path
            for relative_path, expected_hash in clean_run_manifest[
                "artifact_hashes"
            ].items()
            if not (root / relative_path).is_file()
            or file_sha256(root / relative_path) != expected_hash
        ]
        checks = {
            "family_b_config_hash": clean_gate["snapshot"]["family_b_config_hash"]
            == EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": clean_gate["snapshot"][
                "success_criteria_hash"
            ]
            == EXPECTED_SUCCESS_CRITERIA_HASH,
            "command_02_result_hashes": command_02_hashes_clean,
            "command_02_registry_hash": command_02_registry.get(
                "development_registry_hash"
            )
            == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "attribution_audit_hash": _require_hash(
                attribution_manifest,
                "family_b_attribution_audit_hash",
                EXPECTED_ATTRIBUTION_AUDIT_HASH,
            ),
            "B001_distinct_filter_evidence": attribution_summary["B001"][
                "candidate_count"
            ]
            == 302
            and attribution_summary["B001"]["filter_removed_count"] == 0
            and attribution_summary["B001"]["B001_DISTINCT_FILTER_EVIDENCE"]
            == "NONE",
            "B002_original_attribution": attribution_summary["B002"][
                "B002_TREND_FILTER_EVIDENCE"
            ]
            == "CONFOUNDED_BY_HISTORY_AVAILABILITY"
            and attribution_summary["B002"][
                "B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"
            ]
            == "PRIMARILY_HISTORY_AVAILABILITY",
            "history_config_hash": history_manifest.get(
                "history_remediation_config_hash"
            )
            == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
            "raw_extension_hash": history_manifest.get("raw_extension_hash")
            == EXPECTED_RAW_EXTENSION_HASH,
            "adjusted_extension_hash": history_manifest.get(
                "adjusted_extension_hash"
            )
            == EXPECTED_ADJUSTED_EXTENSION_HASH,
            "SMA_readiness_hash": _require_hash(
                history_readiness,
                "family_b_sma_readiness_hash",
                EXPECTED_FAMILY_B_SMA_READINESS_HASH,
            ),
            "remediation_manifest_hash": _require_hash(
                history_manifest,
                "history_remediation_manifest_hash",
                EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
            ),
            "clean_control_result_hash": _require_hash(
                clean_control,
                "clean_control_result_hash",
                EXPECTED_CLEAN_CONTROL_RESULT_HASH,
            ),
            "clean_B002_result_hash": _require_hash(
                clean_b002,
                "clean_b002_result_hash",
                EXPECTED_CLEAN_B002_RESULT_HASH,
            ),
            "clean_reevaluation_hash": _require_hash(
                clean_reevaluation,
                "b002_clean_reevaluation_hash",
                EXPECTED_B002_CLEAN_REEVALUATION_HASH,
            ),
            "clean_run_manifest_hash": _require_hash(
                clean_run_manifest,
                "clean_run_manifest_hash",
                EXPECTED_CLEAN_RUN_MANIFEST_HASH,
            )
            and not clean_artifact_mismatches,
            "clean_B002_classifications": clean_b002[
                "MOM_B_002_CLEAN_REEVALUATION_RESULT"
            ]
            == "SUPPORTED"
            and clean_b002["B002_CLEAN_TREND_FILTER_EVIDENCE"] == "WEAK"
            and clean_b002["B002_CLEAN_DEVELOPMENT_ATTRIBUTION"]
            == "EVIDENCE_TOO_SPARSE",
            "clean_reevaluation_ready": clean_summary["verification"][
                "ready_for_review"
            ]
            is True
            and clean_summary["decisions"]["B002_VALIDATION_DESIGN_READINESS"]
            == "MORE_DEVELOPMENT_EVIDENCE_REQUIRED",
            "family_a_closure_hash": _require_hash(
                family_a_manifest,
                "family_a_closure_hash",
                EXPECTED_FAMILY_A_CLOSURE_HASH,
            ),
            "validation_not_accessed": clean_summary["governance"][
                "validation_accessed"
            ]
            is False,
        }
        if not all(checks.values()):
            failed = {key: value for key, value in checks.items() if not value}
            raise ValueError(failed)
        return {
            "status": "VERIFIED",
            "checks": checks,
            "clean_gate": clean_gate,
            "command_02_results": command_02_results,
            "command_02_registry": command_02_registry,
            "attribution_manifest": attribution_manifest,
            "attribution_summary": attribution_summary,
            "history_readiness": history_readiness,
            "history_manifest": history_manifest,
            "clean_control": clean_control,
            "clean_b002": clean_b002,
            "clean_reevaluation": clean_reevaluation,
            "clean_run_manifest": clean_run_manifest,
            "clean_summary": clean_summary,
            "family_a_manifest": family_a_manifest,
        }
    except FamilyBClosureInputMismatch:
        raise
    except Exception as error:  # noqa: BLE001 - normalize the closure gate
        raise FamilyBClosureInputMismatch(
            f"FAMILY_B_CLOSURE_INPUT_MISMATCH: {error}"
        ) from error


def family_b_baseline_snapshot(root: Path) -> dict[str, Any]:
    inputs = verify_family_b_closure_inputs(root)
    project = frozen_project_snapshot(root)
    family_a = family_a_closure_snapshot(root)
    semantic = {
        "strategy_v1_foundation_hash": project["foundation_hash"],
        "cap4_validation_state": project["cap4_validation_state"],
        "cap4_validation_run_count": project["cap4_validation_run_count"],
        "cap4_validation_result_hash": project["cap4_validation_result_hash"],
        "family_a_closure_snapshot_hash": family_a["snapshot_hash"],
        "family_a_closure_hash": EXPECTED_FAMILY_A_CLOSURE_HASH,
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
        "development_result_hashes": EXPECTED_RESULT_HASHES,
        "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "attribution_audit_hash": EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "history_remediation_hashes": {
            "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
            "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
            "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
            "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
            "history_remediation_manifest_hash": EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
        },
        "clean_reevaluation_hashes": {
            "clean_control_result_hash": EXPECTED_CLEAN_CONTROL_RESULT_HASH,
            "clean_b002_result_hash": EXPECTED_CLEAN_B002_RESULT_HASH,
            "b002_clean_reevaluation_hash": EXPECTED_B002_CLEAN_REEVALUATION_HASH,
            "clean_run_manifest_hash": EXPECTED_CLEAN_RUN_MANIFEST_HASH,
        },
        "daily_history_version": DATA_VERSION,
        "validation_accessed": False,
        "verified_input_count": len(inputs["checks"]),
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def research_lesson() -> dict[str, Any]:
    body = {
        "lesson_id": RESEARCH_LESSON_ID,
        "family_id": FAMILY_VERSION,
        "development_finding": (
            "Top-decile 6M relative momentum strongly overlapped with the two "
            "tested simple absolute-momentum definitions."
        ),
        "interpretation": (
            "The tested absolute filters provided little independent discrimination: "
            "B001 removed zero candidates and clean B002 produced one genuine "
            "below-SMA200 exclusion among 302 candidates."
        ),
        "scope_limit": (
            "This evidence applies only to MOM-B-001 and MOM-B-002 as frozen; it "
            "must not be generalized to all absolute-momentum methods."
        ),
        "generalization_to_all_absolute_momentum_prohibited": True,
    }
    return {**body, "research_lesson_hash": canonical_hash(body)}


def family_c_planning_note() -> dict[str, Any]:
    body = {
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "NEXT_PLANNED",
        "high_level_concept": [
            "CONSOLIDATION_OR_COMPRESSION",
            "BREAKOUT",
            "CONFIRMATION_OR_CONTINUATION",
            "CONTROLLED_HOLDING",
        ],
        "parameters_defined": False,
        "numeric_thresholds_defined": False,
        "experiments_registered": 0,
        "implementation_started": False,
        "performance_run": False,
        "validation_accessed": False,
        "authorized_to_start": False,
        "preregistration_requirement": (
            "Any future Family C experiment must preregister exact parameters and "
            "numeric success criteria before performance evaluation."
        ),
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
    }
    return {**body, "planning_note_hash": canonical_hash(body)}


def governance_record() -> dict[str, Any]:
    return {
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        "policy_remains_active": True,
        "family_b_incremental_parameter_tuning_authorized": False,
        "prohibited_without_independently_justified_new_hypothesis": list(
            PROHIBITED_INCREMENTAL_TUNING
        ),
        "performance_recomputed": False,
        "new_performance_experiments": 0,
        "alternate_MA_tested": False,
        "alternate_absolute_threshold_tested": False,
        "B003_created": False,
        "combined_filter_tested": False,
        "validation_accessed": False,
        "validation_rows_loaded": 0,
        "strategy_v2_created": False,
        "family_c_implementation_started": False,
        "family_c_parameters_defined": False,
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "database_writes": 0,
        "network_calls": 0,
        "secrets_written": 0,
    }


def closure_manifest_body(
    inputs: Mapping[str, Any], closure_timestamp: str
) -> dict[str, Any]:
    lesson = research_lesson()
    return {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_VERSION,
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "control_id": CONTROL_ID,
            "development_result_hash": EXPECTED_RESULT_HASHES[CONTROL_ID],
            "clean_control_result_hash": EXPECTED_CLEAN_CONTROL_RESULT_HASH,
            "role": "FROZEN_REFERENCE_CONTROL",
        },
        "B001": {
            **EXPECTED_EXPERIMENT_HASHES["MOM-B-001"],
            "development_result_hash": EXPECTED_RESULT_HASHES["MOM-B-001"],
            "development_result": inputs["command_02_results"]["MOM-B-001"][
                "classification"
            ],
            "candidate_count": 302,
            "filter_pass_count": 302,
            "filter_removed_count": 0,
            "distinct_filter_evidence": "NONE",
            "final_status": MOM_B_001_FINAL_STATUS,
            "final_reason": "6M >0 provided zero distinct candidate filtering.",
        },
        "B002_original": {
            **EXPECTED_EXPERIMENT_HASHES["MOM-B-002"],
            "development_result_hash": EXPECTED_RESULT_HASHES["MOM-B-002"],
            "development_result": inputs["command_02_results"]["MOM-B-002"][
                "classification"
            ],
            "trend_filter_evidence": "CONFOUNDED_BY_HISTORY_AVAILABILITY",
            "development_advantage_attribution": "PRIMARILY_HISTORY_AVAILABILITY",
        },
        "attribution_audit_hash": EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "history_remediation": {
            "data_version": DATA_VERSION,
            "preservation_status": "PRESERVED_SHARED_RESEARCH_INFRASTRUCTURE",
            "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
            "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
            "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
            "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
            "history_remediation_manifest_hash": EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
        },
        "B002_clean": {
            "clean_control_result_hash": EXPECTED_CLEAN_CONTROL_RESULT_HASH,
            "clean_b002_result_hash": EXPECTED_CLEAN_B002_RESULT_HASH,
            "b002_clean_reevaluation_hash": EXPECTED_B002_CLEAN_REEVALUATION_HASH,
            "clean_run_manifest_hash": EXPECTED_CLEAN_RUN_MANIFEST_HASH,
            "clean_result": "SUPPORTED",
            "trend_filter_evidence": "WEAK",
            "development_attribution": "EVIDENCE_TOO_SPARSE",
            "validation_design_readiness": "MORE_DEVELOPMENT_EVIDENCE_REQUIRED",
            "true_below_SMA200_removals": 1,
            "top_decile_candidates": 302,
            "final_status": MOM_B_002_FINAL_STATUS,
            "final_reason": (
                "Clean SMA200 evaluation preserved overall strategy behavior but "
                "only one genuine trend-filter exclusion occurred."
            ),
        },
        "family_decisions": {
            "FAMILY_B_RESEARCH_STATUS": FAMILY_B_RESEARCH_STATUS,
            "FAMILY_B_EVIDENCE_STATUS": FAMILY_B_EVIDENCE_STATUS,
            "MOM_B_001_FINAL_STATUS": MOM_B_001_FINAL_STATUS,
            "MOM_B_002_FINAL_STATUS": MOM_B_002_FINAL_STATUS,
            "FAMILY_B_VALIDATION_STATUS": FAMILY_B_VALIDATION_STATUS,
            "FAMILY_B_STRATEGY_V2_STATUS": FAMILY_B_STRATEGY_V2_STATUS,
        },
        "research_lesson": lesson,
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        "parameter_tuning": {
            "continues": False,
            "prohibited_without_new_independent_hypothesis": list(
                PROHIBITED_INCREMENTAL_TUNING
            ),
        },
        "next_planned_research_family": NEXT_PLANNED_RESEARCH_FAMILY,
        "performance_recomputed": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "family_c_implemented": False,
        "closure_timestamp": closure_timestamp,
        "immutability": "APPEND_A_NEW_GOVERNED_VERSION_FOR_ANY_FUTURE_CHANGE",
    }


def _write_immutable_manifest(
    path: Path, body: Mapping[str, Any]
) -> dict[str, Any]:
    observed_hash = canonical_hash(body)
    document = {**body, "family_b_closure_hash": observed_hash}
    if (
        EXPECTED_FAMILY_B_CLOSURE_HASH
        and observed_hash != EXPECTED_FAMILY_B_CLOSURE_HASH
    ):
        raise FamilyBClosureImmutabilityError(
            f"family_b_closure_hash mismatch: {observed_hash}"
        )
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(document):
            raise FamilyBClosureImmutabilityError(
                "Family B closure manifest is immutable; append a new version"
            )
        return existing
    write_json(path, document)
    return json_ready(document)


def _verify_roadmap(root: Path) -> bool:
    roadmap = (root / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    required = (
        "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |",
        "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family C | Breakout Continuation | NEXT_PLANNED |",
    )
    return all(marker in roadmap for marker in required) and all(
        f"| Family {family} |" in roadmap
        and "PLANNED_NOT_STARTED"
        in next(
            line
            for line in roadmap.splitlines()
            if line.startswith(f"| Family {family} |")
        )
        for family in "DEFG"
    )


def _write_artifact_manifest(
    root: Path, root_out: Path, closure_hash: str
) -> dict[str, Any]:
    reports_root = root / "data/reports"
    artifact_paths = [
        root_out / "manifest/family_b_closure_manifest_v1.json",
        root_out / "governance/family_b_final_decisions_v1.json",
        root_out / "governance/family_b_research_lesson_v1.json",
        root_out / "handoff/family_c_planning_note_v1.json",
        *(reports_root / name for name in REPORT_NAMES[1:]),
        root / "docs/strategy-family-b-closure-v1.md",
        root / "docs/strategy-family-research-roadmap-v1.md",
    ]
    body = {
        "family_b_closure_hash": closure_hash,
        "artifact_hashes": {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in artifact_paths
            if path.is_file()
        },
    }
    document = {**body, "closure_artifact_manifest_hash": canonical_hash(body)}
    write_json(root_out / "manifest/closure_artifact_hashes_v1.json", document)
    return json_ready(document)


def build_family_b_research_closure(root: Path) -> dict[str, Any]:
    inputs = verify_family_b_closure_inputs(root)
    baseline_before = family_b_baseline_snapshot(root)
    if not _verify_roadmap(root):
        raise FamilyBClosureInputMismatch(
            "FAMILY_B_CLOSURE_INPUT_MISMATCH: roadmap closure state missing"
        )

    root_out = output_root(root)
    reports_root = root / "data/reports"
    manifest_path = root_out / "manifest/family_b_closure_manifest_v1.json"
    closure_timestamp = (
        _read_json(manifest_path)["closure_timestamp"]
        if manifest_path.exists()
        else utc_now()
    )
    lesson = research_lesson()
    handoff = family_c_planning_note()
    governance = governance_record()
    decisions = {
        "FAMILY_B_RESEARCH_STATUS": FAMILY_B_RESEARCH_STATUS,
        "FAMILY_B_EVIDENCE_STATUS": FAMILY_B_EVIDENCE_STATUS,
        "MOM_B_001_FINAL_STATUS": MOM_B_001_FINAL_STATUS,
        "MOM_B_001_FINAL_REASON": "6M >0 provided zero distinct candidate filtering.",
        "MOM_B_002_FINAL_STATUS": MOM_B_002_FINAL_STATUS,
        "MOM_B_002_FINAL_REASON": (
            "Clean SMA200 evaluation preserved overall strategy behavior but only "
            "one genuine trend-filter exclusion occurred."
        ),
        "FAMILY_B_VALIDATION_STATUS": FAMILY_B_VALIDATION_STATUS,
        "FAMILY_B_STRATEGY_V2_STATUS": FAMILY_B_STRATEGY_V2_STATUS,
    }

    write_json(root_out / "governance/family_b_final_decisions_v1.json", decisions)
    write_json(root_out / "governance/family_b_research_lesson_v1.json", lesson)
    write_json(root_out / "handoff/family_c_planning_note_v1.json", handoff)
    manifest = _write_immutable_manifest(
        manifest_path, closure_manifest_body(inputs, closure_timestamp)
    )

    evidence_rows = [
        {
            "evidence_id": CONTROL_ID,
            "stage": "FROZEN_CONTROL",
            "parameter_hash": "",
            "preregistration_hash": "",
            "result_hash": EXPECTED_RESULT_HASHES[CONTROL_ID],
            "candidate_count": "",
            "filter_removed_count": "",
            "development_result": "REFERENCE_CONTROL",
            "distinct_evidence": "REFERENCE_ONLY",
            "final_status": "FROZEN_REFERENCE_CONTROL",
            "reason": "Read-only relative-momentum comparison architecture.",
        },
        {
            "evidence_id": "MOM-B-001",
            "stage": "FINAL",
            **EXPECTED_EXPERIMENT_HASHES["MOM-B-001"],
            "result_hash": EXPECTED_RESULT_HASHES["MOM-B-001"],
            "candidate_count": 302,
            "filter_removed_count": 0,
            "development_result": "SUPPORTED",
            "distinct_evidence": "NONE",
            "final_status": MOM_B_001_FINAL_STATUS,
            "reason": "6M >0 provided zero distinct candidate filtering.",
        },
        {
            "evidence_id": "MOM-B-002",
            "stage": "ORIGINAL_CONFOUNDED",
            **EXPECTED_EXPERIMENT_HASHES["MOM-B-002"],
            "result_hash": EXPECTED_RESULT_HASHES["MOM-B-002"],
            "candidate_count": 302,
            "filter_removed_count": 31,
            "development_result": "SUPPORTED",
            "distinct_evidence": "CONFOUNDED_BY_HISTORY_AVAILABILITY",
            "final_status": "SUPERSEDED_FOR_ATTRIBUTION_BY_CLEAN_REEVALUATION",
            "reason": "Apparent advantage was primarily history availability.",
        },
        {
            "evidence_id": "MOM-B-002-CLEAN-REEVALUATION",
            "stage": "FINAL_CLEAN",
            **EXPECTED_EXPERIMENT_HASHES["MOM-B-002"],
            "result_hash": EXPECTED_CLEAN_B002_RESULT_HASH,
            "candidate_count": 302,
            "filter_removed_count": 1,
            "development_result": "SUPPORTED",
            "distinct_evidence": "WEAK",
            "final_status": MOM_B_002_FINAL_STATUS,
            "reason": (
                "Only one genuine below-SMA200 exclusion remained after remediation."
            ),
        },
    ]
    lesson_rows = [
        {
            "lesson_id": lesson["lesson_id"],
            "development_finding": lesson["development_finding"],
            "interpretation": lesson["interpretation"],
            "scope_limit": lesson["scope_limit"],
            "generalization_prohibited": lesson[
                "generalization_to_all_absolute_momentum_prohibited"
            ],
            "research_lesson_hash": lesson["research_lesson_hash"],
        }
    ]
    write_csv(reports_root / REPORT_NAMES[1], evidence_rows)
    write_csv(reports_root / REPORT_NAMES[2], lesson_rows)
    write_csv(reports_root / REPORT_NAMES[3], [handoff])

    baseline_after = family_b_baseline_snapshot(root)
    baseline_unchanged = baseline_before == baseline_after
    artifact_manifest = _write_artifact_manifest(
        root, root_out, manifest["family_b_closure_hash"]
    )
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_VERSION,
        "closure": manifest,
        "statuses": decisions,
        "research_lesson": lesson,
        "daily_history_preservation": {
            "data_version": DATA_VERSION,
            "status": "PRESERVED_SHARED_RESEARCH_INFRASTRUCTURE",
            "family_b_only_disposable": False,
            "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
            "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
        },
        "governance": governance,
        "family_c_handoff": handoff,
        "input_verification": {"status": "VERIFIED", "checks": inputs["checks"]},
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_unchanged": baseline_unchanged,
            "strategy_v1": "UNCHANGED",
            "CAP4": "UNCHANGED",
            "family_a_commands_01_05_and_closure": "UNCHANGED",
            "family_b_command_01": "UNCHANGED",
            "family_b_command_02": "UNCHANGED",
            "family_b_command_03": "UNCHANGED",
            "family_b_command_04": "UNCHANGED",
            "family_b_command_05": "UNCHANGED",
            "all_frozen_family_b_result_hashes": "UNCHANGED",
            "DAILY_HISTORY_PREHISTORY_V2": "UNCHANGED",
        },
        "storage": {
            "root": root_out.relative_to(root).as_posix(),
            "manifest": manifest_path.relative_to(root).as_posix(),
            "governance": (root_out / "governance").relative_to(root).as_posix(),
            "handoff": (root_out / "handoff").relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
            "closure_artifact_manifest_hash": artifact_manifest[
                "closure_artifact_manifest_hash"
            ],
        },
        "known_limitations": (
            "B001_TESTED_ONLY_THE_STRICT_6M_GREATER_THAN_ZERO_DEFINITION",
            "B002_CLEAN_SAMPLE_CONTAINED_ONLY_ONE_TRUE_BELOW_SMA200_EXCLUSION",
            "SEVEN_LEGITIMATE_SMA_UNAVAILABLE_CANDIDATE_ROWS_REMAINED",
            "DEVELOPMENT_EVIDENCE_IS_NOT_VALIDATION_EVIDENCE",
            "THE_CLOSURE_DOES_NOT_GENERALIZE_TO_ALL_ABSOLUTE_MOMENTUM_METHODS",
        ),
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    return summary


def finalize_family_b_research_closure(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    if not summary_path.is_file():
        raise FileNotFoundError("Create the Family B closure before finalizing")
    summary = _read_json(summary_path)
    inputs = verify_family_b_closure_inputs(root)
    baseline = family_b_baseline_snapshot(root)
    manifest = _read_json(
        output_root(root) / "manifest/family_b_closure_manifest_v1.json"
    )
    if not _require_hash(
        manifest, "family_b_closure_hash", EXPECTED_FAMILY_B_CLOSURE_HASH
    ):
        raise FamilyBClosureImmutabilityError("Family B closure hash mismatch")
    artifact_manifest = _read_json(
        output_root(root) / "manifest/closure_artifact_hashes_v1.json"
    )
    artifact_body = {
        key: value
        for key, value in artifact_manifest.items()
        if key != "closure_artifact_manifest_hash"
    }
    artifact_mismatches = [
        relative_path
        for relative_path, expected_hash in artifact_manifest[
            "artifact_hashes"
        ].items()
        if not (root / relative_path).is_file()
        or file_sha256(root / relative_path) != expected_hash
    ]
    if (
        canonical_hash(artifact_body)
        != artifact_manifest["closure_artifact_manifest_hash"]
        or artifact_mismatches
    ):
        raise FamilyBClosureImmutabilityError(
            f"Family B closure artifact mismatch: {artifact_mismatches}"
        )
    governance = summary["governance"]
    ready = (
        inputs["status"] == "VERIFIED"
        and backend_tests == "PASSED"
        and frontend_build == "PASSED"
        and baseline["snapshot_hash"] == summary["regression"]["after_snapshot_hash"]
        and summary["regression"]["baseline_unchanged"] is True
        and governance["performance_recomputed"] is False
        and governance["new_performance_experiments"] == 0
        and governance["alternate_MA_tested"] is False
        and governance["B003_created"] is False
        and governance["validation_accessed"] is False
        and governance["strategy_v2_created"] is False
        and governance["family_c_implementation_started"] is False
        and _verify_roadmap(root)
    )
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": ready,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_FAMILY_B_CLOSURE_HASH",
    "FAMILY_B_EVIDENCE_STATUS",
    "FAMILY_B_RESEARCH_STATUS",
    "FAMILY_B_STRATEGY_V2_STATUS",
    "FAMILY_B_VALIDATION_STATUS",
    "GOVERNANCE_POLICY_VERSION",
    "MOM_B_001_FINAL_STATUS",
    "MOM_B_002_FINAL_STATUS",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "PROHIBITED_INCREMENTAL_TUNING",
    "REPORT_NAMES",
    "RESEARCH_LESSON_ID",
    "FamilyBClosureImmutabilityError",
    "FamilyBClosureInputMismatch",
    "build_family_b_research_closure",
    "closure_manifest_body",
    "family_b_baseline_snapshot",
    "family_c_planning_note",
    "finalize_family_b_research_closure",
    "governance_record",
    "output_root",
    "research_lesson",
    "verify_family_b_closure_inputs",
)
