from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_development_backtest import (
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_CONFIG_HASH,
    verify_family_a_preregistration,
)
from app.research.strategy.family_a_momentum import (
    FAMILY_VERSION,
    file_sha256,
    frozen_project_snapshot,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_development_evaluation import (
    COMMAND_VERSION as COMMAND_04_VERSION,
    EXPECTED_RESULT_HASHES,
)
from app.research.strategy.family_a_phase2_research import (
    A2_001,
    A2_002,
    EXPECTED_COMMAND_02_REGISTRY_HASH,
    EXPECTED_COMMAND_02_RESULT_HASHES,
    EXPECTED_PHASE2_CONFIG_HASH,
    EXPECTED_PHASE2_EXPERIMENT_HASHES,
    EXPECTED_PHASE2_REGISTRY_HASH,
    REFERENCE_EXPERIMENT_ID,
    verify_command_02_results,
)


COMMAND_VERSION = "FAMILY_A_PHASE2_CLOSURE_V1"
COMMAND_PROFILE = "FAMILY_A_RESEARCH_FREEZE_AND_GOVERNANCE_V1"
COMMAND = "Step 03.01 / Command 05"
FAMILY_A_RESEARCH_STATUS = "PAUSED_PENDING_LATER_VALIDATION_DESIGN"
FAMILY_A_EVIDENCE_STATUS = "PROMISING_DEVELOPMENT_EVIDENCE_NOT_VALIDATED"
FAMILY_A_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_A_STRATEGY_V2_STATUS = "NOT_CREATED"
A2_001_RESEARCH_STATUS = "CLOSED_NOT_ADVANCED"
A2_002_RESEARCH_STATUS = "SUPPORTED_IMPLEMENTATION_EVIDENCE"
RETENTION_BAND_CONCEPT_STATUS = "DEPRIORITIZED_FOR_CURRENT_FAMILY_A_VERSION"
PRACTICAL_CAPITAL_REFERENCE = 500_000
SMALL_CAPITAL_REFERENCE = 100_000
PRIMARY_ARCHITECTURE_REFERENCE = REFERENCE_EXPERIMENT_ID
GOVERNANCE_FINDING_ID = "GOVERNANCE_FINDING_NUMERIC_THRESHOLDS_V1"
GOVERNANCE_POLICY_VERSION = "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_B_RELATIVE_PLUS_ABSOLUTE_MOMENTUM"
EXPECTED_CLOSURE_HASH = "51e2190c25f3146609ac173cc345e2a8adc0b6c9efb824633d735dc976581250"

REPORT_NAMES = (
    "family_a_closure_v1_summary.json",
    "family_a_closure_v1_evidence.csv",
    "family_a_closure_v1_governance.csv",
    "family_a_closure_v1_handoff.csv",
)

PREREGISTRATION_CHECKLIST = (
    "hypothesis",
    "experiment_id",
    "population",
    "exact_parameters",
    "comparison_control",
    "primary_metrics",
    "secondary_metrics",
    "numerical_success_criteria_where_applicable",
    "failure_criteria",
    "stop_conditions",
    "validation_eligibility_rule",
    "cost_model",
    "data_partition",
    "hashes",
)


class FamilyAClosureInputMismatch(RuntimeError):
    pass


class FamilyAClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recompute_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def verify_closure_inputs(root: Path) -> dict[str, Any]:
    try:
        command_01 = verify_family_a_preregistration(root)
        command_02 = verify_command_02_results(root)
        phase2_config = _read_json(
            root / "data/research/strategy_families/family_a/v1/phase2/registry/phase2_config_v1.json"
        )
        phase2_registry = _read_json(
            root
            / "data/research/strategy_families/family_a/v1/phase2/registry/phase2_experiment_registry_v1.json"
        )
        command_03_summary = _read_json(root / "data/reports/family_a_phase2_v1_summary.json")
        command_04_summary = _read_json(root / "data/reports/family_a_phase2_dev_v1_summary.json")
        command_04_registry = _read_json(
            root
            / "data/research/strategy_families/family_a/v1/phase2/development_evaluation"
            / "comparison/phase2_development_registry_v1.json"
        )
        result_paths = {
            A2_001: root
            / "data/research/strategy_families/family_a/v1/phase2/development_evaluation"
            / "a2_001/development_result_v1.json",
            A2_002: root
            / "data/research/strategy_families/family_a/v1/phase2/development_evaluation"
            / "a2_002/development_result_v1.json",
        }
        results = {experiment_id: _read_json(path) for experiment_id, path in result_paths.items()}
        checks = {
            "command_01_family_hash": command_01["family_config_hash"] == EXPECTED_FAMILY_CONFIG_HASH,
            "command_01_experiment_hashes": all(
                row["parameter_hash"] == EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]["parameter_hash"]
                and row["preregistration_hash"]
                == EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]["preregistration_hash"]
                for row in command_01["experiments"]
            ),
            "command_02_registry_hash": command_02["registry"]["development_registry_hash"]
            == EXPECTED_COMMAND_02_REGISTRY_HASH,
            "command_02_result_hashes": all(
                command_02["summary"]["experiments"][experiment_id]["baseline_result_hash"] == expected
                for experiment_id, expected in EXPECTED_COMMAND_02_RESULT_HASHES.items()
            ),
            "command_03_config_hash": phase2_config["phase2_config_hash"] == EXPECTED_PHASE2_CONFIG_HASH
            and _recompute_hash(phase2_config, "phase2_config_hash") == EXPECTED_PHASE2_CONFIG_HASH,
            "command_03_registry_hash": phase2_registry["phase2_registry_hash"] == EXPECTED_PHASE2_REGISTRY_HASH
            and _recompute_hash(phase2_registry, "phase2_registry_hash") == EXPECTED_PHASE2_REGISTRY_HASH,
            "command_03_ready": command_03_summary["verification"]["ready_for_review"] is True,
            "command_04_version": command_04_summary["command_version"] == COMMAND_04_VERSION,
            "command_04_ready": command_04_summary["verification"]["ready_for_review"] is True,
            "command_04_phase2_result": command_04_summary["classifications"]["FAMILY_A_PHASE2_RESULT"]
            == "PARTIAL_SUPPORT",
            "command_04_no_validation": command_04_summary["governance"]["validation_accessed"] is False,
            "command_04_registry": command_04_registry["experiment_count"] == 2
            and all(row["status"] == "DEVELOPMENT_EVALUATED" for row in command_04_registry["experiments"]),
            "A2-001_result_hash": results[A2_001]["development_result_hash"] == EXPECTED_RESULT_HASHES[A2_001]
            and _recompute_hash(results[A2_001], "development_result_hash") == EXPECTED_RESULT_HASHES[A2_001],
            "A2-002_result_hash": results[A2_002]["development_result_hash"] == EXPECTED_RESULT_HASHES[A2_002]
            and _recompute_hash(results[A2_002], "development_result_hash") == EXPECTED_RESULT_HASHES[A2_002],
            "A2-001_result": results[A2_001]["classifications"]["A2_001_DEVELOPMENT_RESULT"]
            == "PARTIALLY_SUPPORTED",
            "A2-002_result": results[A2_002]["classifications"]["A2_002_DEVELOPMENT_RESULT"]
            == "SUPPORTED",
        }
        if not all(checks.values()):
            raise ValueError(checks)
        return {
            "status": "VERIFIED",
            "checks": checks,
            "command_01": command_01,
            "command_02": command_02,
            "phase2_config": phase2_config,
            "phase2_registry": phase2_registry,
            "command_03_summary": command_03_summary,
            "command_04_summary": command_04_summary,
            "command_04_registry": command_04_registry,
            "results": results,
        }
    except (FileNotFoundError, KeyError, StopIteration, TypeError, ValueError) as error:
        raise FamilyAClosureInputMismatch(f"FAMILY_A_CLOSURE_INPUT_MISMATCH: {error}") from error


def closure_baseline_snapshot(root: Path) -> dict[str, Any]:
    inputs = verify_closure_inputs(root)
    project = frozen_project_snapshot(root)
    semantic = {
        "strategy_v1_foundation_hash": project["foundation_hash"],
        "cap4_validation_state": project["cap4_validation_state"],
        "cap4_validation_run_count": project["cap4_validation_run_count"],
        "cap4_validation_result_hash": project["cap4_validation_result_hash"],
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "command_01_registry_hash": inputs["command_01"]["source_registry_hash"],
        "command_01_experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
        "command_02_registry_hash": EXPECTED_COMMAND_02_REGISTRY_HASH,
        "command_02_result_hashes": EXPECTED_COMMAND_02_RESULT_HASHES,
        "command_03_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "command_03_registry_hash": EXPECTED_PHASE2_REGISTRY_HASH,
        "command_03_experiment_hashes": EXPECTED_PHASE2_EXPERIMENT_HASHES,
        "command_04_result_hashes": EXPECTED_RESULT_HASHES,
        "validation_accessed": False,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def governance_policy() -> dict[str, Any]:
    body = {
        "policy_version": GOVERNANCE_POLICY_VERSION,
        "effective_scope": "PROSPECTIVE_CONTROLLED_RESEARCH_EXPERIMENTS",
        "historical_experiment_records_rewritten": False,
        "numeric_threshold_rule": {
            "required": (
                "Freeze exact numerical success and failure thresholds before performance evaluation whenever feasible."
            ),
            "missing_threshold_treatment": (
                "Post-hoc classifications must be explicitly labeled DESCRIPTIVE_NOT_PREREGISTERED."
            ),
            "evidence_precedence": "IMMUTABLE_RAW_METRICS_TAKE_PRECEDENCE_OVER_LABELS",
        },
        "required_preregistration_checklist": list(PREREGISTRATION_CHECKLIST),
    }
    return {**body, "governance_policy_hash": canonical_hash(body)}


def closure_manifest_body(inputs: Mapping[str, Any], closure_timestamp: str) -> dict[str, Any]:
    return {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "baseline_experiment_ids": ["MOM-A-001", "MOM-A-002", "MOM-A-003"],
        "baseline_result_hashes": EXPECTED_COMMAND_02_RESULT_HASHES,
        "phase2_experiment_ids": [A2_001, A2_002],
        "phase2_preregistration_hashes": {
            experiment_id: values["preregistration_hash"]
            for experiment_id, values in EXPECTED_PHASE2_EXPERIMENT_HASHES.items()
        },
        "phase2_result_hashes": EXPECTED_RESULT_HASHES,
        "decisions": {
            "A2_001_RESEARCH_STATUS": A2_001_RESEARCH_STATUS,
            "A2_001_REASON": (
                "Minor turnover and cost reduction did not offset the observed modest performance degradation; no retuning."
            ),
            "RETENTION_BAND_CONCEPT_STATUS": RETENTION_BAND_CONCEPT_STATUS,
            "A2_002_RESEARCH_STATUS": A2_002_RESEARCH_STATUS,
            "FAMILY_A_PRACTICAL_RESEARCH_CAPITAL_REFERENCE_V1_INR": PRACTICAL_CAPITAL_REFERENCE,
            "SMALL_CAPITAL_REFERENCE_INR": SMALL_CAPITAL_REFERENCE,
            "PRIMARY_ARCHITECTURE_REFERENCE": PRIMARY_ARCHITECTURE_REFERENCE,
            "primary_reference_role": "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL",
        },
        "family_status": {
            "FAMILY_A_RESEARCH_STATUS": FAMILY_A_RESEARCH_STATUS,
            "FAMILY_A_EVIDENCE_STATUS": FAMILY_A_EVIDENCE_STATUS,
            "FAMILY_A_VALIDATION_STATUS": FAMILY_A_VALIDATION_STATUS,
            "FAMILY_A_STRATEGY_V2_STATUS": FAMILY_A_STRATEGY_V2_STATUS,
        },
        "governance_finding": GOVERNANCE_FINDING_ID,
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        "capital_reference_interpretation": {
            "purpose": "IMPLEMENTATION_FIDELITY_REFERENCE_FOR_20_TO_35_HOLDING_WHOLE_SHARE_RESEARCH",
            "alpha_parameter": False,
            "profitability_threshold": False,
            "live_capital_recommendation": False,
            "proof_larger_capital_always_performs_better": False,
        },
        "family_b_handoff": {
            "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
            "status": "PLANNING_NOTE_ONLY_NOT_AUTHORIZED",
            "implemented": False,
        },
        "family_a_resume_conditions": (
            "FORMAL_VALIDATION_DESIGN",
            "GENUINELY_NEW_HYPOTHESIS",
            "MULTI_STRATEGY_ARCHITECTURE_INTEGRATION",
        ),
        "performance_recomputed": False,
        "new_strategy_metrics_created": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "closure_timestamp": closure_timestamp,
        "immutability": "APPEND_NEW_VERSION_OR_EXPERIMENT_FOR_FUTURE_WORK",
    }


def _write_immutable_manifest(path: Path, body: Mapping[str, Any], root: Path) -> dict[str, Any]:
    manifest = {**body, "family_a_closure_hash": canonical_hash(body)}
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(manifest):
            summary_path = root / "data/reports/family_a_closure_v1_summary.json"
            finalized = summary_path.exists() and _read_json(summary_path).get("verification", {}).get(
                "ready_for_review"
            ) is True
            if finalized:
                raise FamilyAClosureImmutabilityError(
                    "Family A closure is immutable; append a new version for future work"
                )
            write_json(path, manifest)
            return json_ready(manifest)
        return existing
    write_json(path, manifest)
    return json_ready(manifest)


def _write_closure_artifact_hashes(root: Path, output_root: Path, closure_hash: str) -> None:
    reports_root = root / "data/reports"
    artifact_paths = [
        *sorted(path for path in output_root.rglob("*") if path.is_file()),
        *(reports_root / name for name in REPORT_NAMES),
        root / "docs/strategy-family-a-phase2-closure-v1.md",
        root / "docs/strategy-family-research-roadmap-v1.md",
    ]
    write_json(
        output_root / "manifest/closure_artifact_hashes_v1.json",
        {
            "family_a_closure_hash": closure_hash,
            "artifact_hashes": {
                path.relative_to(root).as_posix(): file_sha256(path)
                for path in artifact_paths
                if path.exists() and path.name != "closure_artifact_hashes_v1.json"
            },
        },
    )


def build_family_a_phase2_closure(root: Path) -> dict[str, Any]:
    inputs = verify_closure_inputs(root)
    baseline_before = closure_baseline_snapshot(root)
    output_root = root / "data/research/strategy_families/family_a/v1/closure"
    reports_root = root / "data/reports"
    manifest_path = output_root / "manifest/family_a_closure_manifest_v1.json"
    closure_timestamp = (
        _read_json(manifest_path)["closure_timestamp"] if manifest_path.exists() else utc_now()
    )
    policy = governance_policy()
    finding = {
        "finding_id": GOVERNANCE_FINDING_ID,
        "source_command": COMMAND_04_VERSION,
        "finding": (
            "Command 03 froze qualitative labels but not exact numerical cutoffs before Command 04 performance evaluation."
        ),
        "classification_treatment": "COMMAND_04_LABELS_ARE_DESCRIPTIVE_NOT_PREREGISTERED",
        "raw_metric_precedence": True,
        "historical_records_rewritten": False,
        "prospective_policy": GOVERNANCE_POLICY_VERSION,
    }
    handoff = {
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "NEXT_PLANNED",
        "concept": (
            "Test whether strong cross-sectional momentum plus positive absolute momentum or trend improves robustness versus relative momentum alone."
        ),
        "parameters_defined": False,
        "experiments_registered": 0,
        "code_implemented": False,
        "backtest_run": False,
        "authorized_to_start": False,
    }
    write_json(output_root / "governance/governance_finding_numeric_thresholds_v1.json", finding)
    write_json(output_root / "governance/research_experiment_governance_v2.json", policy)
    write_json(
        output_root / "governance/preregistration_checklist_v2.json",
        {
            "policy_version": GOVERNANCE_POLICY_VERSION,
            "required_items": list(PREREGISTRATION_CHECKLIST),
            "item_count": len(PREREGISTRATION_CHECKLIST),
        },
    )
    write_json(output_root / "handoff/family_b_planning_note_v1.json", handoff)
    manifest = _write_immutable_manifest(
        manifest_path,
        closure_manifest_body(inputs, closure_timestamp),
        root,
    )
    if EXPECTED_CLOSURE_HASH is not None and manifest["family_a_closure_hash"] != EXPECTED_CLOSURE_HASH:
        raise FamilyAClosureImmutabilityError("Frozen Family A closure hash changed")

    registry_body = {
        "command_version": COMMAND_VERSION,
        "family_id": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "family_research_status": FAMILY_A_RESEARCH_STATUS,
        "family_evidence_status": FAMILY_A_EVIDENCE_STATUS,
        "validation_status": FAMILY_A_VALIDATION_STATUS,
        "strategy_v2_status": FAMILY_A_STRATEGY_V2_STATUS,
        "primary_architecture_reference": PRIMARY_ARCHITECTURE_REFERENCE,
        "primary_reference_role": "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL",
        "baseline_experiments": [
            {
                "experiment_id": experiment_id,
                "status": "PRESERVED_DEVELOPMENT_EVIDENCE",
                "parameter_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
                "preregistration_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["preregistration_hash"],
                "result_hash": EXPECTED_COMMAND_02_RESULT_HASHES[experiment_id],
            }
            for experiment_id in ("MOM-A-001", "MOM-A-002", "MOM-A-003")
        ],
        "phase2_experiments": [
            {
                "experiment_id": A2_001,
                "closure_status": A2_001_RESEARCH_STATUS,
                "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["parameter_hash"],
                "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["preregistration_hash"],
                "result_hash": EXPECTED_RESULT_HASHES[A2_001],
            },
            {
                "experiment_id": A2_002,
                "closure_status": A2_002_RESEARCH_STATUS,
                "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["parameter_hash"],
                "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["preregistration_hash"],
                "result_hash": EXPECTED_RESULT_HASHES[A2_002],
            },
        ],
        "family_a_closure_hash": manifest["family_a_closure_hash"],
        "immutable": True,
    }
    registry = {**registry_body, "closure_registry_hash": canonical_hash(registry_body)}
    registry_path = output_root / "manifest/family_a_closure_registry_v1.json"
    write_json(registry_path, registry)

    evidence_rows = [
        {
            "evidence_id": experiment_id,
            "evidence_type": "ORIGINAL_DEVELOPMENT_BASELINE",
            "status": "PRESERVED_DEVELOPMENT_EVIDENCE",
            "result_hash": EXPECTED_COMMAND_02_RESULT_HASHES[experiment_id],
            "decision": "NO_HISTORICAL_WINNER_LABEL",
        }
        for experiment_id in ("MOM-A-001", "MOM-A-002", "MOM-A-003")
    ]
    evidence_rows.extend(
        (
            {
                "evidence_id": A2_001,
                "evidence_type": "RETENTION_BAND",
                "status": A2_001_RESEARCH_STATUS,
                "result_hash": EXPECTED_RESULT_HASHES[A2_001],
                "decision": "DO_NOT_ADVANCE_OR_RETUNE",
            },
            {
                "evidence_id": A2_002,
                "evidence_type": "CAPITAL_FEASIBILITY",
                "status": A2_002_RESEARCH_STATUS,
                "result_hash": EXPECTED_RESULT_HASHES[A2_002],
                "decision": "RETAIN_500K_AS_IMPLEMENTATION_REFERENCE_NOT_ALPHA",
            },
        )
    )
    governance_rows = [
        {
            "policy_version": GOVERNANCE_POLICY_VERSION,
            "rule": "NUMERIC_THRESHOLDS_BEFORE_PERFORMANCE_WHEN_FEASIBLE",
            "required": True,
        },
        {
            "policy_version": GOVERNANCE_POLICY_VERSION,
            "rule": "POST_HOC_LABELS_DESCRIPTIVE_NOT_PREREGISTERED",
            "required": True,
        },
        {
            "policy_version": GOVERNANCE_POLICY_VERSION,
            "rule": "IMMUTABLE_RAW_METRICS_TAKE_PRECEDENCE",
            "required": True,
        },
        *(
            {
                "policy_version": GOVERNANCE_POLICY_VERSION,
                "rule": f"CHECKLIST:{item}",
                "required": True,
            }
            for item in PREREGISTRATION_CHECKLIST
        ),
    ]
    write_csv(reports_root / REPORT_NAMES[1], evidence_rows)
    write_csv(reports_root / REPORT_NAMES[2], governance_rows)
    write_csv(reports_root / REPORT_NAMES[3], [handoff])

    baseline_after = closure_baseline_snapshot(root)
    baseline_violations = 0 if baseline_before == baseline_after else 1
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "closure": manifest,
        "statuses": {
            "FAMILY_A_RESEARCH_STATUS": FAMILY_A_RESEARCH_STATUS,
            "FAMILY_A_EVIDENCE_STATUS": FAMILY_A_EVIDENCE_STATUS,
            "FAMILY_A_VALIDATION_STATUS": FAMILY_A_VALIDATION_STATUS,
            "FAMILY_A_STRATEGY_V2_STATUS": FAMILY_A_STRATEGY_V2_STATUS,
            "A2_001_RESEARCH_STATUS": A2_001_RESEARCH_STATUS,
            "RETENTION_BAND_CONCEPT_STATUS": RETENTION_BAND_CONCEPT_STATUS,
            "A2_002_RESEARCH_STATUS": A2_002_RESEARCH_STATUS,
        },
        "capital_references": {
            "FAMILY_A_PRACTICAL_RESEARCH_CAPITAL_REFERENCE_V1_INR": PRACTICAL_CAPITAL_REFERENCE,
            "SMALL_CAPITAL_REFERENCE_INR": SMALL_CAPITAL_REFERENCE,
            "interpretation": manifest["capital_reference_interpretation"],
        },
        "architecture_reference": {
            "PRIMARY_ARCHITECTURE_REFERENCE": PRIMARY_ARCHITECTURE_REFERENCE,
            "role": "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL",
            "reason": (
                "Phase 2 eligible, lower turnover than MOM-A-001, positive development behavior, quarterly simplicity, and supported 500k feasibility."
            ),
        },
        "governance": {
            "finding": finding,
            "policy": policy,
            "performance_recomputed": False,
            "new_performance_experiments": 0,
            "new_strategy_metrics_created": False,
            "retention_retuned": False,
            "alternate_capital_tested": False,
            "validation_accessed": False,
            "validation_rows_loaded": 0,
            "strategy_v2_created": False,
            "family_b_implemented": False,
        },
        "family_b_handoff": handoff,
        "input_verification": {"status": "VERIFIED", "checks": inputs["checks"]},
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_mutation_violations": baseline_violations,
            "family_a_command_01": "PASSED" if baseline_violations == 0 else "FAILED",
            "family_a_command_02": "PASSED" if baseline_violations == 0 else "FAILED",
            "family_a_command_03": "PASSED" if baseline_violations == 0 else "FAILED",
            "family_a_command_04": "PASSED" if baseline_violations == 0 else "FAILED",
            "cap4": "PASSED" if baseline_violations == 0 else "FAILED",
            "strategy_v1": "PASSED" if baseline_violations == 0 else "FAILED",
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "manifest": manifest_path.relative_to(root).as_posix(),
            "registry": registry_path.relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        },
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    _write_closure_artifact_hashes(root, output_root, manifest["family_a_closure_hash"])
    return summary


def finalize_family_a_closure(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    if not summary_path.exists():
        raise FileNotFoundError("Create the Family A closure before finalizing")
    summary = _read_json(summary_path)
    inputs = verify_closure_inputs(root)
    baseline = closure_baseline_snapshot(root)
    manifest = summary["closure"]
    if _recompute_hash(manifest, "family_a_closure_hash") != manifest["family_a_closure_hash"]:
        raise FamilyAClosureImmutabilityError("Family A closure hash mismatch")
    if EXPECTED_CLOSURE_HASH is None or manifest["family_a_closure_hash"] != EXPECTED_CLOSURE_HASH:
        raise FamilyAClosureImmutabilityError("Frozen expected closure hash mismatch")
    ready = (
        inputs["status"] == "VERIFIED"
        and backend_tests == "PASSED"
        and frontend_build == "PASSED"
        and baseline["snapshot_hash"] == summary["regression"]["after_snapshot_hash"]
        and summary["regression"]["baseline_mutation_violations"] == 0
        and summary["governance"]["performance_recomputed"] is False
        and summary["governance"]["validation_accessed"] is False
        and summary["governance"]["family_b_implemented"] is False
    )
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": ready,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    _write_closure_artifact_hashes(
        root,
        root / "data/research/strategy_families/family_a/v1/closure",
        manifest["family_a_closure_hash"],
    )
    return summary


__all__ = (
    "A2_001_RESEARCH_STATUS",
    "A2_002_RESEARCH_STATUS",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_CLOSURE_HASH",
    "FAMILY_A_EVIDENCE_STATUS",
    "FAMILY_A_RESEARCH_STATUS",
    "FAMILY_A_STRATEGY_V2_STATUS",
    "FAMILY_A_VALIDATION_STATUS",
    "GOVERNANCE_FINDING_ID",
    "GOVERNANCE_POLICY_VERSION",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "PRACTICAL_CAPITAL_REFERENCE",
    "PRIMARY_ARCHITECTURE_REFERENCE",
    "PREREGISTRATION_CHECKLIST",
    "REPORT_NAMES",
    "RETENTION_BAND_CONCEPT_STATUS",
    "SMALL_CAPITAL_REFERENCE",
    "FamilyAClosureImmutabilityError",
    "FamilyAClosureInputMismatch",
    "build_family_a_phase2_closure",
    "closure_baseline_snapshot",
    "closure_manifest_body",
    "finalize_family_a_closure",
    "governance_policy",
    "verify_closure_inputs",
)
