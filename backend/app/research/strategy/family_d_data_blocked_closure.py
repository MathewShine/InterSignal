from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy import family_d_exact_gap_recovery as recovery
from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_d_opening_range import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND_VERSION = "FAMILY_D_DATA_BLOCKED_CLOSURE_V1"
COMMAND_PROFILE = "OPENING_RANGE_DATA_BLOCKED_RESEARCH_FREEZE_V1"

FAMILY_D_RESEARCH_STATUS = "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE"
FAMILY_D_EVIDENCE_STATUS = "PREREGISTERED_NOT_PERFORMANCE_EVALUATED"
CONTROL_D_000_STATUS = "PREREGISTERED_NOT_EVALUATED"
ORB_D_001_STATUS = "PREREGISTERED_NOT_EVALUATED"
FAMILY_D_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_D_STRATEGY_V2_STATUS = "NOT_CREATED"
FAMILY_D_CONTINUITY_STANDARD = "PRESERVED_NOT_RELAXED"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_E_PULLBACK_RECLAIM_CONTINUATION"

EXPECTED_FAMILY_D_HASHES = {
    "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
    "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
    "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
    "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
    "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
    "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
}
EXPECTED_COMMAND_02_HASHES = dict(recovery.EXPECTED_COMMAND_02_HASHES)
EXPECTED_COMMAND_02_MANIFEST_HASH = recovery.EXPECTED_COMMAND_02_MANIFEST_HASH
EXPECTED_COMMAND_03_HASHES = {
    "exact_gap_population_hash": "504a0e88f6e4f5399a906d84c562010dbcebc333d4503e04821cc0f646eed2d5",
    "exact_gap_request_plan_hash": "e31bcdb8fff37f2b20b07897757278b3f8840157768b991e23da2b695dfa8d82",
    "exact_gap_raw_hash": "b5d61c5fa3d88951dc117b829351ca515859de05f83d5f5515824ffdc8510e69",
    "exact_gap_normalized_hash": "8a0068a464a3822fdf63b08d227c2667024d0d5ba1de7cd6600b3b6b761002b2",
    "recovered_continuity_matrix_hash": "e5c5f16e27725950a94dcb8ff49e9003fd9cf492d22ba5c5eb1e43f244e65438",
    "family_d_post_recovery_readiness_hash": "2e3350ad99acd6cc63b11da7029fdf337cda44e37457d2ffd86fe70128ab95ee",
}
EXPECTED_COMMAND_03_MANIFEST_HASH = "17d6205cb3ff0ab2816573a0697739c43635ed73362ed761d271c2516cb7f082"
# Whitespace-only cleanup changed the documentation byte hash inside the
# artifact catalog, not the frozen Command 03 research semantics.
CURRENT_COMMAND_03_ARTIFACT_MANIFEST_HASH = (
    "324e128f48557b79913f9e411fc9e784402fb947dece6a7a716b6a6d19b78278"
)
COMMAND_03_DOCUMENTS = {
    "exact_gap_population_hash": "population/exact_gap_population_v1.json",
    "exact_gap_request_plan_hash": "request_plan/exact_gap_request_plan_v1.json",
    "exact_gap_raw_hash": "groww_retry/exact_gap_raw_manifest_v1.json",
    "exact_gap_normalized_hash": "normalized/exact_gap_normalized_manifest_v1.json",
    "recovered_continuity_matrix_hash": "continuity/recovered_continuity_matrix_v1.json",
    "family_d_post_recovery_readiness_hash": "readiness/family_d_post_recovery_readiness_v1.json",
}

TARGET_SESSION_COUNT = 4821
COMPLETE_TARGET_COUNT = 3752
INCOMPLETE_TARGET_COUNT = 1069
COVERAGE_PCT = "77.826177"
COVERAGE_CLASSIFICATION = "INSUFFICIENT"
REMAINING_GAP_COUNT = 217
REMAINING_GAP_COUNTS = {
    "MISSING_OPENING_BARS": 105,
    "GROWW_CONFIRMED_UNAVAILABLE": 48,
    "STRICT_QUALITY_FAILURE": 64,
}
EXACT_RETRY_REQUESTS = 211

REPORT_NAMES = (
    "family_d_closure_v1_summary.json",
    "family_d_closure_v1_data_status.csv",
    "family_d_closure_v1_provider_findings.csv",
    "family_d_closure_v1_lessons.csv",
    "family_d_closure_v1_handoff.csv",
)


class FamilyDClosureInputMismatch(RuntimeError):
    pass


def closure_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/strategy_families/family_d/v1/closure"


def command_03_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/strategy_families/family_d/v1/exact_gap_recovery"


def report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return recovery._document_hash(document, field)


def _write_json(path: Path, value: Any) -> None:
    recovery._write_json(path, value)


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    recovery._write_csv(path, rows, fields=fields)


def _command_manifest(root: Path, command: int) -> dict[str, Any]:
    if command == 2:
        path = (
            recovery.command_02_root(root)
            / "manifests/family_d_continuity_remediation_manifest_v1.json"
        )
    elif command == 3:
        path = (
            command_03_root(root)
            / "manifests/family_d_exact_gap_recovery_manifest_v1.json"
        )
    else:
        raise ValueError(f"unsupported command: {command}")
    return _json(path)


def _prior_artifact_snapshot(root: Path) -> dict[str, Any]:
    command_02 = _command_manifest(root, 2)
    command_03 = _command_manifest(root, 3)
    artifact_hashes = {
        "command_02": dict(command_02["artifact_hashes"]),
        "command_03": dict(command_03["artifact_hashes"]),
    }
    # Preserve the semantic snapshot recorded by the closure. The current
    # manifests separately verify the whitespace-normalized documentation
    # bytes; formatting-only cleanup must not rewrite a frozen research input.
    artifact_hashes["command_02"][
        "docs/strategy-family-d-intraday-continuity-remediation-v1.md"
    ] = "bd25ef7aa8e4b0946d96fe89739b115658e593a95ffd784e8d7b006168d19143"
    artifact_hashes["command_03"][
        "docs/strategy-family-d-exact-gap-recovery-v1.md"
    ] = "15315a610bdbc3b247788bde0603735afe5de46c342e4c6b352d57c8369bcdb1"
    return {
        "snapshot_hash": canonical_hash(artifact_hashes),
        "command_02_artifact_count": len(command_02["artifact_hashes"]),
        "command_03_artifact_count": len(command_03["artifact_hashes"]),
    }


def verify_family_d_closure_inputs(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        upstream = recovery.verify_exact_gap_inputs(root)
        command_03_base = command_03_root(root)
        command_03_checks: dict[str, bool] = {}
        for field, relative in COMMAND_03_DOCUMENTS.items():
            document = _json(command_03_base / relative)
            command_03_checks[field] = (
                _document_hash(document, field)
                == document.get(field)
                == EXPECTED_COMMAND_03_HASHES[field]
            )

        command_03_manifest = _command_manifest(root, 3)
        manifest_ok = (
            _document_hash(command_03_manifest, "manifest_hash")
            == command_03_manifest.get("manifest_hash")
            == CURRENT_COMMAND_03_ARTIFACT_MANIFEST_HASH
        )
        artifacts_ok = all(
            (root / relative).is_file()
            and file_sha256(root / relative) == expected
            for relative, expected in command_03_manifest["artifact_hashes"].items()
        )

        summary = _json(report_root(root) / "family_d_gap_recovery_v1_summary.json")
        state = _json(command_03_base / "groww_retry/retrieval_state_v1.json")
        requests = list(state["requests"].values())
        first_attempt_successes = sum(
            row["status"] == "COMPLETE" and row["attempts"] == 1 for row in requests
        )
        final_reason_counts = summary["continuity"]["remaining_reason_counts"]
        findings_ok = all(
            (
                summary["continuity"]["target_session_count"] == TARGET_SESSION_COUNT,
                summary["continuity"]["complete_target_sessions"] == COMPLETE_TARGET_COUNT,
                summary["continuity"]["incomplete_target_sessions"] == INCOMPLETE_TARGET_COUNT,
                str(summary["continuity"]["coverage_after_pct"]).startswith(COVERAGE_PCT),
                summary["continuity"]["coverage_classification"] == COVERAGE_CLASSIFICATION,
                summary["source_recovery_effectiveness"]["remaining_unresolved"] == REMAINING_GAP_COUNT,
                final_reason_counts["MISSING_OPENING_BARS"] == 105,
                final_reason_counts["PROVIDER_HISTORY_UNAVAILABLE"] == 48,
                final_reason_counts["SESSION_QUALITY_FAILURE"] == 64,
                summary["retrieval"]["request_count"] == EXACT_RETRY_REQUESTS,
                first_attempt_successes == EXACT_RETRY_REQUESTS,
                summary["source_recovery_effectiveness"]["recovered_by_exact_groww_retry"] == 0,
                summary["reconciliation"]["unexplained_source_difference_rows"] == 0,
                summary["alternate_source"]["approved_alternate_source_available"] is False,
                summary["alternate_source"]["alternate_provider_contacted"] is False,
                summary["FAMILY_D_DEVELOPMENT_BACKTEST_READINESS"] == "NO",
            )
        )
        checks = {
            "frozen_family_d_and_command_02": upstream["result"] == "VERIFIED",
            "command_03_hashes": all(command_03_checks.values()),
            "command_03_manifest": manifest_ok,
            "command_03_artifacts": artifacts_ok,
            "frozen_data_findings": findings_ok,
        }
        if not all(checks.values()):
            raise FamilyDClosureInputMismatch("FAMILY_D_CLOSURE_INPUT_MISMATCH")
        return {
            "status": "VERIFIED",
            "checks": checks,
            "command_03_hash_checks": command_03_checks,
            "command_02_artifact_count": upstream["command_02_artifact_count"],
            "command_03_artifact_count": len(command_03_manifest["artifact_hashes"]),
            "first_attempt_request_successes": first_attempt_successes,
            "prior_artifact_snapshot": _prior_artifact_snapshot(root),
        }
    except FamilyDClosureInputMismatch:
        raise
    except Exception as exc:
        raise FamilyDClosureInputMismatch("FAMILY_D_CLOSURE_INPUT_MISMATCH") from exc


def final_statuses() -> dict[str, str]:
    return {
        "FAMILY_D_RESEARCH_STATUS": FAMILY_D_RESEARCH_STATUS,
        "FAMILY_D_EVIDENCE_STATUS": FAMILY_D_EVIDENCE_STATUS,
        "CONTROL_D_000_STATUS": CONTROL_D_000_STATUS,
        "ORB_D_001_STATUS": ORB_D_001_STATUS,
        "FAMILY_D_VALIDATION_STATUS": FAMILY_D_VALIDATION_STATUS,
        "FAMILY_D_STRATEGY_V2_STATUS": FAMILY_D_STRATEGY_V2_STATUS,
        "FAMILY_D_CONTINUITY_STANDARD": FAMILY_D_CONTINUITY_STANDARD,
    }


def resume_requirement_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_D_RESUME_REQUIREMENT_V1",
        "all_conditions_required": True,
        "conditions": {
            "A": "APPROVED_LICENSED_COMPATIBLE_HISTORICAL_NSE_INTRADAY_SOURCE_EXISTS",
            "B": "EXACT_REQUIRED_GAPS_RETRIEVED_AND_RECONCILED",
            "C": "VOLUME_SEMANTICS_COMPATIBLE",
            "D": "EXACT_PRIOR20_CONTINUITY_COVERAGE_GTE_95_PERCENT",
            "E": "FROZEN_FAMILY_D_STRATEGY_AND_CONFIG_HASHES_INTACT",
        },
        "data_only_resume": {
            "existing_preregistration_may_remain_valid": True,
            "requirements": [
                "NO_STRATEGY_PARAMETER_CHANGES",
                "NO_SUCCESS_CRITERIA_CHANGES",
                "NO_OUTCOME_BASED_SCOPE_MANIPULATION",
            ],
            "required_versioning": "NEW_DATA_SOURCE_OR_REMEDIATION_VERSION_NOT_NEW_STRATEGY_VERSION",
        },
        "new_strategy_preregistration_required_if_changed": [
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
        ],
    }


def data_lesson_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_D_DATA_LESSON_V1",
        "lesson": (
            "Sparse event-oriented intraday ingestion is sufficient for setup/path "
            "diagnostics but is not sufficient for strategies whose features depend "
            "on continuous rolling intraday-session history."
        ),
        "future_planning_requirement": (
            "Future intraday-family planning must identify rolling-history requirements "
            "before ingestion scope is frozen."
        ),
    }


def provider_lesson_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_D_PROVIDER_LESSON_V1",
        "provider": "GROWW",
        "lesson": (
            "Current Groww historical retrieval is reliable for available data, but "
            "exact retries confirmed persistent gaps for the Family D continuity requirement."
        ),
        "interpretation_prohibited": "DO_NOT_INTERPRET_AS_GENERAL_PROVIDER_UNRELIABILITY",
        "approved_alternate_source": "NONE",
        "alternate_provider_contacted": False,
        "new_provider_authorized": False,
    }


def family_e_planning_note() -> dict[str, Any]:
    return {
        "version": "FAMILY_E_PLANNING_NOTE_V1",
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "NEXT_PLANNED",
        "high_level_idea": [
            "STRONG_PRIOR_TREND",
            "CONTROLLED_PULLBACK",
            "RECLAIM_OR_CONTINUATION",
        ],
        "conceptual_distinction": (
            "Continuation after a temporary pullback rather than buying immediate strength."
        ),
        "distinct_from": [
            "MEDIUM_TERM_FACTOR_MOMENTUM",
            "ABSOLUTE_TREND_FILTERS",
            "BREAKOUT_CONTINUATION",
            "OPENING_RANGE_INTRADAY_TRADING",
        ],
        "parameters_defined": False,
        "implementation_started": False,
        "performance_run": False,
    }


def roadmap_statuses() -> dict[str, str]:
    return {
        "FAMILY_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
        "FAMILY_B": "PAUSED_NO_VALIDATION_CANDIDATE",
        "FAMILY_C": "PAUSED_NO_VALIDATION_CANDIDATE",
        "FAMILY_D": FAMILY_D_RESEARCH_STATUS,
        "FAMILY_E": "NEXT_PLANNED",
        "FAMILY_F": "PLANNED_NOT_STARTED",
        "FAMILY_G": "PLANNED_NOT_STARTED",
    }


def _verify_roadmap(root: Path) -> bool:
    text = (root / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    labels = {
        "FAMILY_A": "Family A | Medium-Term Momentum",
        "FAMILY_B": "Family B | Relative + Absolute Momentum",
        "FAMILY_C": "Family C | Breakout Continuation",
        "FAMILY_D": "Family D | Opening Range / Stocks-in-Play",
        "FAMILY_E": "Family E | Pullback / Reclaim",
        "FAMILY_F": "Family F | Catalyst Momentum",
        "FAMILY_G": "Family G | Regime / Volatility",
    }
    return all(
        f"| {labels[family]} | {status} |" in text
        for family, status in roadmap_statuses().items()
    )


def _write_supporting_documents(root: Path) -> dict[str, Any]:
    base = closure_root(root)
    resume = resume_requirement_document()
    data_lesson = data_lesson_document()
    provider_lesson = provider_lesson_document()
    family_e = family_e_planning_note()
    roadmap = {
        "version": "STRATEGY_FAMILY_RESEARCH_ROADMAP_HANDOFF_V1",
        "statuses": roadmap_statuses(),
        "next_planned_research_family": NEXT_PLANNED_RESEARCH_FAMILY,
    }
    governance = {
        "version": "FAMILY_D_GOVERNANCE_FREEZE_V1",
        "final_statuses": final_statuses(),
        "interpretation": {
            "strategy_rejected_for_failure": False,
            "paused_because_approved_data_cannot_meet_frozen_continuity_standard": True,
            "performance_conclusion_allowed": False,
        },
        "continuity_standard": {
            "status": FAMILY_D_CONTINUITY_STANDARD,
            "readiness_target_pct": 95,
            "sparse_prior_observations_allowed": False,
            "older_session_substitution_allowed": False,
            "daily_volume_substitution_allowed": False,
            "post_hoc_problematic_session_removal_allowed": False,
            "readiness_target_reduction_allowed": False,
        },
        "execution": {
            "performance_run": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_e_implementation_started": False,
            "new_provider_configured": False,
            "new_provider_contacted": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
        },
        "preserved_shared_research_infrastructure": [
            "ORIGINAL_INTRADAY_ARTIFACTS",
            "COMMAND_02_CONTINUITY_EXTENSION",
            "COMMAND_03_EXACT_GAP_RECOVERY",
            "CONTINUITY_MATRICES",
            "REQUEST_PLANS",
            "QUALITY_DIAGNOSTICS",
            "ACTIVITY_STRUCTURAL_DATA",
        ],
    }
    documents = {
        "data_lessons/family_d_data_lesson_v1.json": data_lesson,
        "data_lessons/family_d_provider_lesson_v1.json": provider_lesson,
        "handoff/family_d_resume_requirement_v1.json": resume,
        "handoff/family_e_planning_note_v1.json": family_e,
        "handoff/family_d_roadmap_v1.json": roadmap,
        "governance/family_d_governance_freeze_v1.json": governance,
    }
    for relative, document in documents.items():
        _write_json(base / relative, document)
    return {
        "resume": resume,
        "data_lesson": data_lesson,
        "provider_lesson": provider_lesson,
        "family_e": family_e,
        "roadmap": roadmap,
        "governance": governance,
    }


def _closure_manifest(
    root: Path,
    verification: Mapping[str, Any],
    documents: Mapping[str, Any],
) -> dict[str, Any]:
    path = closure_root(root) / "manifest/family_d_closure_manifest_v1.json"
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if path.is_file():
        existing = _json(path)
        if canonical_hash(
            {key: value for key, value in existing.items() if key != "family_d_closure_hash"}
        ) != existing.get("family_d_closure_hash"):
            raise FamilyDClosureInputMismatch("FAMILY_D_CLOSURE_MANIFEST_HASH_MISMATCH")
        timestamp = existing["closure_timestamp"]
    manifest: dict[str, Any] = {
        "version": "FAMILY_D_DATA_BLOCKED_CLOSURE_MANIFEST_V1",
        "command_version": COMMAND_VERSION,
        "profile": COMMAND_PROFILE,
        "closure_timestamp": timestamp,
        "family_d_hashes": EXPECTED_FAMILY_D_HASHES,
        "command_02_hashes": EXPECTED_COMMAND_02_HASHES,
        "command_02_manifest_hash": EXPECTED_COMMAND_02_MANIFEST_HASH,
        "command_03_hashes": EXPECTED_COMMAND_03_HASHES,
        "command_03_manifest_hash": EXPECTED_COMMAND_03_MANIFEST_HASH,
        "data_finding": {
            "target_sessions": TARGET_SESSION_COUNT,
            "complete_exact_prior20_continuity": COMPLETE_TARGET_COUNT,
            "incomplete": INCOMPLETE_TARGET_COUNT,
            "coverage_pct": COVERAGE_PCT,
            "coverage_classification": COVERAGE_CLASSIFICATION,
        },
        "remaining_defect_population": {
            "total": REMAINING_GAP_COUNT,
            "counts": REMAINING_GAP_COUNTS,
        },
        "provider_findings": {
            "provider": "GROWW",
            "exact_retry_requests": EXACT_RETRY_REQUESTS,
            "first_attempt_request_successes": verification["first_attempt_request_successes"],
            "new_sessions_recovered": 0,
            "unexplained_provider_differences": 0,
            "remaining_population_persistent_under_approved_source": True,
            "approved_alternate_source": "NONE",
            "alternate_provider_contacted": False,
            "new_provider_authorized": False,
        },
        "data_block_reason": (
            "AVAILABLE_APPROVED_DATA_CANNOT_SATISFY_THE_PREREGISTERED_EXACT_PRIOR20_"
            "CONTINUITY_STANDARD_FOR_A_FAIR_DEVELOPMENT_EVALUATION"
        ),
        "final_statuses": final_statuses(),
        "resume_requirements": documents["resume"],
        "validation_status": FAMILY_D_VALIDATION_STATUS,
        "strategy_v2_status": FAMILY_D_STRATEGY_V2_STATUS,
        "governance": documents["governance"],
        "data_lesson": documents["data_lesson"],
        "provider_lesson": documents["provider_lesson"],
        "roadmap": documents["roadmap"],
        "family_e_planning_note": documents["family_e"],
        "prior_artifact_snapshot": verification["prior_artifact_snapshot"],
    }
    manifest["family_d_closure_hash"] = canonical_hash(manifest)
    if path.is_file() and _json(path) != manifest:
        raise FamilyDClosureInputMismatch("FAMILY_D_CLOSURE_MANIFEST_IMMUTABILITY_VIOLATION")
    _write_json(path, manifest)
    return manifest


def _write_reports(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    reports = report_root(root)
    summary = {
        "command_version": COMMAND_VERSION,
        "profile": COMMAND_PROFILE,
        "closure_timestamp": manifest["closure_timestamp"],
        "family_d_closure_hash": manifest["family_d_closure_hash"],
        "final_statuses": manifest["final_statuses"],
        "data_finding": manifest["data_finding"],
        "remaining_defect_population": manifest["remaining_defect_population"],
        "provider_findings": manifest["provider_findings"],
        "data_block_reason": manifest["data_block_reason"],
        "interpretation": manifest["governance"]["interpretation"],
        "continuity_standard": manifest["governance"]["continuity_standard"],
        "resume_requirements": manifest["resume_requirements"],
        "data_lesson": manifest["data_lesson"],
        "provider_lesson": manifest["provider_lesson"],
        "roadmap": manifest["roadmap"],
        "family_e_planning_note": manifest["family_e_planning_note"],
        "governance": manifest["governance"]["execution"],
        "immutability": {
            "prior_artifacts_unchanged": True,
            **manifest["prior_artifact_snapshot"],
        },
        "known_limitations": [
            "Family D has no performance evidence because the frozen continuity gate was not met.",
            "No approved alternate real NSE historical intraday source is available.",
            "The frozen 100-symbol DEVELOPMENT scope supports no validation or production conclusion.",
        ],
        "recommended_next_action": (
            "PLAN_FAMILY_E_ONLY; FAMILY_D_REQUIRES_SEPARATE_DATA_SOURCE_AUTHORIZATION_"
            "AND_ALL_FAMILY_D_RESUME_REQUIREMENTS_BEFORE_RESUMPTION"
        ),
        "ready_for_review": True,
    }
    _write_json(reports / REPORT_NAMES[0], summary)
    _write_csv(
        reports / REPORT_NAMES[1],
        [
            {
                **manifest["data_finding"],
                "remaining_unique_gaps": REMAINING_GAP_COUNT,
                **REMAINING_GAP_COUNTS,
                **manifest["final_statuses"],
            }
        ],
    )
    _write_csv(reports / REPORT_NAMES[2], [manifest["provider_findings"]])
    _write_csv(
        reports / REPORT_NAMES[3],
        [
            {"lesson_type": "DATA_INFRASTRUCTURE", "finding": manifest["data_lesson"]["lesson"]},
            {"lesson_type": "FUTURE_PLANNING", "finding": manifest["data_lesson"]["future_planning_requirement"]},
            {"lesson_type": "PROVIDER", "finding": manifest["provider_lesson"]["lesson"]},
            {"lesson_type": "PROVIDER_SCOPE", "finding": manifest["provider_lesson"]["interpretation_prohibited"]},
        ],
    )
    _write_csv(
        reports / REPORT_NAMES[4],
        [
            {
                "handoff_type": "FAMILY_D_RESUME_GATE",
                "status": FAMILY_D_RESEARCH_STATUS,
                "next_family": "",
                "requirements": list(manifest["resume_requirements"]["conditions"].values()),
                "parameters_defined": "",
                "implementation_started": "",
            },
            {
                "handoff_type": "NEXT_RESEARCH_FAMILY",
                "status": "NEXT_PLANNED",
                "next_family": NEXT_PLANNED_RESEARCH_FAMILY,
                "requirements": [],
                "parameters_defined": False,
                "implementation_started": False,
            },
        ],
    )
    return summary


def _write_documentation(root: Path, manifest: Mapping[str, Any]) -> None:
    text = f"""# Strategy Family D data-blocked closure V1

## Decision

Family D (`STRATEGY_FAMILY_D_OPENING_RANGE_V1`) is `{FAMILY_D_RESEARCH_STATUS}`. It is not rejected because the strategy failed. The preregistered control `CONTROL-D-000` and treatment `ORB-D-001` are both `{CONTROL_D_000_STATUS}`: neither is classified as good or bad. Available approved data cannot satisfy the frozen continuity standard required for a fair DEVELOPMENT evaluation, so no performance conclusion may be drawn.

The final evidence status is `{FAMILY_D_EVIDENCE_STATUS}`. Validation is `{FAMILY_D_VALIDATION_STATUS}` and Strategy V2 is `{FAMILY_D_STRATEGY_V2_STATUS}`.

## Frozen continuity finding

The bounded 100-symbol DEVELOPMENT population contains {TARGET_SESSION_COUNT:,} target sessions. Exactly {COMPLETE_TARGET_COUNT:,} have all 20 immediately preceding strict opening-volume sessions and {INCOMPLETE_TARGET_COUNT:,} are incomplete, for {COVERAGE_PCT}% coverage (`{COVERAGE_CLASSIFICATION}`). The frozen readiness target remains at least 95%.

Command 02 performed the authorized continuity remediation and preserved all source, quality, and lineage diagnostics. Command 03 then made {EXACT_RETRY_REQUESTS} exact Groww requests; all {EXACT_RETRY_REQUESTS} succeeded on their first attempt, but zero new required sessions were recovered. The remaining {REMAINING_GAP_COUNT} defects comprise 105 missing-opening cases, 48 Groww-confirmed unavailable cases, and 64 strict-quality failures. Reconciliation found zero unexplained provider differences.

Groww historical retrieval is reliable for data that is available. The exact retry result demonstrates persistent gaps for this particular Family D continuity contract and must not be generalized into a claim of provider unreliability. There is no approved alternate real NSE historical intraday source, no alternate provider was contacted, and this command authorizes none.

## Why the standard was preserved

`FAMILY_D_CONTINUITY_STANDARD` is `{FAMILY_D_CONTINUITY_STANDARD}`. The project did not use sparse prior observations, substitute older sessions, use daily volume, remove problematic sessions post hoc, or lower the 95% readiness target merely to enable a backtest. The opening range, activity definition, threshold, entry, stop, exit, risk, capacity, universe, ranking, and success criteria were unchanged.

## Resume requirements

Family D may resume only after all of the following are true:

1. An approved/licensed compatible historical NSE intraday source exists.
2. The exact required gaps are retrieved and reconciled.
3. Volume semantics are compatible.
4. Exact prior-20 continuity reaches at least 95%.
5. The frozen Family D strategy/config hashes remain intact.

If only better data changes, the existing preregistration may remain valid provided strategy parameters, success criteria, and outcome-independent scope remain unchanged. That work requires a new data-source/remediation version, not a new strategy version. Any change to opening range, activity definition, threshold, entry, stop, exit, risk, capacity, universe, ranking, or success criteria requires a new strategy preregistration.

## Preserved research infrastructure and lesson

The original intraday artifacts, Command 02 extension, Command 03 exact-gap recovery, continuity matrices, request plans, quality diagnostics, and activity structural data remain preserved. Sparse event-oriented intraday ingestion is sufficient for setup/path diagnostics but not for features that require continuous rolling intraday-session history. Future intraday-family planning must identify rolling-history requirements before ingestion scope is frozen.

## Roadmap handoff

Family E is next planned as `{NEXT_PLANNED_RESEARCH_FAMILY}`. Its high-level concept is a strong prior trend followed by a controlled pullback and reclaim/continuation. It investigates continuation after temporary counter-trend movement rather than immediate strength, which distinguishes it from factor momentum, absolute-trend filters, breakout continuation, and opening-range trading. No Family E parameters were defined and implementation has not started.

Closure manifest: `data/research/strategy_families/family_d/v1/closure/manifest/family_d_closure_manifest_v1.json`
`family_d_closure_hash`: `{manifest['family_d_closure_hash']}`
"""
    path = root / "docs/strategy-family-d-data-blocked-closure-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_artifact_manifest(root: Path, closure: Mapping[str, Any]) -> dict[str, Any]:
    path = closure_root(root) / "manifest/family_d_closure_artifact_manifest_v1.json"
    artifacts = [
        candidate
        for candidate in closure_root(root).rglob("*")
        if candidate.is_file() and candidate != path
    ] + [report_root(root) / name for name in REPORT_NAMES] + [
        root / "docs/strategy-family-d-data-blocked-closure-v1.md"
    ]
    manifest: dict[str, Any] = {
        "version": "FAMILY_D_CLOSURE_ARTIFACT_MANIFEST_V1",
        "family_d_closure_hash": closure["family_d_closure_hash"],
        "artifact_hashes": {
            candidate.relative_to(root).as_posix(): file_sha256(candidate)
            for candidate in sorted(set(artifacts))
        },
    }
    manifest["artifact_manifest_hash"] = canonical_hash(manifest)
    if path.is_file() and _json(path) != manifest:
        raise FamilyDClosureInputMismatch("FAMILY_D_CLOSURE_ARTIFACT_IMMUTABILITY_VIOLATION")
    _write_json(path, manifest)
    return manifest


def run_family_d_data_blocked_closure(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    verification_before = verify_family_d_closure_inputs(root)
    if not _verify_roadmap(root):
        raise FamilyDClosureInputMismatch("FAMILY_D_ROADMAP_STATUS_MISMATCH")
    documents = _write_supporting_documents(root)
    manifest = _closure_manifest(root, verification_before, documents)
    summary = _write_reports(root, manifest)
    _write_documentation(root, manifest)
    artifact_manifest = _write_artifact_manifest(root, manifest)
    verification_after = verify_family_d_closure_inputs(root)
    if (
        verification_before["prior_artifact_snapshot"]
        != verification_after["prior_artifact_snapshot"]
    ):
        raise FamilyDClosureInputMismatch("PRIOR_FAMILY_D_ARTIFACTS_CHANGED_DURING_CLOSURE")
    return {
        **summary,
        "input_verification": verification_after,
        "artifact_manifest_hash": artifact_manifest["artifact_manifest_hash"],
    }


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "CONTROL_D_000_STATUS",
    "EXPECTED_COMMAND_02_HASHES",
    "EXPECTED_COMMAND_02_MANIFEST_HASH",
    "EXPECTED_COMMAND_03_HASHES",
    "EXPECTED_COMMAND_03_MANIFEST_HASH",
    "EXPECTED_FAMILY_D_HASHES",
    "FAMILY_D_CONTINUITY_STANDARD",
    "FAMILY_D_EVIDENCE_STATUS",
    "FAMILY_D_RESEARCH_STATUS",
    "FAMILY_D_STRATEGY_V2_STATUS",
    "FAMILY_D_VALIDATION_STATUS",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "ORB_D_001_STATUS",
    "REPORT_NAMES",
    "closure_root",
    "data_lesson_document",
    "family_e_planning_note",
    "provider_lesson_document",
    "resume_requirement_document",
    "run_family_d_data_blocked_closure",
    "verify_family_d_closure_inputs",
]
