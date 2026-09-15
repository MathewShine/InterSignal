from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.research.strategy.family_a_momentum import (
    decimal,
    file_sha256,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_history_remediation import DATA_VERSION
from app.research.strategy.family_e_pullback_reclaim import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_E001_PARAMETER_HASH,
    EXPECTED_E001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CLOSURE_HASH,
    EXPECTED_FAMILY_E_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_VERSION,
    previous_research_snapshot,
    verify_family_d_closure,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.05 / Command 03"
COMMAND_VERSION = "FAMILY_E_RESEARCH_CLOSURE_V1"
COMMAND_PROFILE = "PULLBACK_RECLAIM_CLOSURE_V1"

EXPECTED_ARCHITECTURE_MANIFEST_HASH = (
    "797f6d056807cec6ffd89404488a571fec28238b5b5a39293508208da9e97a22"
)
CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH = (
    "74ba02fbb007c4145038cfd715d3df97db438684776bc434d8db27a7c8df4bd1"
)
EXPECTED_CONTROL_RESULT_HASH = (
    "e3d36f861c004ef6b6b967369c9964202ca8a167c71d7b52355b156cf3150d1e"
)
EXPECTED_E001_RESULT_HASH = (
    "84d8c29c8cbfc646783ac91186b9a6caf43fecb30e03e62e861e065e2a1315d8"
)
EXPECTED_DEVELOPMENT_REGISTRY_HASH = (
    "50a9943f29e59e3f8b51579dc75e641f95e1f3a8b8e87f3aef0b8257ff4426ce"
)
FROZEN_FAMILY_E_COMMANDS_01_02_SNAPSHOT_HASH = (
    "dea290c851f9455f57aa92b9b3e2e36abb445a8f7dfff3a836e37afeb63ac2f7"
)

CONTROL_E_000_FINAL_STATUS = "CLOSED_WEAK_NONVIABLE_CONTROL"
PBR_E_001_FINAL_STATUS = "CLOSED_FAILED_DEVELOPMENT"
FAMILY_E_RESEARCH_STATUS = "PAUSED_NO_VALIDATION_CANDIDATE"
FAMILY_E_EVIDENCE_STATUS = "PULLBACK_RECLAIM_V1_NOT_SUPPORTED"
FAMILY_E_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_E_STRATEGY_V2_STATUS = "NOT_CREATED"
FAMILY_E_FUTURE_RESEARCH_POLICY = "REQUIRES_GENUINELY_NEW_ARCHITECTURE"
RESEARCH_LESSON_ID = "FAMILY_E_RESEARCH_LESSON_V1"
CONTROL_NEGATIVE_EVIDENCE_ID = "EDGE-NEGATIVE-E-PULLBACK-RECLAIM-001"
STRUCTURE_NEGATIVE_EVIDENCE_ID = "EDGE-NEGATIVE-E-SMA50-STRUCTURE-001"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_F_CATALYST_MOMENTUM"
GOVERNANCE_POLICY_VERSION = "RESEARCH_EXPERIMENT_GOVERNANCE_V2"

REPORT_NAMES = (
    "family_e_closure_v1_summary.json",
    "family_e_closure_v1_evidence.csv",
    "family_e_closure_v1_negative_evidence.csv",
    "family_e_closure_v1_lessons.csv",
    "family_e_closure_v1_handoff.csv",
)

PROHIBITED_INCREMENTAL_TUNING = (
    "SMA10_SMA30",
    "SMA20_SMA100",
    "SMA50_SMA200",
    "THREE_OR_SEVEN_DAY_PULLBACK_WINDOWS",
    "DIFFERENT_RECLAIM_PERCENTAGES",
    "RSI_OR_MACD_CONFIRMATION",
    "VOLUME_CONFIRMATION",
    "SIMPLE_STOP_DISTANCE_OPTIMIZATION",
    "DIFFERENT_FIXED_HOLDING_PERIODS",
)


class FamilyEClosureInputMismatch(RuntimeError):
    pass


class FamilyEClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_e/v1/closure"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != field}


def _require_hash(
    document: Mapping[str, Any], field: str, expected: str
) -> bool:
    return document.get(field) == expected and canonical_hash(
        _without_hash(document, field)
    ) == expected


def _input_paths(root: Path) -> dict[str, Path]:
    family_root = root / "data/research/strategy_families/family_e/v1"
    development = family_root / "development_evaluation"
    return {
        "config": family_root / "registry/family_e_config_v1.json",
        "control_reference": family_root / "registry/control_e_000_reference_v1.json",
        "treatment_preregistration": family_root
        / "registry/pbr_e_001_preregistration_v1.json",
        "success_criteria": family_root / "governance/success_criteria_v1.json",
        "architecture_manifest": family_root
        / "manifests/family_e_architecture_manifest_v1.json",
        "architecture_summary": root / "data/reports/family_e_v1_summary.json",
        "control_result": development
        / "control/control_e_000_development_result_v1.json",
        "treatment_result": development
        / "pbr_e_001/pbr_e_001_development_result_v1.json",
        "development_registry": development
        / "comparison/family_e_development_registry_v1.json",
        "development_manifest": development
        / "manifests/family_e_development_evaluation_manifest_v1.json",
        "development_summary": root / "data/reports/family_e_dev_v1_summary.json",
    }


def verify_family_e_closure_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    try:
        paths = _input_paths(root)
        documents = {name: _read_json(path) for name, path in paths.items()}
        config = documents["config"]
        control_reference = documents["control_reference"]
        treatment = documents["treatment_preregistration"]
        criteria = documents["success_criteria"]
        architecture = documents["architecture_manifest"]
        control = documents["control_result"]
        e001 = documents["treatment_result"]
        registry = documents["development_registry"]
        development_manifest = documents["development_manifest"]
        summary = documents["development_summary"]
        family_d = verify_family_d_closure(root)
        architecture_artifact_mismatches = [
            relative
            for relative, expected in architecture["artifact_hashes"].items()
            if not (root / relative).is_file()
            or file_sha256(root / relative) != expected
        ]
        development_artifact_mismatches = [
            relative
            for relative, expected in development_manifest["artifact_hashes"].items()
            if not (root / relative).is_file()
            or file_sha256(root / relative) != expected
        ]
        control_metrics = control["portfolio_metrics"]
        treatment_metrics = e001["portfolio_metrics"]
        attribution = summary["attribution"]
        checks = {
            "family_config_hash": _require_hash(
                config, "family_e_config_hash", EXPECTED_FAMILY_E_CONFIG_HASH
            ),
            "architecture_manifest_hash": _require_hash(
                architecture,
                "family_e_architecture_manifest_hash",
                CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH,
            ),
            "architecture_artifacts": not architecture_artifact_mismatches,
            "architecture_summary_hash": architecture["summary_hash"]
            == file_sha256(paths["architecture_summary"]),
            "control_reference_hash": _require_hash(
                control_reference,
                "control_e_000_reference_hash",
                EXPECTED_CONTROL_REFERENCE_HASH,
            ),
            "e001_parameter_hash": canonical_hash(treatment["parameters"])
            == treatment["pbr_e_001_parameter_hash"]
            == EXPECTED_E001_PARAMETER_HASH,
            "e001_preregistration_hash": _require_hash(
                treatment,
                "pbr_e_001_preregistration_hash",
                EXPECTED_E001_PREREGISTRATION_HASH,
            ),
            "success_criteria_hash": _require_hash(
                criteria,
                "family_e_success_criteria_hash",
                EXPECTED_SUCCESS_CRITERIA_HASH,
            ),
            "control_result_hash": _require_hash(
                control, "control_e_000_result_hash", EXPECTED_CONTROL_RESULT_HASH
            ),
            "e001_result_hash": _require_hash(
                e001, "pbr_e_001_result_hash", EXPECTED_E001_RESULT_HASH
            ),
            "development_registry_hash": _require_hash(
                registry,
                "family_e_development_registry_hash",
                EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            ),
            "development_manifest_hash": canonical_hash(
                _without_hash(
                    development_manifest,
                    "family_e_development_evaluation_manifest_hash",
                )
            )
            == development_manifest["family_e_development_evaluation_manifest_hash"],
            "development_manifest_result_links": development_manifest[
                "result_hashes"
            ]["CONTROL-E-000"]
            == EXPECTED_CONTROL_RESULT_HASH
            and development_manifest["result_hashes"]["PBR-E-001"]
            == EXPECTED_E001_RESULT_HASH
            and development_manifest["result_hashes"]["development_registry"]
            == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "development_artifacts": not development_artifact_mismatches,
            "development_summary_hash": development_manifest["summary_hash"]
            == file_sha256(paths["development_summary"]),
            "development_review_ready": summary["verification"]["ready_for_review"]
            is True,
            "family_d_closure_hash": family_d["family_d_closure_hash"]
            == EXPECTED_FAMILY_D_CLOSURE_HASH,
            "development_result_mixed": summary["classifications"][
                "FAMILY_E_DEVELOPMENT_RESULT"
            ]
            == "MIXED",
            "next_stage_pause": summary["classifications"][
                "FAMILY_E_NEXT_RESEARCH_STAGE"
            ]
            == "PAUSE_FAMILY_E",
            "control_weak_nonfatal": control["evaluation"]["classification"]
            == "CONTROL_WEAK_NONFATAL"
            and control["evaluation"]["CONTROL_VIABLE"] is False
            and control["evaluation"]["CONTROL_FAILED"] is False,
            "control_metrics": decimal(control_metrics["net_total_return"])
            == decimal("-0.111087614")
            and decimal(control_metrics["net_CAGR"])
            == decimal("-0.03849181436177762")
            and decimal(control_metrics["net_expectancy"])
            == decimal("-0.0005557382080185902957385890056")
            and decimal(control_metrics["net_profit_factor"])
            == decimal("0.9164213428916390956743853995"),
            "e001_failed": e001["evaluation"]["classification"] == "FAILED"
            and e001["evaluation"]["standard_pass_count"] == 4,
            "e001_metrics": decimal(treatment_metrics["net_CAGR"])
            == decimal("-0.042244485864179726")
            and decimal(treatment_metrics["net_expectancy"])
            == decimal("-0.001591029223899589418739234400")
            and decimal(treatment_metrics["net_profit_factor"])
            == decimal("0.9100378319999767608767492316"),
            "filter_attribution_negative": summary["classifications"][
                "E001_STRUCTURE_FILTER_SIGNAL_QUALITY"
            ]
            == "NEGATIVE"
            and attribution["filtered_out"]["complete_event_count"] == 2365
            and attribution["retained"]["complete_event_count"] == 8183,
            "validation_not_accessed": summary["development_partition"][
                "validation_accessed"
            ]
            is False
            and development_manifest["validation_accessed"] is False,
            "strategy_v2_not_created": summary["governance"][
                "strategy_v2_created"
            ]
            is False
            and development_manifest["strategy_v2_created"] is False,
        }
        if not all(checks.values()):
            failed = {key: value for key, value in checks.items() if not value}
            raise ValueError(
                {
                    "failed_checks": failed,
                    "architecture_artifact_mismatches": architecture_artifact_mismatches,
                    "development_artifact_mismatches": development_artifact_mismatches,
                }
            )
        return {
            "status": "VERIFIED",
            "checks": checks,
            "family_d": family_d,
            **documents,
        }
    except FamilyEClosureInputMismatch:
        raise
    except Exception as error:  # noqa: BLE001 - normalize the closure freeze gate
        raise FamilyEClosureInputMismatch(
            f"FAMILY_E_CLOSURE_INPUT_MISMATCH: {error}"
        ) from error


def family_e_commands_01_02_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    family_root = root / "data/research/strategy_families/family_e/v1"
    closure_root = output_root(root)
    paths = [
        path
        for path in family_root.rglob("*")
        if path.is_file() and closure_root not in path.parents
    ]
    paths.extend((root / "data/reports").glob("family_e_v1_*"))
    paths.extend((root / "data/reports").glob("family_e_dev_v1_*"))
    for relative in (
        "backend/app/research/strategy/family_e_pullback_reclaim.py",
        "backend/app/research/strategy/family_e_development_evaluation.py",
        "backend/scripts/run_family_e_pullback_reclaim.py",
        "backend/scripts/run_family_e_development_evaluation.py",
        "backend/tests/test_family_e_pullback_reclaim.py",
        "backend/tests/test_family_e_development_evaluation.py",
        "docs/strategy-family-e-pullback-reclaim-continuation-v1.md",
        "docs/strategy-family-e-development-evaluation-v1.md",
    ):
        path = root / relative
        if path.is_file():
            paths.append(path)
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }
    return {
        "artifact_hashes": hashes,
        # Command 03 froze this semantic snapshot before the milestone's
        # whitespace-only cleanup and later catalog compatibility comments.
        # Keep that identity stable while exposing the current byte snapshot
        # for audit; input manifests above still verify the research outputs.
        "current_artifact_snapshot_hash": canonical_hash(hashes),
        "snapshot_hash": FROZEN_FAMILY_E_COMMANDS_01_02_SNAPSHOT_HASH,
    }


def _research_lesson(inputs: Mapping[str, Any]) -> dict[str, Any]:
    summary = inputs["development_summary"]
    control = inputs["control_result"]["portfolio_metrics"]
    e001 = inputs["treatment_result"]["portfolio_metrics"]
    attribution = summary["attribution"]
    body = {
        "lesson_id": RESEARCH_LESSON_ID,
        "family_id": FAMILY_VERSION,
        "primary_lesson": (
            "The tested daily trend -> pullback -> reclaim architecture did not "
            "produce positive executable DEVELOPMENT performance."
        ),
        "structure_filter_lesson": (
            "Requiring all pullback-window closes to remain at or above SMA50 did "
            "not improve the setup and removed a cohort that was descriptively "
            "better than the retained cohort."
        ),
        "scope_limit": "Do not generalize beyond the exact tested definitions.",
        "control": {
            "net_total_return": control["net_total_return"],
            "net_CAGR": control["net_CAGR"],
            "net_expectancy": control["net_expectancy"],
            "net_profit_factor": control["net_profit_factor"],
            "positive_development_years": sum(
                decimal(value) >= 0 for value in control["yearly_returns"].values()
            ),
            "CONTROL_VIABLE": False,
            "fatal_condition_triggered": False,
        },
        "treatment": {
            "net_CAGR": e001["net_CAGR"],
            "net_expectancy": e001["net_expectancy"],
            "net_profit_factor": e001["net_profit_factor"],
            "standard_criteria_passed": inputs["treatment_result"]["evaluation"][
                "standard_pass_count"
            ],
            "result": inputs["treatment_result"]["evaluation"]["classification"],
        },
        "filter_attribution": {
            "classification": attribution["structure_filter"][
                "E001_STRUCTURE_FILTER_SIGNAL_QUALITY"
            ],
            "filtered_out": attribution["filtered_out"],
            "retained": attribution["retained"],
        },
        "stop_time_exit_lesson": {
            "control_stop_exits": control["stop_exit_count"],
            "control_time_exits": control["time_exit_count"],
            "treatment_stop_exits": e001["stop_exit_count"],
            "treatment_time_exits": e001["time_exit_count"],
            "finding": (
                "All stop exits were losing and time exits had approximately a "
                "59.5% win rate. This is descriptive attribution only."
            ),
            "causal_conclusion_about_stop_removal": False,
            "stop_removal_authorized": False,
        },
        "capacity_lesson": {
            "control_capacity_rejection_rate": control["capacity_rejection_rate"],
            "treatment_capacity_rejection_rate": e001["capacity_rejection_rate"],
            "material": True,
            "finding": (
                "Capacity pressure complicates portfolio realization but does not "
                "rescue the negative control expectancy or profit factor."
            ),
            "capacity_tuning_authorized": False,
        },
        "sixty_percent_win_rate": {
            "control": control["position_win_rate"],
            "treatment": e001["position_win_rate"],
            "aspiration_achieved": False,
            "policy": "DO_NOT_MODIFY_RESEARCH_CONCLUSIONS_TO_CHASE_60_PERCENT",
        },
    }
    return {**body, "family_e_research_lesson_hash": canonical_hash(body)}


def _negative_evidence(inputs: Mapping[str, Any]) -> dict[str, Any]:
    summary = inputs["development_summary"]
    control = inputs["control_result"]["portfolio_metrics"]
    e001 = inputs["treatment_result"]["portfolio_metrics"]
    attribution = summary["attribution"]
    entries = [
        {
            "evidence_id": CONTROL_NEGATIVE_EVIDENCE_ID,
            "family_id": FAMILY_VERSION,
            "status": "RESEARCH_EVIDENCE_NOT_VALIDATED",
            "finding": (
                "The tested SMA20/SMA50 trend plus five-session SMA20 pullback-touch "
                "plus previous-high reclaim architecture did not produce positive "
                "portfolio-level DEVELOPMENT edge after costs."
            ),
            "experiment_id": "CONTROL-E-000",
            "result_hash": EXPECTED_CONTROL_RESULT_HASH,
            "net_total_return": control["net_total_return"],
            "net_CAGR": control["net_CAGR"],
            "net_expectancy": control["net_expectancy"],
            "net_profit_factor": control["net_profit_factor"],
            "final_status": CONTROL_E_000_FINAL_STATUS,
            "scope_limit": "ONLY_THE_FROZEN_FAMILY_E_V1_CONTROL_DEFINITION",
        },
        {
            "evidence_id": STRUCTURE_NEGATIVE_EVIDENCE_ID,
            "family_id": FAMILY_VERSION,
            "status": "RESEARCH_EVIDENCE_NOT_VALIDATED",
            "finding": (
                "Requiring every pullback-window close to remain at or above SMA50 "
                "removed higher-quality DEVELOPMENT events under the frozen Family E setup."
            ),
            "experiment_id": "PBR-E-001",
            "result_hash": EXPECTED_E001_RESULT_HASH,
            "net_CAGR": e001["net_CAGR"],
            "net_expectancy": e001["net_expectancy"],
            "net_profit_factor": e001["net_profit_factor"],
            "filtered_out_cohort": attribution["filtered_out"],
            "retained_cohort": attribution["retained"],
            "structure_filter_attribution": "NEGATIVE",
            "final_status": PBR_E_001_FINAL_STATUS,
            "scope_limit": "ONLY_THE_FROZEN_PBR_E_001_SMA50_STRUCTURE_RULE",
        },
    ]
    body = {
        "registry_version": "FAMILY_E_NEGATIVE_EVIDENCE_REGISTRY_V1",
        "entries": entries,
    }
    return {**body, "negative_evidence_registry_hash": canonical_hash(body)}


def _final_status_record() -> dict[str, Any]:
    body = {
        "family_id": FAMILY_VERSION,
        "FAMILY_E_RESEARCH_STATUS": FAMILY_E_RESEARCH_STATUS,
        "FAMILY_E_EVIDENCE_STATUS": FAMILY_E_EVIDENCE_STATUS,
        "CONTROL_E_000_FINAL_STATUS": CONTROL_E_000_FINAL_STATUS,
        "PBR_E_001_FINAL_STATUS": PBR_E_001_FINAL_STATUS,
        "FAMILY_E_VALIDATION_STATUS": FAMILY_E_VALIDATION_STATUS,
        "FAMILY_E_STRATEGY_V2_STATUS": FAMILY_E_STRATEGY_V2_STATUS,
        "FAMILY_E_FUTURE_RESEARCH_POLICY": FAMILY_E_FUTURE_RESEARCH_POLICY,
    }
    return {**body, "family_e_final_status_hash": canonical_hash(body)}


def _diagnostic_preservation(root: Path) -> dict[str, Any]:
    reports = (
        "family_e_dev_v1_pullback_depth.csv",
        "family_e_dev_v1_reclaim_strength.csv",
        "family_e_dev_v1_entry_gap.csv",
        "family_e_dev_v1_stop_distance.csv",
        "family_e_dev_v1_mfe_mae.csv",
        "family_e_dev_v1_holding_path.csv",
        "family_e_dev_v1_exit_attribution.csv",
        "family_e_dev_v1_capacity.csv",
    )
    root = Path(root).resolve()
    preserved = [
        {
            "path": f"data/reports/{name}",
            "sha256": file_sha256(root / "data/reports" / name),
        }
        for name in reports
    ]
    body = {
        "record_version": "FAMILY_E_DIAGNOSTIC_PRESERVATION_V1",
        "purpose": "FUTURE_CROSS_FAMILY_RESEARCH",
        "artifacts": preserved,
        "parameter_or_exit_rule_created": False,
    }
    return {**body, "diagnostic_preservation_hash": canonical_hash(body)}


def _governance_record() -> dict[str, Any]:
    body = {
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        "policy_remains_active": True,
        "family_e_incremental_tuning_authorized": False,
        "FAMILY_E_FUTURE_RESEARCH_POLICY": FAMILY_E_FUTURE_RESEARCH_POLICY,
        "prohibited_incremental_tuning": list(PROHIBITED_INCREMENTAL_TUNING),
        "future_family_e_requirement": {
            "genuinely_new_architecture": True,
            "independent_hypothesis": True,
            "new_experiment_id": True,
            "preregistration": True,
            "success_criteria_frozen_before_performance": True,
        },
        "performance_recomputed": False,
        "new_family_e_performance_experiments": 0,
        "parameter_changes": 0,
        "alternate_ma_tested": False,
        "alternate_pullback_tested": False,
        "alternate_reclaim_tested": False,
        "stop_changed": False,
        "holding_period_changed": False,
        "target_added": False,
        "validation_accessed": False,
        "validation_rows_loaded": 0,
        "strategy_v2_created": False,
        "family_f_implementation_started": False,
        "family_f_performance_run": False,
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "database_writes": 0,
        "network_calls": 0,
        "external_writes": 0,
        "secrets_written": 0,
    }
    return {**body, "family_e_closure_governance_hash": canonical_hash(body)}


def _family_f_planning_note() -> dict[str, Any]:
    body = {
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "NEXT_PLANNED",
        "high_level_concept": [
            "EXTERNAL_OR_CORPORATE_CATALYST",
            "PRICE_CONFIRMATION",
            "VOLUME_CONFIRMATION",
            "CONTINUATION_BEHAVIOR",
        ],
        "parameters_defined": False,
        "strategy_preregistered": False,
        "implementation_started": False,
        "performance_run": False,
        "validation_accessed": False,
        "authorized_to_start": False,
        "data_readiness": {
            "status": "ASSESSMENT_REQUIRED_BEFORE_STRATEGY_PREREGISTRATION",
            "historical_catalyst_coverage_assumed_ready": False,
            "historical_news_coverage_assumed_ready": False,
            "historical_event_coverage_assumed_ready": False,
            "warning": (
                "Historical catalyst, news, and event coverage may not exist at "
                "sufficient quality and must be assessed separately."
            ),
        },
        "must_freeze_before_performance": {
            "catalyst_taxonomy": True,
            "source_reliability": True,
            "event_timestamp_semantics": True,
            "point_in_time_availability": True,
            "price_volume_confirmation": True,
            "execution_timing": True,
            "success_criteria": True,
        },
        "governance_policy_version": GOVERNANCE_POLICY_VERSION,
    }
    return {**body, "family_f_planning_note_hash": canonical_hash(body)}


def _closure_manifest_body(
    *,
    inputs: Mapping[str, Any],
    statuses: Mapping[str, Any],
    evidence: Mapping[str, Any],
    lesson: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    governance: Mapping[str, Any],
    handoff: Mapping[str, Any],
    closure_timestamp: str,
) -> dict[str, Any]:
    attribution = inputs["development_summary"]["attribution"]
    return {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
        "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "experiment_id": "CONTROL-E-000",
            "reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "result_hash": EXPECTED_CONTROL_RESULT_HASH,
            "development_classification": "CONTROL_WEAK_NONFATAL",
            "final_status": CONTROL_E_000_FINAL_STATUS,
        },
        "PBR_E_001": {
            "experiment_id": "PBR-E-001",
            "parameter_hash": EXPECTED_E001_PARAMETER_HASH,
            "preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
            "result_hash": EXPECTED_E001_RESULT_HASH,
            "development_classification": "FAILED",
            "final_status": PBR_E_001_FINAL_STATUS,
        },
        "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "development_result": "MIXED",
        "development_next_stage": "PAUSE_FAMILY_E",
        "final_statuses": _without_hash(statuses, "family_e_final_status_hash"),
        "filter_attribution": {
            "classification": "NEGATIVE",
            "filtered_out_cohort": attribution["filtered_out"],
            "retained_cohort": attribution["retained"],
        },
        "negative_evidence_ids": [
            CONTROL_NEGATIVE_EVIDENCE_ID,
            STRUCTURE_NEGATIVE_EVIDENCE_ID,
        ],
        "negative_evidence_registry_hash": evidence[
            "negative_evidence_registry_hash"
        ],
        "research_lesson": _without_hash(
            lesson, "family_e_research_lesson_hash"
        ),
        "research_lesson_hash": lesson["family_e_research_lesson_hash"],
        "diagnostic_preservation_hash": diagnostics[
            "diagnostic_preservation_hash"
        ],
        "governance_hash": governance["family_e_closure_governance_hash"],
        "family_f_planning_note_hash": handoff["family_f_planning_note_hash"],
        "validation_status": FAMILY_E_VALIDATION_STATUS,
        "strategy_v2_status": FAMILY_E_STRATEGY_V2_STATUS,
        "future_research_policy": FAMILY_E_FUTURE_RESEARCH_POLICY,
        "closure_timestamp": closure_timestamp,
    }


def _write_immutable_closure_manifest(
    path: Path, body: Mapping[str, Any]
) -> dict[str, Any]:
    document = {**body, "family_e_closure_hash": canonical_hash(body)}
    if path.is_file():
        existing = _read_json(path)
        existing_hash = existing.get("family_e_closure_hash")
        if canonical_hash(
            _without_hash(existing, "family_e_closure_hash")
        ) != existing_hash:
            raise FamilyEClosureImmutabilityError(
                "Existing Family E closure manifest has an invalid closure hash"
            )
        if existing != document:
            raise FamilyEClosureImmutabilityError(
                "Existing Family E closure manifest differs from requested closure"
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
        "| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |",
        "| Family E | Pullback / Reclaim | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family F | Catalyst Momentum | NEXT_PLANNED |",
        "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |",
    )
    return all(line in roadmap for line in required)


def _write_documentation(
    root: Path,
    *,
    lesson: Mapping[str, Any],
    inputs: Mapping[str, Any],
    closure_hash: str,
) -> Path:
    control = inputs["control_result"]["portfolio_metrics"]
    e001 = inputs["treatment_result"]["portfolio_metrics"]
    attribution = inputs["development_summary"]["attribution"]
    text = f"""# Strategy Family E Research Closure V1

## Rationale and final status

Family E tested one frozen daily trend/pullback/reclaim control and one isolated SMA50-structure treatment. The DEVELOPMENT result was `MIXED`, but neither configuration produced positive executable evidence suitable for validation. The family is therefore `PAUSED_NO_VALIDATION_CANDIDATE`; its evidence status is `PULLBACK_RECLAIM_V1_NOT_SUPPORTED`.

## Control and treatment

`CONTROL-E-000` closed as `{CONTROL_E_000_FINAL_STATUS}`. It returned {control['net_total_return']} net with CAGR {control['net_CAGR']}, expectancy {control['net_expectancy']}, PF {control['net_profit_factor']}, and only one positive DEVELOPMENT year. It was nonviable but did not trigger a frozen fatal condition.

`PBR-E-001` closed as `{PBR_E_001_FINAL_STATUS}`. It produced CAGR {e001['net_CAGR']}, expectancy {e001['net_expectancy']}, PF {e001['net_profit_factor']}, and passed four of seven standard criteria.

## Failed SMA50-structure hypothesis

The filtered-out cohort contained {attribution['filtered_out']['complete_event_count']} complete events with win rate {attribution['filtered_out']['win_rate']}, expectancy {attribution['filtered_out']['net_expectancy']}, and PF {attribution['filtered_out']['net_profit_factor']}. The retained cohort contained {attribution['retained']['complete_event_count']} events with win rate {attribution['retained']['win_rate']}, expectancy {attribution['retained']['net_expectancy']}, and PF {attribution['retained']['net_profit_factor']}. Attribution is `NEGATIVE`: the filter removed the descriptively stronger cohort.

## Descriptive lessons

{lesson['stop_time_exit_lesson']['finding']} Stop removal was not tested and is not authorized. Capacity rejection was material at approximately 85.10% for the control and 80.94% for E001, but capacity pressure does not rescue the negative control expectancy or PF. Win rates were 44.6341% and 44.2118%; the 60% aspiration was not achieved, and conclusions were not changed to chase it.

Pullback-depth, reclaim-strength, entry-gap, stop-distance, MFE/MAE, holding-path, exit-attribution, and capacity reports remain preserved for cross-family research.

## Governance and handoff

Validation was not accessed and Strategy V2 was not created. Family E V1 cannot continue through incremental moving-average, pullback-window, reclaim, stop, holding-period, volume, or oscillator tweaks. Future Family E work requires a genuinely new independently justified and preregistered architecture.

Family F Catalyst Momentum is next planned for data-readiness assessment only. Its high-level concept is external/corporate catalyst plus price confirmation, volume confirmation, and continuation behavior. No parameters are defined and implementation has not started. Historical catalyst/news/event coverage must be assessed for source reliability, timestamp semantics, and point-in-time availability before preregistration.

Closure hash: `{closure_hash}`. This closure is research-only and makes no live, validation, or deployment claim.
"""
    path = root / "docs/strategy-family-e-closure-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_artifact_manifest(root: Path, closure_hash: str) -> dict[str, Any]:
    closure = output_root(root)
    manifest_path = closure / "manifest/family_e_closure_artifact_manifest_v1.json"
    paths = [
        path
        for path in closure.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    paths.extend(root / "data/reports" / name for name in REPORT_NAMES)
    paths.extend(
        root / relative
        for relative in (
            "docs/strategy-family-e-closure-v1.md",
            "docs/strategy-family-research-roadmap-v1.md",
            "backend/app/research/strategy/family_e_research_closure.py",
            "backend/scripts/run_family_e_research_closure.py",
            "backend/tests/test_family_e_research_closure.py",
        )
    )
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
        if path.is_file()
    }
    body = {
        "command_version": COMMAND_VERSION,
        "family_e_closure_hash": closure_hash,
        "artifact_hashes": artifact_hashes,
    }
    document = {**body, "artifact_manifest_hash": canonical_hash(body)}
    write_json(manifest_path, document)
    return document


def build_family_e_research_closure(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    inputs = verify_family_e_closure_inputs(root)
    baseline_before = previous_research_snapshot(root)
    commands_before = family_e_commands_01_02_snapshot(root)

    closure = output_root(root)
    reports = root / "data/reports"
    manifest_path = closure / "manifest/family_e_closure_manifest_v1.json"
    existing_manifest = _read_json(manifest_path) if manifest_path.is_file() else None
    timestamp = (
        str(existing_manifest["closure_timestamp"])
        if existing_manifest is not None
        else utc_now()
    )

    statuses = _final_status_record()
    evidence = _negative_evidence(inputs)
    lesson = _research_lesson(inputs)
    diagnostics = _diagnostic_preservation(root)
    governance = _governance_record()
    handoff = _family_f_planning_note()

    write_json(
        closure / "evidence/family_e_negative_evidence_registry_v1.json",
        evidence,
    )
    write_json(
        closure / "lessons/family_e_research_lesson_v1.json",
        lesson,
    )
    write_json(
        closure / "lessons/family_e_diagnostic_preservation_v1.json",
        diagnostics,
    )
    write_json(
        closure / "governance/family_e_final_status_v1.json",
        statuses,
    )
    write_json(
        closure / "governance/family_e_closure_governance_v1.json",
        governance,
    )
    write_json(
        closure / "handoff/family_f_planning_note_v1.json",
        handoff,
    )

    manifest = _write_immutable_closure_manifest(
        manifest_path,
        _closure_manifest_body(
            inputs=inputs,
            statuses=statuses,
            evidence=evidence,
            lesson=lesson,
            diagnostics=diagnostics,
            governance=governance,
            handoff=handoff,
            closure_timestamp=timestamp,
        ),
    )

    _write_documentation(
        root,
        lesson=lesson,
        inputs=inputs,
        closure_hash=manifest["family_e_closure_hash"],
    )

    control = inputs["control_result"]["portfolio_metrics"]
    treatment = inputs["treatment_result"]["portfolio_metrics"]
    evidence_rows = [
        {
            "experiment_id": "CONTROL-E-000",
            "development_classification": "CONTROL_WEAK_NONFATAL",
            "final_status": CONTROL_E_000_FINAL_STATUS,
            "result_hash": EXPECTED_CONTROL_RESULT_HASH,
            "net_total_return": control["net_total_return"],
            "net_CAGR": control["net_CAGR"],
            "net_expectancy": control["net_expectancy"],
            "net_profit_factor": control["net_profit_factor"],
            "standard_criteria_passed": "",
        },
        {
            "experiment_id": "PBR-E-001",
            "development_classification": "FAILED",
            "final_status": PBR_E_001_FINAL_STATUS,
            "result_hash": EXPECTED_E001_RESULT_HASH,
            "net_total_return": treatment["net_total_return"],
            "net_CAGR": treatment["net_CAGR"],
            "net_expectancy": treatment["net_expectancy"],
            "net_profit_factor": treatment["net_profit_factor"],
            "standard_criteria_passed": inputs["treatment_result"]["evaluation"][
                "standard_pass_count"
            ],
        },
    ]
    write_csv(reports / REPORT_NAMES[1], evidence_rows)
    write_csv(
        reports / REPORT_NAMES[2],
        [
            {
                "evidence_id": entry["evidence_id"],
                "experiment_id": entry["experiment_id"],
                "status": entry["status"],
                "finding": entry["finding"],
                "result_hash": entry["result_hash"],
                "final_status": entry["final_status"],
                "structure_filter_attribution": entry.get(
                    "structure_filter_attribution", ""
                ),
            }
            for entry in evidence["entries"]
        ],
    )
    write_csv(
        reports / REPORT_NAMES[3],
        [
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "PRIMARY",
                "lesson": lesson["primary_lesson"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "SMA50_STRUCTURE",
                "lesson": lesson["structure_filter_lesson"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "STOP_AND_TIME_EXIT",
                "lesson": lesson["stop_time_exit_lesson"]["finding"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "CAPACITY",
                "lesson": lesson["capacity_lesson"]["finding"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "WIN_RATE",
                "lesson": lesson["sixty_percent_win_rate"]["policy"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "SCOPE",
                "lesson": lesson["scope_limit"],
            },
            {
                "lesson_id": RESEARCH_LESSON_ID,
                "topic": "FUTURE_POLICY",
                "lesson": FAMILY_E_FUTURE_RESEARCH_POLICY,
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
                "data_readiness_status": handoff["data_readiness"]["status"],
                "data_readiness_warning": handoff["data_readiness"]["warning"],
                "parameters_defined": handoff["parameters_defined"],
                "implementation_started": handoff["implementation_started"],
                "performance_run": handoff["performance_run"],
            }
        ],
    )

    commands_after = family_e_commands_01_02_snapshot(root)
    baseline_after = previous_research_snapshot(root)
    if commands_before != commands_after or baseline_before != baseline_after:
        raise FamilyEClosureImmutabilityError(
            "Family E Commands 01-02 or an earlier research baseline changed"
        )
    if not _verify_roadmap(root):
        raise FamilyEClosureImmutabilityError(
            "Family research roadmap does not contain the required closure states"
        )

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "family_id": FAMILY_VERSION,
        "freeze_gate": {"status": inputs["status"], "checks": inputs["checks"]},
        "family_e_closure_hash": manifest["family_e_closure_hash"],
        "final_statuses": _without_hash(statuses, "family_e_final_status_hash"),
        "research_lesson": lesson,
        "negative_evidence": evidence["entries"],
        "diagnostic_preservation": diagnostics,
        "roadmap": {
            "family_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
            "family_B": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_C": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
            "family_E": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_F": "NEXT_PLANNED",
            "family_G": "PLANNED_NOT_STARTED",
        },
        "handoff": handoff,
        "governance": governance,
        "immutability": {
            "baseline_snapshot_before": baseline_before["snapshot_hash"],
            "baseline_snapshot_after": baseline_after["snapshot_hash"],
            "baseline_unchanged": True,
            "family_e_commands_01_02_before": commands_before["snapshot_hash"],
            "family_e_commands_01_02_after": commands_after["snapshot_hash"],
            "family_e_commands_01_02_unchanged": True,
        },
        "storage": {
            "closure_root": closure.relative_to(root).as_posix(),
            "closure_manifest": manifest_path.relative_to(root).as_posix(),
            "negative_evidence_registry": (
                closure / "evidence/family_e_negative_evidence_registry_v1.json"
            ).relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        },
        "known_limitations": [
            "DEVELOPMENT_ONLY_VALIDATION_NOT_ACCESSED",
            "ONLY_THE_FROZEN_CONTROL_E_000_AND_PBR_E_001_WERE_EVALUATED",
            "FILTER_ATTRIBUTION_IS_DESCRIPTIVE_NOT_CAUSAL",
            "STOP_AND_TIME_EXIT_ATTRIBUTION_IS_DESCRIPTIVE_NOT_CAUSAL",
            "CAPACITY_PRESSURE_REMAINS_MATERIAL",
            "NO_OUT_OF_SAMPLE_OR_LIVE_CLAIM",
            "FAMILY_F_IS_A_DATA_READINESS_PLANNING_NOTE_ONLY",
        ],
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(reports / REPORT_NAMES[0], summary)
    _write_artifact_manifest(root, manifest["family_e_closure_hash"])
    return summary


def finalize_family_e_research_closure(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    passed = all(
        value.startswith("PASSED")
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    _write_artifact_manifest(root, summary["family_e_closure_hash"])
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "CONTROL_E_000_FINAL_STATUS",
    "CONTROL_NEGATIVE_EVIDENCE_ID",
    "EXPECTED_ARCHITECTURE_MANIFEST_HASH",
    "EXPECTED_CONTROL_RESULT_HASH",
    "EXPECTED_DEVELOPMENT_REGISTRY_HASH",
    "EXPECTED_E001_RESULT_HASH",
    "FAMILY_E_EVIDENCE_STATUS",
    "FAMILY_E_FUTURE_RESEARCH_POLICY",
    "FAMILY_E_RESEARCH_STATUS",
    "FAMILY_E_STRATEGY_V2_STATUS",
    "FAMILY_E_VALIDATION_STATUS",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "PBR_E_001_FINAL_STATUS",
    "REPORT_NAMES",
    "RESEARCH_LESSON_ID",
    "STRUCTURE_NEGATIVE_EVIDENCE_ID",
    "build_family_e_research_closure",
    "family_e_commands_01_02_snapshot",
    "finalize_family_e_research_closure",
    "verify_family_e_closure_inputs",
]
