from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_f_catalyst_data_readiness import (
    EXPECTED_FAMILY_E_CLOSURE_HASH,
    HISTORICAL_EARNINGS_SURPRISE_READINESS,
    verify_family_e_closure,
)
from app.research.strategy.family_f_data_source_closure import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    FAMILY_F_EVIDENCE_STATUS,
    FAMILY_F_PERFORMANCE_STATUS,
    FAMILY_F_PREREGISTRATION_STATUS,
    FAMILY_F_RESEARCH_STATUS,
    FAMILY_F_STRATEGY_V2_STATUS,
    FAMILY_F_VALIDATION_STATUS,
    LICENSE_GATE_VERSION,
    MANIFEST_VERSION,
    NEGATIVE_EVIDENCE_ID,
    NEXT_PLANNED_RESEARCH_FAMILY,
    POSITIVE_EVIDENCE_ID,
    REPORT_NAMES,
    RESUME_REQUIREMENT_VERSION,
    ROADMAP_STATUSES,
    SOURCE_LESSON_VERSION,
    prior_artifact_snapshot,
    verify_command_02,
)
from app.research.strategy.family_f_official_source_pilot import verify_command_01
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = REPO_ROOT / "data/research/strategy_families/family_f/closure/v1"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = (
    CLOSURE_ROOT / "manifest/family_f_data_source_closure_manifest_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_command_and_all_frozen_input_hashes_are_exact() -> None:
    assert COMMAND_VERSION == "FAMILY_F_DATA_SOURCE_CLOSURE_V1"
    assert COMMAND_PROFILE == "CATALYST_LICENSE_PENDING_RESEARCH_FREEZE_V1"
    assert MANIFEST_VERSION == "FAMILY_F_DATA_SOURCE_CLOSURE_MANIFEST_V1"
    command_01 = verify_command_01(REPO_ROOT)
    command_02 = verify_command_02(REPO_ROOT)
    family_e = verify_family_e_closure(REPO_ROOT)
    assert command_01["family_f_data_readiness_hash"] == (
        "45ce21fdbf020cd990bdd9ca727e0d278de1eb9d5132d3cba18a70fb72ca0765"
    )
    assert command_02["family_f_pilot_request_plan_hash"] == (
        "8522ea20315ca6632a75f06694c615b7dd1a0ff4526c5bddf4b78a585ca1a98d"
    )
    assert command_02["family_f_source_pilot_hash"] == (
        "6dbbaad6c347952ebead5e9312037ccc1fce49ade9d06e85a3784fcdfc9c29c3"
    )
    assert family_e["family_e_closure_hash"] == EXPECTED_FAMILY_E_CLOSURE_HASH


def test_final_statuses_freeze_pause_without_evaluation() -> None:
    statuses = _summary()["statuses"]
    assert statuses == {
        "FAMILY_F_RESEARCH_STATUS": FAMILY_F_RESEARCH_STATUS,
        "FAMILY_F_EVIDENCE_STATUS": FAMILY_F_EVIDENCE_STATUS,
        "FAMILY_F_PREREGISTRATION_STATUS": FAMILY_F_PREREGISTRATION_STATUS,
        "FAMILY_F_PERFORMANCE_STATUS": FAMILY_F_PERFORMANCE_STATUS,
        "FAMILY_F_VALIDATION_STATUS": FAMILY_F_VALIDATION_STATUS,
        "FAMILY_F_STRATEGY_V2_STATUS": FAMILY_F_STRATEGY_V2_STATUS,
        "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
    }
    assert FAMILY_F_RESEARCH_STATUS == "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE"
    assert FAMILY_F_PREREGISTRATION_STATUS == "NOT_READY"
    assert FAMILY_F_PERFORMANCE_STATUS == "NOT_EVALUATED"
    assert FAMILY_F_VALIDATION_STATUS == "NOT_ACCESSED"
    assert FAMILY_F_STRATEGY_V2_STATUS == "NOT_CREATED"


def test_nse_positive_data_evidence_is_preserved_exactly() -> None:
    evidence = _summary()["source_evidence"]["positive_evidence"]
    assert evidence["evidence_id"] == POSITIVE_EVIDENCE_ID
    assert evidence["pilot_result"] == "PILOT_CONDITIONAL"
    assert evidence["records_inspected"] == 21
    assert evidence["trusted_publication_timestamp_quality_percent"] == 95.24
    assert evidence["canonical_linkage_percent"] == 100.0
    assert evidence["stable_document_identity_percent"] == 100.0
    assert evidence["reproducible_retrieval_percent"] == 100.0
    assert evidence["status"] == "TECHNICALLY_SUITABLE_PENDING_AUTHORIZATION"
    assert evidence["performance_interpretation"] == "NONE"


def test_index_negative_evidence_is_data_only() -> None:
    evidence = _summary()["source_evidence"]["negative_evidence"]
    assert evidence["evidence_id"] == NEGATIVE_EVIDENCE_ID
    assert evidence["records_inspected"] == 6
    assert evidence["status"] == "TIMESTAMP_INSUFFICIENT_FOR_SAME_DAY_RESEARCH"
    assert "date-only" in evidence["finding"]
    assert evidence["economic_utility_conclusion"] == "NOT_EVALUATED"


def test_other_command_02_source_statuses_are_not_upgraded() -> None:
    statuses = {
        row["source"]: row["status"]
        for row in _summary()["source_evidence"]["other_source_statuses"]
    }
    assert statuses == {
        "NSE_FINANCIAL_RESULTS_XBRL": "INCONCLUSIVE",
        "NSE_INSIDER_BULK_BLOCK_ARCHIVES": "INCONCLUSIVE",
        "SEBI_ORDERS_AND_ACTIONS": "INCONCLUSIVE",
        "ICRA_RATING_RATIONALES": "INCONCLUSIVE",
        "CRISIL_RATING_DISCLOSURES": "ACCESS_RESTRICTED",
        "BSE_CORPORATE_ANNOUNCEMENTS": "ACCESS_RESTRICTED",
    }


def test_license_gate_blocks_public_web_workaround() -> None:
    gate = _summary()["license_gate"]
    assert gate["version"] == LICENSE_GATE_VERSION
    assert gate["status"] == "BLOCKING_HISTORICAL_ACQUISITION"
    assert len(gate["acquisition_may_proceed_after_any_one"]) == 3
    assert {row["gate_id"] for row in gate["acquisition_may_proceed_after_any_one"]} == {
        "A", "B", "C"
    }
    assert gate["restriction_bypass_permitted"] is False
    assert "not authorization" in gate["public_web_authorization_rule"]


def test_future_acquisition_requirements_and_architecture_are_design_only() -> None:
    handoff = _summary()["acquisition_handoff"]
    assert handoff["status"] == "DESIGN_ONLY_NOT_IMPLEMENTED"
    assert handoff["date_range"] == {"start": "2022-01-01", "end": "2024-12-31"}
    assert handoff["target_universe"] == "POINT_IN_TIME_NIFTY_500"
    quality = handoff["minimum_quality_requirements"]
    assert quality["trusted_publication_timestamp_percent"] == 95
    assert quality["canonical_linkage_percent"] == 95
    assert quality["stable_document_identity_percent"] == 95
    assert quality["reproducibility_percent"] == 95
    assert quality["immutable_provenance"] == "REQUIRED"
    assert quality["revision_handling"] == "REQUIRED"
    assert quality["authorization_or_licensing"] == "REQUIRED"
    assert handoff["future_architecture"][0] == "AUTHORIZED_SOURCE"
    assert handoff["future_architecture"][-1] == "FAMILY_F_RESEARCH_DATASET"
    assert handoff["historical_acquisition_executed"] is False


def test_text_classification_and_leakage_rules_are_frozen() -> None:
    handoff = _summary()["acquisition_handoff"]
    classifier = handoff["text_classification"]
    assert classifier["TEXT_CLASSIFICATION_REQUIRED"] == "YES"
    assert classifier["classifier_implemented"] is False
    assert classifier["required_trace_fields"] == [
        "source_document_id",
        "raw_text_reference",
        "classifier_version",
        "confidence",
        "evidence_or_rationale",
    ]
    assert handoff["price_first_discovery_prohibited"] is True
    assert handoff["future_label_leakage_prohibited"] == [
        "LATER_ARTICLE", "ANALYST_INTERPRETATION", "REVISED_FILING",
        "SUBSEQUENT_PRICE_MOVEMENT",
    ]


def test_lesson_and_all_nine_resume_requirements_are_frozen() -> None:
    lesson = _summary()["source_lesson"]
    resume = _summary()["resume_requirements"]
    assert lesson["version"] == SOURCE_LESSON_VERSION
    assert lesson["family_pause_reason"] == "SOURCE_AUTHORIZATION_NOT_STRATEGY_FAILURE"
    assert lesson["catalyst_momentum_performance_conclusion"] == "NONE"
    assert resume["version"] == RESUME_REQUIREMENT_VERSION
    assert resume["status"] == "ALL_REQUIRED_BEFORE_RESUME"
    assert len(resume["requirements"]) == 9
    assert all(row["met"] is False for row in resume["requirements"])


def test_roadmap_and_family_g_planning_note_are_exact() -> None:
    summary = _summary()
    assert summary["roadmap"] == ROADMAP_STATUSES
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    for status in ROADMAP_STATUSES.values():
        assert status in roadmap
    family_g = summary["family_g_planning"]
    assert family_g["NEXT_PLANNED_RESEARCH_FAMILY"] == NEXT_PLANNED_RESEARCH_FAMILY
    assert family_g["status"] == "PLANNING_NOTE_ONLY"
    assert family_g["principle"].endswith(
        "do not begin as another large multi-factor score."
    )
    assert all(
        family_g[field] is False
        for field in (
            "thresholds_defined", "weights_defined", "signals_defined",
            "position_sizing_defined", "entries_defined", "exits_defined",
            "experiments_defined", "implementation_started",
        )
    )


def test_no_strategy_performance_acquisition_network_or_external_effects() -> None:
    safety = _summary()["safety"]
    assert safety == {
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
    }
    source = (
        REPO_ROOT / "backend/app/research/strategy/family_f_data_source_closure.py"
    ).read_text(encoding="utf-8")
    assert not re.search(r"\b(?:CONTROL|CAT)-F-\d{3}\b", source)
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(name in module for module in imports for name in ("requests", "httpx"))
    assert not any("backtest" in module for module in imports)


def test_closure_manifest_hash_components_and_prior_artifacts_are_immutable() -> None:
    manifest = _json(MANIFEST_PATH)
    body = {key: value for key, value in manifest.items() if key != "family_f_closure_hash"}
    assert manifest["family_f_closure_hash"] == canonical_hash(body)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["closure_timestamp"].endswith("Z")
    for relative, expected in manifest["component_hashes"].items():
        assert file_sha256(REPO_ROOT / relative) == expected
    assert manifest["baseline"]["prior_command_artifact_snapshot"] == prior_artifact_snapshot(
        REPO_ROOT
    )


def test_reports_documentation_and_storage_layout_exist() -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert (
        REPO_ROOT / "docs/strategy-family-f-data-source-closure-v1.md"
    ).is_file()
    for directory in (
        "manifest", "evidence", "license_gate", "lessons",
        "resume_requirements", "handoff",
    ):
        assert (CLOSURE_ROOT / directory).is_dir()
