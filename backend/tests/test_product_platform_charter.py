from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from app.research.strategy import product_platform_charter as charter
from app.research.strategy.family_a_momentum import file_sha256
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = charter.output_root(ROOT)
SUMMARY = json.loads(
    (ROOT / "data/reports/platform_charter_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
MANIFEST = json.loads(
    (
        ARTIFACT_ROOT
        / "manifests/intersignal_product_platform_charter_manifest_v1.json"
    ).read_text(encoding="utf-8")
)


def _json(relative: str) -> dict:
    return json.loads((ARTIFACT_ROOT / relative).read_text(encoding="utf-8"))


def _hash_without(document: dict, field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def test_command_manifest_and_upstream_hashes_are_exact() -> None:
    assert charter.COMMAND_VERSION == "INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_V1"
    assert charter.COMMAND_PROFILE == "MONTH_1_PLATFORM_SCOPE_FREEZE_V1"
    assert MANIFEST["manifest_version"] == (
        "INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_MANIFEST_V1"
    )
    assert MANIFEST["post_research_program_review_hash"] == (
        "a152b0e489005ecb506887082c99bee35a8e3c77e199f4c0ada2d7e0089a18cc"
    )
    assert MANIFEST["family_a_post_validation_closure_hash"] == (
        "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"
    )
    assert _hash_without(MANIFEST, "product_platform_charter_hash") == MANIFEST[
        "product_platform_charter_hash"
    ]
    assert MANIFEST["product_platform_charter_hash"] == (
        "3bdf3224c6ca21c06c261bf673b76e164e6d0788b204b2875122dad878d9263b"
    )


def test_product_vision_and_all_ten_modules_are_frozen() -> None:
    vision = _json("architecture/product_vision_v1.json")
    priorities = _json("modules/module_priorities_v1.json")
    assert vision["product_framing"] == "InterSignal = Investment Intelligence Platform"
    assert vision["core_domains"] == ["TRADE", "INVEST", "RESEARCH"]
    assert vision["architecture_principle"] == "LOOSELY_COUPLED_ADAPTER_DRIVEN"
    assert [(row["module_id"], row["module"]) for row in priorities["modules"]] == [
        ("A", "RESEARCH_WORKBENCH"),
        ("B", "PORTFOLIO_OS_FOUNDATION"),
        ("C", "DATA_LINEAGE_PROVENANCE"),
        ("D", "STRATEGY_EVIDENCE_REGISTRY"),
        ("E", "PORTFOLIO_RISK_ANALYTICS"),
        ("F", "SHADOW_OBSERVATION_FRAMEWORK_DESIGN"),
        ("G", "BROKER_ABSTRACTION_DESIGN"),
        ("H", "DATA_INGESTION_OBSERVABILITY"),
        ("I", "GOVERNANCE_AUDIT_UI"),
        ("J", "ALERT_MONITORING_FOUNDATION"),
    ]
    assert all(row["implementation_started"] is False for row in priorities["modules"])


def test_priority_classifications_and_deferred_scope_are_exact() -> None:
    priorities = _json("modules/module_priorities_v1.json")
    by_priority = {
        level: [
            row["module"] for row in priorities["modules"] if row["priority"] == level
        ]
        for level in ("P0", "P1", "P2")
    }
    assert by_priority == {
        "P0": [
            "RESEARCH_WORKBENCH",
            "PORTFOLIO_OS_FOUNDATION",
            "DATA_LINEAGE_PROVENANCE",
            "STRATEGY_EVIDENCE_REGISTRY",
        ],
        "P1": [
            "PORTFOLIO_RISK_ANALYTICS",
            "SHADOW_OBSERVATION_FRAMEWORK_DESIGN",
            "DATA_INGESTION_OBSERVABILITY",
            "GOVERNANCE_AUDIT_UI",
        ],
        "P2": ["BROKER_ABSTRACTION_DESIGN", "ALERT_MONITORING_FOUNDATION"],
    }
    assert priorities["priority_order"] == ["P0", "P1", "P2", "DEFERRED"]
    assert tuple(row["scope_id"] for row in priorities["deferred"]) == (
        charter.DEFERRED_MODULES
    )
    assert all(row["priority"] == "DEFERRED" for row in priorities["deferred"])


def test_non_goals_freeze_strategy_execution_and_data_acquisition() -> None:
    non_goals = _json("governance/month_1_non_goals_v1.json")
    assert set(non_goals["non_goals"]) == {
        "PRODUCTION_TRADING",
        "AUTONOMOUS_EXECUTION",
        "NEW_ALPHA_DISCOVERY",
        "FAMILY_H",
        "STRATEGY_V2",
        "AUTO_OPTIMIZING_INDICATORS",
        "UNRESTRICTED_AI_STRATEGY_GENERATION",
        "FAMILY_D_OR_F_DATA_ACQUISITION",
        "LIVE_CAPITAL_DEPLOYMENT",
    }
    assert non_goals["month_2_started"] is False


def test_lineage_domain_and_registry_models_are_complete() -> None:
    lineage = _json("lineage/data_lineage_spec_v1.json")
    evidence = _json("governance/evidence_registry_spec_v1.json")
    strategy = _json("governance/strategy_registry_spec_v1.json")
    domain = _json("domain_model/canonical_domain_model_v1.json")
    assert tuple(lineage["stages"]) == charter.LINEAGE_STAGES
    assert lineage["rule"] == (
        "EVERY_DERIVED_OBJECT_MUST_RETAIN_UPSTREAM_PROVENANCE"
    )
    assert tuple(evidence["classifications"]) == charter.EVIDENCE_CLASSIFICATIONS
    assert "EVIDENCE-C-COMPRESSION-001" in evidence[
        "preserved_a_to_g_evidence_ids"
    ]
    assert evidence["family_c_canonical_observation_id"] == (
        "EDGE-EVIDENCE-C-COMPRESSION-001"
    )
    assert tuple(strategy["lifecycle"]) == charter.STRATEGY_LIFECYCLE
    assert strategy["current_families_upgraded"] is False
    assert strategy["production_candidates_created"] == 0
    assert {"Research", "Portfolio", "Data", "Broker", "Operations"} == set(
        domain["entities"]
    )


def test_shadow_and_broker_are_design_only() -> None:
    shadow = _json("shadow/shadow_mode_governance_v1.json")
    broker = _json("broker/broker_abstraction_contract_v1.json")
    assert shadow["mode"] == "RESEARCH_SHADOW_MODE"
    assert shadow["status"] == "DESIGN_ONLY_NOT_ACTIVATED"
    assert shadow["family_a"]["status"] == "FROZEN_RESEARCH_BENCHMARK"
    assert shadow["family_a"]["production_candidate"] is False
    assert shadow["family_c"] == {
        "evidence_id": "EDGE-EVIDENCE-C-COMPRESSION-001",
        "status": "SIGNAL_LEVEL_RESEARCH_OBSERVATION_ONLY",
        "strategy_created": False,
    }
    assert shadow["shadow_mode_started"] is False
    assert broker["broker_connected"] is False
    assert broker["broker_calls"] == 0
    assert broker["orders_placed"] == 0
    assert broker["implementation_started"] is False


def test_no_strategy_family_or_execution_path_was_created() -> None:
    tree = ast.parse(inspect.getsource(charter))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not called & {
        "execute_one_shot_validation",
        "execute_post_outcome_remediated_validation",
        "simulate_validation_executable",
        "calculate_validation_metrics",
        "place_order",
        "submit_order",
        "connect_broker",
    }
    assert MANIFEST["implementation_started"] is False
    assert MANIFEST["new_strategy_created"] is False
    assert MANIFEST["strategy_run_performed"] is False
    assert MANIFEST["validation_run_performed"] is False
    assert MANIFEST["paper_trading_started"] is False
    assert MANIFEST["live_trading_started"] is False
    assert MANIFEST["strategy_v2_created"] is False
    assert MANIFEST["family_h_created"] is False
    assert MANIFEST["month_2_started"] is False


def test_governance_ui_audit_alerts_and_boundaries_are_planned() -> None:
    governance = _json("governance/platform_governance_audit_v1.json")
    alerts = _json("governance/alert_monitoring_scope_v1.json")
    boundaries = _json("modules/module_boundaries_v1.json")
    ui = _json("ui/ui_information_architecture_v1.json")
    assert len(governance["append_only_audit_events"]) == 8
    assert governance["audit_log_append_only"] is True
    assert set(alerts["planned_alerts"]) == {
        "DATA_FEED_OUTAGE",
        "STALE_DATA",
        "JOB_FAILURE",
        "BROKER_DISCONNECT",
        "RISK_BREACH",
        "STRATEGY_ERROR_CONDITION",
        "MISSING_SOURCE",
        "VALIDATION_INTEGRITY_ISSUE",
    }
    assert boundaries["cycles_allowed"] is False
    assert len(boundaries["boundaries"]) == 9
    assert set(ui["pages"]) == {
        "Home / Command Center",
        "Research",
        "Strategies",
        "Evidence",
        "Portfolio",
        "Market",
        "Data",
        "Governance",
        "Alerts",
        "Settings",
    }
    assert ui["current_validated_strategy_count"] == 0


def test_product_owner_decisions_and_month_2_backlog_require_approval() -> None:
    decisions = _json("governance/product_owner_decisions_v1.json")
    backlog = _json("backlog/month_2_backlog_categories_v1.json")
    assert len(decisions["decisions"]) == 7
    assert all(row["approval_required"] is True for row in decisions["decisions"])
    assert decisions["default_without_approval"] == "DO_NOT_START"
    assert backlog["implementation_commands_generated"] == 0
    assert backlog["month_2_started"] is False
    assert all(
        row["status"] == "REQUIRES_PRODUCT_OWNER_APPROVAL"
        and row["implementation_command_generated"] is False
        for row in backlog["categories"]
    )


def test_protected_research_artifacts_are_byte_identical() -> None:
    proof = MANIFEST["proof_protected_artifacts_unchanged"]
    assert proof["unchanged"] is True
    assert proof["file_hashes_before"] == proof["file_hashes_after"]
    assert {
        relative: file_sha256(ROOT / relative)
        for relative in proof["file_hashes_after"]
    } == proof["file_hashes_after"]


def test_storage_reports_documentation_roadmap_and_security_are_complete() -> None:
    assert all(
        (ARTIFACT_ROOT / name).is_dir()
        for name in (
            "architecture",
            "modules",
            "domain_model",
            "lineage",
            "governance",
            "shadow",
            "broker",
            "ui",
            "backlog",
            "manifests",
        )
    )
    assert all((ROOT / "data/reports" / name).is_file() for name in charter.REPORT_NAMES)
    assert all((ROOT / name).is_file() for name in charter.DOCUMENTATION_PATHS)
    roadmap = (ROOT / "docs/post-validation-governance-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    assert "ACTIVE_PLATFORM_CHARTER" in roadmap
    assert MANIFEST["security"] == {
        "network_required": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "credentials_written": 0,
        "migrations": 0,
        "supabase_writes": 0,
    }
    assert SUMMARY["manifest_path"].endswith(
        "intersignal_product_platform_charter_manifest_v1.json"
    )
