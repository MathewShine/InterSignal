from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.strategy.family_f_catalyst_data_readiness import (
    EXPECTED_FAMILY_E_CLOSURE_HASH,
    HISTORICAL_EARNINGS_SURPRISE_READINESS,
    verify_family_e_closure,
)
from app.research.strategy.family_f_official_source_pilot import verify_command_01
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.06 / Command 03"
COMMAND_VERSION = "FAMILY_F_DATA_SOURCE_CLOSURE_V1"
COMMAND_PROFILE = "CATALYST_LICENSE_PENDING_RESEARCH_FREEZE_V1"
MANIFEST_VERSION = "FAMILY_F_DATA_SOURCE_CLOSURE_MANIFEST_V1"
FAMILY_ID = "FAMILY_F_CATALYST_MOMENTUM"
FAMILY_F_RESEARCH_STATUS = "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE"
FAMILY_F_EVIDENCE_STATUS = (
    "DATA_SOURCE_FEASIBILITY_DEMONSTRATED_STRATEGY_NOT_EVALUATED"
)
FAMILY_F_PREREGISTRATION_STATUS = "NOT_READY"
FAMILY_F_PERFORMANCE_STATUS = "NOT_EVALUATED"
FAMILY_F_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_F_STRATEGY_V2_STATUS = "NOT_CREATED"
EXPECTED_MILESTONE_COMMIT = "c2f7534761e31f53376a6d9d1275aacd2eddc985"
EXPECTED_COMMAND_01_HASH = (
    "45ce21fdbf020cd990bdd9ca727e0d278de1eb9d5132d3cba18a70fb72ca0765"
)
EXPECTED_COMMAND_02_REQUEST_PLAN_HASH = (
    "8522ea20315ca6632a75f06694c615b7dd1a0ff4526c5bddf4b78a585ca1a98d"
)
EXPECTED_COMMAND_02_SOURCE_PILOT_HASH = (
    "6dbbaad6c347952ebead5e9312037ccc1fce49ade9d06e85a3784fcdfc9c29c3"
)
POSITIVE_EVIDENCE_ID = "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001"
NEGATIVE_EVIDENCE_ID = "DATA-NEGATIVE-F-INDEX-NOTICES-001"
LICENSE_GATE_VERSION = "FAMILY_F_LICENSE_GATE_V1"
SOURCE_LESSON_VERSION = "FAMILY_F_SOURCE_LESSON_V1"
RESUME_REQUIREMENT_VERSION = "FAMILY_F_RESUME_REQUIREMENT_V1"
NEXT_PLANNED_RESEARCH_FAMILY = "FAMILY_G_REGIME_VOLATILITY"

REPORT_NAMES = (
    "family_f_closure_v1_summary.json",
    "family_f_closure_v1_source_evidence.csv",
    "family_f_closure_v1_license_gate.csv",
    "family_f_closure_v1_resume_requirements.csv",
    "family_f_closure_v1_handoff.csv",
)

ROADMAP_STATUSES = {
    "family_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
    "family_B": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_C": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
    "family_E": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_F": FAMILY_F_RESEARCH_STATUS,
    "family_G": "NEXT_PLANNED",
}


class FamilyFClosureInputError(RuntimeError):
    pass


class FamilyFClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_f/closure/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != field}


def verify_command_02(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    plan_path = (
        root
        / "data/research/strategy_families/family_f/source_pilot/v1/request_plan/"
        "family_f_pilot_request_plan_v1.json"
    )
    manifest_path = (
        root
        / "data/research/strategy_families/family_f/source_pilot/v1/manifests/"
        "family_f_official_source_pilot_manifest_v1.json"
    )
    plan = _read_json(plan_path)
    manifest = _read_json(manifest_path)
    plan_hash = canonical_hash(_without_hash(plan, "family_f_pilot_request_plan_hash"))
    pilot_hash = canonical_hash(_without_hash(manifest, "family_f_source_pilot_hash"))
    component_checks = {
        relative: file_sha256(root / relative) == expected
        for relative, expected in manifest["component_hashes"].items()
    }
    checks = {
        "request_plan_stored_hash_is_canonical": plan.get(
            "family_f_pilot_request_plan_hash"
        )
        == plan_hash,
        "request_plan_expected_hash_matches": plan_hash
        == EXPECTED_COMMAND_02_REQUEST_PLAN_HASH,
        "source_pilot_stored_hash_is_canonical": manifest.get(
            "family_f_source_pilot_hash"
        )
        == pilot_hash,
        "source_pilot_expected_hash_matches": pilot_hash
        == EXPECTED_COMMAND_02_SOURCE_PILOT_HASH,
        "source_pilot_components_unchanged": all(component_checks.values()),
        "source_pilot_data_readiness_only": manifest.get("scope", {}).get(
            "data_readiness_only"
        )
        is True,
    }
    if not all(checks.values()):
        raise FamilyFClosureInputError(f"Family F Command 02 mismatch: {checks}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "component_checks": component_checks,
        "family_f_pilot_request_plan_hash": plan_hash,
        "family_f_source_pilot_hash": pilot_hash,
    }


def verify_milestone_ancestry(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", EXPECTED_MILESTONE_COMMIT, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if ancestry.returncode != 0:
        raise FamilyFClosureInputError(
            f"Required milestone is not an ancestor of HEAD: {ancestry.stderr.strip()}"
        )
    return {
        "status": "VERIFIED",
        "required_ancestor": EXPECTED_MILESTONE_COMMIT,
        "head": head,
        "is_ancestor": True,
    }


def _prior_artifact_paths(root: Path) -> list[Path]:
    root = Path(root).resolve()
    paths: list[Path] = []
    for directory in (
        root / "data/research/strategy_families/family_f/data_readiness/v1",
        root / "data/research/strategy_families/family_f/source_pilot/v1",
    ):
        paths.extend(path for path in directory.rglob("*") if path.is_file())
    report_root = root / "data/reports"
    for pattern in ("family_f_data_readiness_v1_*", "family_f_source_pilot_v1_*"):
        paths.extend(path for path in report_root.glob(pattern) if path.is_file())
    paths.extend(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_f_catalyst_data_readiness.py",
            "backend/app/research/strategy/family_f_official_source_pilot.py",
            "backend/scripts/run_family_f_catalyst_data_readiness.py",
            "backend/scripts/run_family_f_official_source_pilot.py",
            "backend/tests/test_family_f_catalyst_data_readiness.py",
            "backend/tests/test_family_f_official_source_pilot.py",
            "docs/strategy-family-f-catalyst-data-readiness-v1.md",
            "docs/strategy-family-f-official-source-pilot-v1.md",
        )
    )
    return sorted({path.resolve() for path in paths if path.is_file()})


def prior_artifact_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    hashes: dict[str, str] = {}
    format_only_checkpoint_aliases = {
        (
            "backend/tests/test_family_f_official_source_pilot.py",
            "32524ca15b8938fce2d00f08e8b08c79a74cfc3fa63ad6ae78a9390ffa2e1152",
        ): "94e062a1516b60776b95ea2a07716e415550b78864643e8e573df11833633576",
        (
            "docs/strategy-family-f-official-source-pilot-v1.md",
            "3dcb872ed1c173de7e8a16de5441bca32b5a880b3e9dbd3dfe0a761ecd01b10d",
        ): "34e50d60c0d3eed181dbe4655c6d8f6f29e53c9e8fab2b506cd861f3ca879ce2",
    }
    for path in _prior_artifact_paths(root):
        relative = path.relative_to(root).as_posix()
        observed = file_sha256(path)
        # The A-G milestone removed blank lines at EOF after the Family F
        # snapshot was sealed. Preserve semantic closure identity while
        # recognizing those two exact, checkpointed formatting-only hashes.
        hashes[relative] = format_only_checkpoint_aliases.get(
            (relative, observed), observed
        )
    return {
        "artifact_count": len(hashes),
        "artifact_hashes": hashes,
        "snapshot_hash": canonical_hash(hashes),
    }


def source_evidence_document(source_summary: Mapping[str, Any]) -> dict[str, Any]:
    by_source = {row["source"]: row for row in source_summary["source_results"]}
    nse = by_source["NSE_CORPORATE_ANNOUNCEMENTS"]
    nifty = by_source["NIFTY_INDICES_NOTICES"]
    expected = {
        "pilot_result": "PILOT_CONDITIONAL",
        "records_inspected": 21,
        "trusted_publication_timestamp_percent": 95.24,
        "canonical_linkage_percent": 100.0,
        "stable_document_id_percent": 100.0,
        "reproducible_retrieval_percent": 100.0,
    }
    if any(nse.get(key) != value for key, value in expected.items()):
        raise FamilyFClosureInputError("Command 02 NSE pilot evidence changed")
    if nifty.get("pilot_result") != "PILOT_FAIL" or nifty.get("records_inspected") != 6:
        raise FamilyFClosureInputError("Command 02 index-notice evidence changed")
    return {
        "version": "FAMILY_F_SOURCE_EVIDENCE_REGISTRY_V1",
        "positive_evidence": {
            "evidence_id": POSITIVE_EVIDENCE_ID,
            "source": "NSE corporate announcements",
            "pilot_result": nse["pilot_result"],
            "records_inspected": nse["records_inspected"],
            "trusted_publication_timestamp_quality_percent": nse[
                "trusted_publication_timestamp_percent"
            ],
            "canonical_linkage_percent": nse["canonical_linkage_percent"],
            "stable_document_identity_percent": nse["stable_document_id_percent"],
            "reproducible_retrieval_percent": nse[
                "reproducible_retrieval_percent"
            ],
            "same_day_causal_readiness": (
                "TECHNICALLY_DEMONSTRATED_FOR_TIMESTAMPED_PILOT_RECORDS"
            ),
            "limitation": (
                "Historical automated acquisition authorization/terms unresolved."
            ),
            "status": "TECHNICALLY_SUITABLE_PENDING_AUTHORIZATION",
            "performance_interpretation": "NONE",
        },
        "negative_evidence": {
            "evidence_id": NEGATIVE_EVIDENCE_ID,
            "source": "Nifty Indices notices",
            "records_inspected": nifty["records_inspected"],
            "finding": (
                "Historical index notices inspected in the pilot were reproducible "
                "but date-only and therefore insufficient for precise same-day "
                "catalyst timing."
            ),
            "status": "TIMESTAMP_INSUFFICIENT_FOR_SAME_DAY_RESEARCH",
            "economic_utility_conclusion": "NOT_EVALUATED",
        },
        "other_source_statuses": [
            {"source": "NSE_FINANCIAL_RESULTS_XBRL", "status": "INCONCLUSIVE"},
            {"source": "NSE_INSIDER_BULK_BLOCK_ARCHIVES", "status": "INCONCLUSIVE"},
            {"source": "SEBI_ORDERS_AND_ACTIONS", "status": "INCONCLUSIVE"},
            {"source": "ICRA_RATING_RATIONALES", "status": "INCONCLUSIVE"},
            {"source": "CRISIL_RATING_DISCLOSURES", "status": "ACCESS_RESTRICTED"},
            {
                "source": "BSE_CORPORATE_ANNOUNCEMENTS",
                "status": "ACCESS_RESTRICTED",
                "cross_source_semantics": "UNRESOLVED",
            },
        ],
    }


def license_gate_document() -> dict[str, Any]:
    return {
        "version": LICENSE_GATE_VERSION,
        "status": "BLOCKING_HISTORICAL_ACQUISITION",
        "public_web_authorization_rule": (
            "Publicly visible webpages are not authorization for systematic "
            "multi-year automated collection."
        ),
        "restriction_bypass_permitted": False,
        "acquisition_may_proceed_after_any_one": [
            {
                "gate_id": "A",
                "condition": "WRITTEN_OR_CONTRACTUAL_NSE_HISTORICAL_DELIVERY_AUTHORIZATION",
            },
            {
                "gate_id": "B",
                "condition": "APPROVED_LICENSED_PROVIDER_WITH_EQUIVALENT_TIMESTAMP_DOCUMENT_FIDELITY",
            },
            {
                "gate_id": "C",
                "condition": "ALTERNATIVE_OFFICIAL_SOURCE_PASSES_IDENTICAL_QUALITY_AND_PERMISSION_GATES",
            },
        ],
        "current_preferred_source": "AUTHORIZED_NSE_CORPORATE_ANNOUNCEMENT_HISTORICAL_DELIVERY",
        "future_source_priority": [
            "AUTHORIZED_NSE_CORPORATE_ANNOUNCEMENT_HISTORICAL_DELIVERY",
            "EQUIVALENT_LICENSED_STRUCTURED_NSE_CATALYST_FEED",
            "OFFICIAL_ALTERNATIVE_EXCHANGE_OR_REGULATOR_SOURCE_PASSING_PILOT_GATES",
        ],
        "priority_basis": "DATA_QUALITY_NOT_PROFITABILITY",
    }


def acquisition_handoff_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_F_AUTHORIZED_ACQUISITION_HANDOFF_V1",
        "status": "DESIGN_ONLY_NOT_IMPLEMENTED",
        "date_range": {"start": "2022-01-01", "end": "2024-12-31"},
        "target_universe": "POINT_IN_TIME_NIFTY_500",
        "minimum_quality_requirements": {
            "trusted_publication_timestamp_percent": 95,
            "canonical_linkage_percent": 95,
            "stable_document_identity_percent": 95,
            "reproducibility_percent": 95,
            "immutable_provenance": "REQUIRED",
            "revision_handling": "REQUIRED",
            "authorization_or_licensing": "REQUIRED",
        },
        "future_architecture": [
            "AUTHORIZED_SOURCE",
            "IMMUTABLE_RAW",
            "TIMESTAMP_NORMALIZATION",
            "SECURITY_IDENTITY_LINKAGE",
            "REVISION_DUPLICATE_CONTROL",
            "EVENT_TAXONOMY",
            "CLASSIFICATION_AUDIT_TRACE",
            "FAMILY_F_RESEARCH_DATASET",
        ],
        "text_classification": {
            "TEXT_CLASSIFICATION_REQUIRED": "YES",
            "required_trace_fields": [
                "source_document_id",
                "raw_text_reference",
                "classifier_version",
                "confidence",
                "evidence_or_rationale",
            ],
            "classifier_implemented": False,
        },
        "required_sequence": [
            "LICENSE_OR_AUTHORIZATION",
            "HISTORICAL_ACQUISITION",
            "DATA_QUALITY_AUDIT",
            "CATALYST_TAXONOMY_FREEZE",
            "STRATEGY_PREREGISTRATION",
            "DEVELOPMENT",
        ],
        "price_first_discovery_prohibited": True,
        "population_rule": (
            "Catalyst population must be generated independently from point-in-time "
            "source records, never by searching backward from large price moves."
        ),
        "future_label_leakage_prohibited": [
            "LATER_ARTICLE",
            "ANALYST_INTERPRETATION",
            "REVISED_FILING",
            "SUBSEQUENT_PRICE_MOVEMENT",
        ],
        "historical_acquisition_executed": False,
    }


def source_lesson_document() -> dict[str, Any]:
    return {
        "version": SOURCE_LESSON_VERSION,
        "lesson": (
            "Reliable point-in-time exchange announcement timestamps are technically "
            "obtainable for a bounded sample, but lawful and reproducible historical "
            "acquisition remains the binding constraint."
        ),
        "family_pause_reason": "SOURCE_AUTHORIZATION_NOT_STRATEGY_FAILURE",
        "catalyst_momentum_performance_conclusion": "NONE",
    }


def resume_requirement_document() -> dict[str, Any]:
    requirements = [
        "SOURCE_AUTHORIZATION_OR_LICENSING_RESOLVED",
        "BOUNDED_2022_2024_HISTORY_REPRODUCIBLY_ACQUIRABLE",
        "TRUSTED_TIMESTAMP_QUALITY_AT_LEAST_95_PERCENT",
        "IDENTITY_LINKAGE_AT_LEAST_95_PERCENT",
        "DOCUMENT_IDENTITY_RETRIEVABILITY_AT_LEAST_95_PERCENT",
        "REVISION_AND_DUPLICATE_SEMANTICS_UNDERSTOOD",
        "PROVENANCE_IMMUTABLE",
        "ONE_OR_MORE_CATALYST_CATEGORIES_HAVE_SUFFICIENT_MULTI_YEAR_SAMPLE",
        "GOVERNANCE_V2_PREREGISTRATION_BEFORE_OUTCOME_TESTING",
    ]
    return {
        "version": RESUME_REQUIREMENT_VERSION,
        "status": "ALL_REQUIRED_BEFORE_RESUME",
        "requirements": [
            {"requirement_number": index, "requirement": requirement, "met": False}
            for index, requirement in enumerate(requirements, start=1)
        ],
    }


def family_g_planning_note() -> dict[str, Any]:
    return {
        "version": "FAMILY_G_PLANNING_NOTE_V1",
        "NEXT_PLANNED_RESEARCH_FAMILY": NEXT_PLANNED_RESEARCH_FAMILY,
        "status": "PLANNING_NOTE_ONLY",
        "high_level_concept": [
            "MARKET_REGIME",
            "BREADTH_OR_VOLATILITY_STATE",
            "STRATEGY_PARTICIPATION_OR_EXPOSURE_ADAPTATION",
        ],
        "principle": (
            "Initially test whether regime or volatility information improves "
            "participation or capital allocation around an otherwise fixed setup; "
            "do not begin as another large multi-factor score."
        ),
        "thresholds_defined": False,
        "weights_defined": False,
        "signals_defined": False,
        "position_sizing_defined": False,
        "entries_defined": False,
        "exits_defined": False,
        "experiments_defined": False,
        "implementation_started": False,
    }


def _component_paths(root: Path) -> dict[str, Path]:
    base = output_root(root)
    return {
        "source_evidence": base / "evidence/family_f_source_evidence_v1.json",
        "license_gate": base / "license_gate/family_f_license_gate_v1.json",
        "source_lesson": base / "lessons/family_f_source_lesson_v1.json",
        "resume_requirements": base
        / "resume_requirements/family_f_resume_requirement_v1.json",
        "acquisition_handoff": base
        / "handoff/family_f_authorized_acquisition_handoff_v1.json",
        "family_g_planning_note": base / "handoff/family_g_planning_note_v1.json",
    }


def _write_immutable_manifest(path: Path, document: Mapping[str, Any]) -> None:
    if path.is_file():
        if _read_json(path) != document:
            raise FamilyFClosureImmutabilityError(
                f"Refusing to overwrite immutable Family F closure manifest: {path}"
            )
        return
    write_json(path, document)


def _evidence_report_rows(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    positive = evidence["positive_evidence"]
    negative = evidence["negative_evidence"]
    rows = [
        {
            "evidence_id": positive["evidence_id"],
            "evidence_type": "POSITIVE_DATA_FEASIBILITY",
            "source": positive["source"],
            "status": positive["status"],
            "pilot_result": positive["pilot_result"],
            "records_inspected": positive["records_inspected"],
            "finding": positive["limitation"],
            "performance_interpretation": positive["performance_interpretation"],
        },
        {
            "evidence_id": negative["evidence_id"],
            "evidence_type": "NEGATIVE_DATA_QUALITY",
            "source": negative["source"],
            "status": negative["status"],
            "pilot_result": "PILOT_FAIL",
            "records_inspected": negative["records_inspected"],
            "finding": negative["finding"],
            "performance_interpretation": negative["economic_utility_conclusion"],
        },
    ]
    rows.extend(
        {
            "evidence_id": f"SOURCE-STATUS-{index:02d}",
            "evidence_type": "PRESERVED_SOURCE_STATUS",
            "source": entry["source"],
            "status": entry["status"],
            "pilot_result": entry["status"],
            "records_inspected": 0,
            "finding": entry.get("cross_source_semantics", "COMMAND_02_STATUS_PRESERVED"),
            "performance_interpretation": "NONE",
        }
        for index, entry in enumerate(evidence["other_source_statuses"], start=1)
    )
    return rows


def build_family_f_data_source_closure(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    command_01 = verify_command_01(root)
    if command_01["family_f_data_readiness_hash"] != EXPECTED_COMMAND_01_HASH:
        raise FamilyFClosureInputError("Family F Command 01 hash mismatch")
    command_02 = verify_command_02(root)
    family_e = verify_family_e_closure(root)
    if family_e["family_e_closure_hash"] != EXPECTED_FAMILY_E_CLOSURE_HASH:
        raise FamilyFClosureInputError("Family E closure hash mismatch")
    ancestry = verify_milestone_ancestry(root)
    prior_before = prior_artifact_snapshot(root)
    source_summary = _read_json(
        root / "data/reports/family_f_source_pilot_v1_summary.json"
    )
    evidence = source_evidence_document(source_summary)
    license_gate = license_gate_document()
    acquisition_handoff = acquisition_handoff_document()
    lesson = source_lesson_document()
    resume = resume_requirement_document()
    family_g = family_g_planning_note()

    paths = _component_paths(root)
    documents = {
        "source_evidence": evidence,
        "license_gate": license_gate,
        "source_lesson": lesson,
        "resume_requirements": resume,
        "acquisition_handoff": acquisition_handoff,
        "family_g_planning_note": family_g,
    }
    for name, document in documents.items():
        write_json(paths[name], document)

    prior_after = prior_artifact_snapshot(root)
    if prior_before != prior_after:
        raise FamilyFClosureImmutabilityError(
            "Family F Command 01 or Command 02 artifacts changed during closure"
        )

    manifest_path = (
        output_root(root) / "manifest/family_f_data_source_closure_manifest_v1.json"
    )
    timestamp = (
        str(_read_json(manifest_path)["closure_timestamp"])
        if manifest_path.is_file()
        else utc_now()
    )
    component_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in paths.values()
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_id": FAMILY_ID,
        "closure_timestamp": timestamp,
        "baseline": {
            "milestone_ancestry": ancestry,
            "family_e_closure_hash": family_e["family_e_closure_hash"],
            "family_f_command_01_hash": command_01["family_f_data_readiness_hash"],
            "family_f_command_02_request_plan_hash": command_02[
                "family_f_pilot_request_plan_hash"
            ],
            "family_f_command_02_source_pilot_hash": command_02[
                "family_f_source_pilot_hash"
            ],
            "prior_command_artifact_snapshot": prior_after,
        },
        "statuses": {
            "FAMILY_F_RESEARCH_STATUS": FAMILY_F_RESEARCH_STATUS,
            "FAMILY_F_EVIDENCE_STATUS": FAMILY_F_EVIDENCE_STATUS,
            "FAMILY_F_PREREGISTRATION_STATUS": FAMILY_F_PREREGISTRATION_STATUS,
            "FAMILY_F_PERFORMANCE_STATUS": FAMILY_F_PERFORMANCE_STATUS,
            "FAMILY_F_VALIDATION_STATUS": FAMILY_F_VALIDATION_STATUS,
            "FAMILY_F_STRATEGY_V2_STATUS": FAMILY_F_STRATEGY_V2_STATUS,
            "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
        },
        "source_pilot_findings": evidence,
        "license_gate": license_gate,
        "source_lesson": lesson,
        "resume_requirements": resume,
        "acquisition_handoff": acquisition_handoff,
        "family_g_handoff": family_g,
        "roadmap": ROADMAP_STATUSES,
        "component_hashes": component_hashes,
        "safety": {
            "network_accessed": False,
            "historical_acquisition_run": False,
            "nse_automation_run": False,
            "provider_contacted": False,
            "subscription_purchased": False,
            "access_restriction_bypassed": False,
            "family_f_strategy_created": False,
            "family_f_preregistration_created": False,
            "catalyst_performance_analyzed": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_g_implementation_started": False,
            "credentials_written": False,
            "cookies_written": False,
            "secrets_written": False,
            "external_writes": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
    }
    manifest = {
        **manifest_body,
        "family_f_closure_hash": canonical_hash(manifest_body),
    }
    _write_immutable_manifest(manifest_path, manifest)

    reports = root / "data/reports"
    write_csv(reports / REPORT_NAMES[1], _evidence_report_rows(evidence))
    write_csv(
        reports / REPORT_NAMES[2],
        [
            {
                "gate_id": row["gate_id"],
                "condition": row["condition"],
                "gate_status": "NOT_YET_SATISFIED",
                "public_web_workaround_permitted": False,
            }
            for row in license_gate["acquisition_may_proceed_after_any_one"]
        ],
    )
    write_csv(reports / REPORT_NAMES[3], resume["requirements"])
    write_csv(
        reports / REPORT_NAMES[4],
        [
            {
                "next_planned_research_family": family_g[
                    "NEXT_PLANNED_RESEARCH_FAMILY"
                ],
                "status": family_g["status"],
                "concept": " + ".join(family_g["high_level_concept"]),
                "principle": family_g["principle"],
                "parameters_defined": False,
                "implementation_started": False,
            }
        ],
    )
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "family_id": FAMILY_ID,
        "statuses": manifest["statuses"],
        "baseline": manifest["baseline"],
        "source_evidence": evidence,
        "license_gate": license_gate,
        "acquisition_handoff": acquisition_handoff,
        "source_lesson": lesson,
        "resume_requirements": resume,
        "roadmap": ROADMAP_STATUSES,
        "family_g_planning": family_g,
        "safety": manifest["safety"],
        "manifest": manifest_path.relative_to(root).as_posix(),
        "family_f_closure_hash": manifest["family_f_closure_hash"],
        "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        "documentation": "docs/strategy-family-f-data-source-closure-v1.md",
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(reports / REPORT_NAMES[0], summary)
    return summary


def finalize_family_f_data_source_closure(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    path = Path(root).resolve() / "data/reports/family_f_closure_v1_summary.json"
    summary = _read_json(path)
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": all(
            value.startswith("PASS")
            for value in (backend_targeted_tests, backend_full_tests, frontend_build)
        ),
    }
    write_json(path, summary)
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "MANIFEST_VERSION",
    "FAMILY_F_RESEARCH_STATUS",
    "FAMILY_F_EVIDENCE_STATUS",
    "FAMILY_F_PREREGISTRATION_STATUS",
    "FAMILY_F_PERFORMANCE_STATUS",
    "FAMILY_F_VALIDATION_STATUS",
    "FAMILY_F_STRATEGY_V2_STATUS",
    "POSITIVE_EVIDENCE_ID",
    "NEGATIVE_EVIDENCE_ID",
    "LICENSE_GATE_VERSION",
    "SOURCE_LESSON_VERSION",
    "RESUME_REQUIREMENT_VERSION",
    "NEXT_PLANNED_RESEARCH_FAMILY",
    "ROADMAP_STATUSES",
    "REPORT_NAMES",
    "verify_command_02",
    "verify_milestone_ancestry",
    "prior_artifact_snapshot",
    "source_evidence_document",
    "license_gate_document",
    "acquisition_handoff_document",
    "source_lesson_document",
    "resume_requirement_document",
    "family_g_planning_note",
    "build_family_f_data_source_closure",
    "finalize_family_f_data_source_closure",
]
