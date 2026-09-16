from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.13 / Command 01"
COMMAND_VERSION = "INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_V1"
COMMAND_PROFILE = "MONTH_1_PLATFORM_SCOPE_FREEZE_V1"
MANIFEST_VERSION = "INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_MANIFEST_V1"

PROGRAM_REVIEW_HASH = "a152b0e489005ecb506887082c99bee35a8e3c77e199f4c0ada2d7e0089a18cc"
FAMILY_A_CLOSURE_HASH = "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"

LINEAGE_STAGES = (
    "SOURCE",
    "RAW",
    "NORMALIZED",
    "DERIVED",
    "FEATURE",
    "CANDIDATE",
    "SIGNAL",
    "POSITION",
    "TRADE",
    "OUTCOME",
    "EVIDENCE",
)

STRATEGY_LIFECYCLE = (
    "IDEA",
    "PREREGISTERED",
    "DEVELOPMENT_EVALUATED",
    "VALIDATION_CANDIDATE",
    "VALIDATION_EVALUATED",
    "PAUSED",
    "REJECTED",
    "DATA_BLOCKED",
    "SOURCE_BLOCKED",
    "PRODUCTION_CANDIDATE",
)

EVIDENCE_CLASSIFICATIONS = (
    "POSITIVE_EVIDENCE",
    "NEGATIVE_EVIDENCE",
    "BLOCKED_RESEARCH",
    "VALIDATION_EVIDENCE",
    "POST_OUTCOME_EVIDENCE",
    "DATA_INFRASTRUCTURE_EVIDENCE",
)

DEFERRED_MODULES = (
    "LIVE_AUTOMATED_EXECUTION",
    "PAPER_TRADING_DEPLOYMENT_REHEARSAL",
    "FAMILY_H",
    "STRATEGY_V2",
    "NEW_STRATEGY_RESEARCH",
    "FAMILY_D_FULL_INTRADAY_ACQUISITION",
    "FAMILY_F_CATALYST_ACQUISITION",
    "BROKER_ORDER_PLACEMENT_AUTOMATION",
    "AI_AUTONOMOUS_STRATEGY_SELECTION",
)

REPORT_NAMES = (
    "platform_charter_v1_summary.json",
    "platform_charter_v1_priorities.csv",
    "platform_charter_v1_modules.csv",
    "platform_charter_v1_boundaries.csv",
    "platform_charter_v1_deliverables.csv",
    "platform_charter_v1_decisions.csv",
    "platform_charter_v1_risks.csv",
)

DOCUMENTATION_PATHS = (
    "docs/intersignal-product-platform-charter-v1.md",
    "docs/intersignal-platform-architecture-v1.md",
    "docs/intersignal-month-1-scope-v1.md",
    "docs/intersignal-ui-information-architecture-v1.md",
)


class ProductPlatformCharterInputMismatch(RuntimeError):
    pass


class ProductPlatformCharterImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/product/platform_charter/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _verified_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _read_json(path)
    if document.get(field) != expected or _document_hash(document, field) != expected:
        raise ProductPlatformCharterInputMismatch(f"Immutable charter input mismatch: {path}")
    return document


def _with_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def verify_charter_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    program_review = _verified_document(
        root
        / "data/research/program_review/v1/manifests/"
        "post_research_strategy_program_review_manifest_v1.json",
        "post_research_program_review_hash",
        PROGRAM_REVIEW_HASH,
    )
    closure = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_validation_closure/manifests/"
        "family_a_post_validation_closure_manifest_v1.json",
        "family_a_post_validation_closure_hash",
        FAMILY_A_CLOSURE_HASH,
    )
    checks = {
        "program_review_hash_exact": True,
        "family_a_closure_hash_exact": True,
        "a_to_g_complete_no_validated_strategy": (
            program_review.get("a_to_g_final_status")
            == "COMPLETE_NO_VALIDATED_STRATEGY"
            and closure.get("a_to_g_final_status")
            == "COMPLETE_NO_VALIDATED_STRATEGY"
        ),
        "primary_program_product_platform": (
            program_review.get("NEXT_PROGRAM_PRIMARY_DIRECTION")
            == "PRODUCT_PLATFORM_PROGRAM"
        ),
        "secondary_program_forward_data": (
            program_review.get("NEXT_PROGRAM_SECONDARY_DIRECTION")
            == "FORWARD_DATA_PROGRAM"
        ),
        "strategy_research_paused": (
            program_review.get("STRATEGY_DISCOVERY_MODE") == "PAUSED"
        ),
        "strategy_v2_not_created": (
            program_review.get("STRATEGY_V2_STATUS") == "NOT_CREATED"
            and closure.get("strategy_v2_status") == "NOT_CREATED"
        ),
        "family_h_not_planned": (
            program_review.get("FAMILY_H_STATUS") == "NOT_PLANNED"
            and closure.get("family_h_status") == "NOT_PLANNED"
        ),
        "family_a_closed_not_advanced": (
            closure.get("candidate_final_status") == "CLOSED_NOT_ADVANCED"
        ),
    }
    if not all(checks.values()):
        raise ProductPlatformCharterInputMismatch(
            f"PRODUCT_PLATFORM_CHARTER_INPUT_MISMATCH: {checks}"
        )
    return {"checks": checks, "program_review": program_review, "closure": closure}


def _protected_artifact_hashes(root: Path) -> dict[str, str]:
    roots = (
        root / "data/research/cross_family_synthesis/v1",
        root / "data/research/validation/family_a/v1/evaluation",
        root / "data/research/validation/family_a/v1/post_validation_ca_audit",
        root / "data/research/validation/family_a/v1/ca_remediation",
        root / "data/research/validation/family_a/v1/post_outcome_remediated",
        root / "data/research/validation/family_a/v1/post_validation_closure",
        root / "data/research/program_review/v1",
    )
    paths = [path for base in roots for path in base.rglob("*") if path.is_file()]
    family_root = root / "data/research/strategy_families"
    paths.extend(
        path
        for path in family_root.rglob("*")
        if path.is_file() and "manifests" in path.parts
    )
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }


def module_rows() -> list[dict[str, Any]]:
    return [
        {
            "module_id": "A",
            "module": "RESEARCH_WORKBENCH",
            "priority": "P0",
            "month_1_scope": "Governed navigation, comparison, planning, and report/export specification.",
            "rationale": "Makes the completed research corpus usable without changing its evidence.",
            "implementation_started": False,
        },
        {
            "module_id": "B",
            "module": "PORTFOLIO_OS_FOUNDATION",
            "priority": "P0",
            "month_1_scope": "Canonical portfolio, account, holding, cash, transaction, attribution, and risk-state model.",
            "rationale": "Provides the shared state foundation for Trade, Invest, and portfolio intelligence.",
            "implementation_started": False,
        },
        {
            "module_id": "C",
            "module": "DATA_LINEAGE_PROVENANCE",
            "priority": "P0",
            "month_1_scope": "End-to-end lineage stages, identifiers, hashes, quality state, and upstream provenance contract.",
            "rationale": "Auditability and causal integrity are prerequisites for every product domain.",
            "implementation_started": False,
        },
        {
            "module_id": "D",
            "module": "STRATEGY_EVIDENCE_REGISTRY",
            "priority": "P0",
            "month_1_scope": "Lifecycle and evidence schemas that preserve A-G identifiers and current states.",
            "rationale": "Prevents ambiguous promotion and creates a common research/governance vocabulary.",
            "implementation_started": False,
        },
        {
            "module_id": "E",
            "module": "PORTFOLIO_RISK_ANALYTICS",
            "priority": "P1",
            "month_1_scope": "Metric definitions and data contracts for portfolio performance and risk.",
            "rationale": "High product value, sequenced after portfolio and lineage foundations.",
            "implementation_started": False,
        },
        {
            "module_id": "F",
            "module": "SHADOW_OBSERVATION_FRAMEWORK_DESIGN",
            "priority": "P1",
            "month_1_scope": "Research-only observation governance for future unseen data; no activation.",
            "rationale": "Preserves future evidence collection while keeping deployment semantics separate.",
            "implementation_started": False,
        },
        {
            "module_id": "G",
            "module": "BROKER_ABSTRACTION_DESIGN",
            "priority": "P2",
            "month_1_scope": "Broker-neutral capability and adapter contracts only.",
            "rationale": "Portability matters, but no validated strategy or order path justifies earlier work.",
            "implementation_started": False,
        },
        {
            "module_id": "H",
            "module": "DATA_INGESTION_OBSERVABILITY",
            "priority": "P1",
            "month_1_scope": "Freshness, quality, coverage, licensing, run, and failure-state specifications.",
            "rationale": "Operational confidence in data is needed before downstream analytics.",
            "implementation_started": False,
        },
        {
            "module_id": "I",
            "module": "GOVERNANCE_AUDIT_UI",
            "priority": "P1",
            "month_1_scope": "Information architecture for statuses, hashes, authorization, evidence, and audit events.",
            "rationale": "Makes governance visible and reviewable across all modules.",
            "implementation_started": False,
        },
        {
            "module_id": "J",
            "module": "ALERT_MONITORING_FOUNDATION",
            "priority": "P2",
            "month_1_scope": "Alert taxonomy, severity, ownership, acknowledgement, and escalation design.",
            "rationale": "Depends on the data, risk, governance, and broker boundaries being stable.",
            "implementation_started": False,
        },
    ]


def priorities_document() -> dict[str, Any]:
    rows = module_rows()
    body = {
        "priority_version": "MONTH_1_MODULE_PRIORITY_FREEZE_V1",
        "priority_order": ["P0", "P1", "P2", "DEFERRED"],
        "modules": rows,
        "deferred": [
            {
                "scope_id": item,
                "priority": "DEFERRED",
                "implementation_started": False,
                "requires_separate_product_owner_approval": True,
            }
            for item in DEFERRED_MODULES
        ],
        "all_planned_modules_assigned": len(rows) == 10,
    }
    return _with_hash(body, "month_1_module_priority_hash")


def vision_document() -> dict[str, Any]:
    body = {
        "vision_version": "INTERSIGNAL_PRODUCT_VISION_V1",
        "product_framing": "InterSignal = Investment Intelligence Platform",
        "core_domains": ["TRADE", "INVEST", "RESEARCH"],
        "shared_platform": [
            "PORTFOLIO OS",
            "BROKER CONNECTION",
            "DATA LAYER",
            "RISK / GOVERNANCE",
            "AUDITABILITY",
        ],
        "architecture_principle": "LOOSELY_COUPLED_ADAPTER_DRIVEN",
        "core_logic_must_not_depend_directly_on": [
            "GROWW",
            "ZERODHA",
            "SINGLE_DATA_VENDOR",
            "SINGLE_COUNTRY",
        ],
        "geographic_sequence": ["INDIA_FIRST", "UK_FUTURE", "US_FUTURE"],
        "configuration_dimensions": [
            "MARKET",
            "EXCHANGE",
            "CALENDAR",
            "CURRENCY",
            "INSTRUMENT_UNIVERSE",
            "DATA_SOURCE",
            "BROKER",
        ],
    }
    return _with_hash(body, "product_vision_hash")


def architecture_document() -> dict[str, Any]:
    body = {
        "architecture_version": "INTERSIGNAL_PLATFORM_ARCHITECTURE_V1",
        "style": "LOOSELY_COUPLED_MODULAR_PLATFORM",
        "adapter_interfaces_required": True,
        "domains": {
            "TRADE": "Future decision and execution domain; inactive in Month 1.",
            "INVEST": "Long-horizon portfolio, goal, allocation, and intelligence domain.",
            "RESEARCH": "Governed hypothesis, experiment, validation, and evidence domain.",
        },
        "shared_services": [
            "PORTFOLIO_OS",
            "DATA_LAYER",
            "RISK",
            "GOVERNANCE",
            "AUDITABILITY",
            "ALERTS",
            "BROKER_ABSTRACTION",
        ],
        "dependency_rules": [
            "DOMAIN_LOGIC_DEPENDS_ON_CONTRACTS_NOT_PROVIDER_ADAPTERS",
            "DATA_PROVENANCE_CROSSES_ALL_DERIVED_OBJECTS",
            "GOVERNANCE_IS_A_POLICY_AND_AUDIT_BOUNDARY_NOT_ALPHA_LOGIC",
            "RISK_GATES_FUTURE_DECISIONS_BUT_DOES_NOT_CREATE_STRATEGIES",
            "ALERTS_REPORT_STATE_BUT_DO_NOT_OWN_SOURCE_STATE",
            "NO_CIRCULAR_DEPENDENCIES",
        ],
        "implementation_started": False,
    }
    return _with_hash(body, "platform_architecture_hash")


def boundary_rows() -> list[dict[str, Any]]:
    return [
        {"module": "Research", "owns": "hypotheses; experiments; candidates; evidence; validation plans", "allowed_dependencies": "Data; Governance; Strategy/Evidence Registry", "forbidden_dependencies": "Broker adapters; Trade execution; Alerts as authority"},
        {"module": "Trade", "owns": "future signal evaluation; execution decisions; order intents", "allowed_dependencies": "Portfolio OS; Data; Risk; Broker contracts; Governance", "forbidden_dependencies": "Provider-specific broker code; research mutation"},
        {"module": "Invest", "owns": "goals; long-horizon allocation; portfolio intelligence", "allowed_dependencies": "Portfolio OS; Data; Risk; Alerts", "forbidden_dependencies": "Research internals; provider-specific code"},
        {"module": "Portfolio OS", "owns": "accounts; holdings; cash; transactions; attribution; portfolio state", "allowed_dependencies": "Data contracts; Broker read contracts; Risk contracts", "forbidden_dependencies": "Strategy selection; broker implementation"},
        {"module": "Broker", "owns": "provider adapters; account mappings; future order transport", "allowed_dependencies": "External provider APIs behind adapters", "forbidden_dependencies": "Research logic; portfolio analytics; policy authority"},
        {"module": "Data", "owns": "sources; ingestion; normalization; quality; lineage; market reference data", "allowed_dependencies": "Provider adapters; configuration", "forbidden_dependencies": "Strategy decisions; order decisions"},
        {"module": "Risk", "owns": "limits; exposure calculations; risk states; future risk gates", "allowed_dependencies": "Portfolio OS; Data; Governance policy", "forbidden_dependencies": "Alpha generation; broker transport"},
        {"module": "Governance", "owns": "authorization; lifecycle policy; evidence state; audit policy", "allowed_dependencies": "Registry; append-only audit events", "forbidden_dependencies": "Market prediction; broker transport"},
        {"module": "Alerts", "owns": "alert rules; severity; routing; acknowledgement", "allowed_dependencies": "Read-only telemetry from Data; Broker; Risk; Governance; jobs", "forbidden_dependencies": "Authoritative state mutation; order placement"},
    ]


def boundaries_document() -> dict[str, Any]:
    body = {
        "boundaries_version": "INTERSIGNAL_PRODUCT_MODULE_BOUNDARIES_V1",
        "boundaries": boundary_rows(),
        "cycles_allowed": False,
        "provider_dependencies_isolated_behind_adapters": True,
        "month_1_implementation_started": False,
    }
    return _with_hash(body, "product_module_boundaries_hash")


def domain_model_document() -> dict[str, Any]:
    body = {
        "domain_model_version": "INTERSIGNAL_CANONICAL_DOMAIN_MODEL_V1",
        "entities": {
            "Research": ["StrategyFamily", "Strategy", "Experiment", "Candidate", "Evidence", "Authorization", "ValidationRun", "ArtifactHash"],
            "Portfolio": ["Portfolio", "Account", "Holding", "CashBalance", "Transaction", "Exposure", "PnL", "Benchmark", "Allocation", "Attribution", "RiskState", "Goal"],
            "Data": ["DataSource", "Dataset", "DataPartition", "LineageNode", "QualityCheck", "CorporateAction", "Instrument", "MarketCalendar"],
            "Broker": ["BrokerAccountMapping", "BrokerAdapter", "OrderIntent", "OrderRecord"],
            "Operations": ["Alert", "JobRun", "AuditEvent", "ManualOverride"],
        },
        "identity_rules": [
            "EVERY_ENTITY_HAS_A_STABLE_ID_AND_VERSION",
            "EVERY_DERIVED_ENTITY_RETAINS_UPSTREAM_LINEAGE_IDS",
            "CONFIGURATION_AND_EVIDENCE_OBJECTS_RETAIN_CONTENT_HASHES",
            "LIFECYCLE_CHANGES_REQUIRE_APPEND_ONLY_AUDIT_EVENTS",
        ],
        "order_entities_are_future_contractS_only": True,
        "implementation_started": False,
    }
    return _with_hash(body, "canonical_domain_model_hash")


def portfolio_os_document() -> dict[str, Any]:
    body = {
        "portfolio_os_version": "INTERSIGNAL_PORTFOLIO_OS_DOMAIN_MODEL_V1",
        "scope": [
            "PORTFOLIO_ENTITIES",
            "HOLDINGS",
            "CASH",
            "TRANSACTIONS",
            "EXPOSURES",
            "REALIZED_PNL",
            "UNREALIZED_PNL",
            "BENCHMARK_COMPARISON",
            "ALLOCATION",
            "STRATEGY_SOURCE_ATTRIBUTION",
            "RISK_STATE",
            "BROKER_ACCOUNT_MAPPING",
        ],
        "authoritative_state_principle": "PORTFOLIO_STATE_IS_RECONCILED_FROM_AUDITABLE_TRANSACTIONS_AND_SNAPSHOTS",
        "broker_neutral": True,
        "architecture_only": True,
    }
    return _with_hash(body, "portfolio_os_domain_model_hash")


def lineage_document() -> dict[str, Any]:
    body = {
        "lineage_version": "INTERSIGNAL_DATA_LINEAGE_SPEC_V1",
        "stages": list(LINEAGE_STAGES),
        "canonical_path": "SOURCE->RAW->NORMALIZED->DERIVED->FEATURE->CANDIDATE->SIGNAL->POSITION->TRADE->OUTCOME->EVIDENCE",
        "required_provenance": [
            "OBJECT_ID",
            "OBJECT_VERSION",
            "CREATED_AT",
            "UPSTREAM_IDS",
            "UPSTREAM_HASHES",
            "TRANSFORMATION_ID",
            "CONFIGURATION_HASH",
            "CODE_VERSION",
            "DATASET_PARTITION",
            "QUALITY_STATE",
            "AUTHORIZATION_ID_WHERE_APPLICABLE",
        ],
        "rule": "EVERY_DERIVED_OBJECT_MUST_RETAIN_UPSTREAM_PROVENANCE",
        "lineage_break_policy": "BLOCK_DOWNSTREAM_GOVERNED_USE_AND_EMIT_AUDIT_EVENT",
        "implementation_started": False,
    }
    return _with_hash(body, "data_lineage_spec_hash")


def market_data_document() -> dict[str, Any]:
    body = {
        "market_data_architecture_version": "INTERSIGNAL_MARKET_DATA_ARCHITECTURE_V1",
        "categories": [
            "DAILY_DATA",
            "INTRADAY_DATA",
            "REAL_TIME_DATA",
            "CORPORATE_ACTIONS",
            "FUNDAMENTALS",
            "CATALYSTS",
            "BENCHMARKS",
            "BROKER_ACCOUNT_DATA",
        ],
        "separation_dimensions": ["SOURCE", "LICENSE", "FREQUENCY", "MARKET", "QUALITY_STATE", "RETENTION", "LINEAGE"],
        "provider_selected": False,
        "data_acquisition_started": False,
        "implementation_started": False,
    }
    return _with_hash(body, "market_data_architecture_hash")


def realtime_design_document() -> dict[str, Any]:
    body = {
        "design_version": "INTERSIGNAL_REALTIME_INDICATOR_PATTERN_DESIGN_V1",
        "future_live_data_path": [
            "BROKER_OR_FEED",
            "REAL_TIME_NORMALIZATION",
            "BAR_AGGREGATION",
            "INDICATOR_CALCULATION",
            "PATTERN_STATE",
            "STRATEGY_EVALUATION",
            "RISK_GATE",
            "EXECUTION_DECISION",
        ],
        "indicators": ["VWAP", "ATR", "MOVING_AVERAGES", "RELATIVE_VOLUME", "RELATIVE_STRENGTH", "MOMENTUM", "OPENING_RANGE", "BREADTH", "VOLATILITY", "SUPPORT_RESISTANCE", "PRICE_STRUCTURE"],
        "indicator_consumers": ["STRATEGY_LOGIC", "EXECUTION", "RISK", "MONITORING", "ANALYTICS"],
        "indicators_automatically_imply_alpha": False,
        "patterns": ["BREAKOUT", "RECLAIM", "PULLBACK", "COMPRESSION", "OPENING_RANGE_BEHAVIOR", "TREND", "MOMENTUM_CONTINUATION", "SUPPORT_RESISTANCE_INTERACTION"],
        "strategy_activation": False,
        "implementation_started": False,
    }
    return _with_hash(body, "realtime_indicator_pattern_design_hash")


def research_workbench_document() -> dict[str, Any]:
    body = {
        "workbench_version": "INTERSIGNAL_RESEARCH_WORKBENCH_SCOPE_V1",
        "responsibilities": [
            "BROWSE_STRATEGY_FAMILIES",
            "VIEW_EXPERIMENT_LINEAGE",
            "VIEW_FROZEN_HASHES",
            "COMPARE_DEVELOPMENT_VALIDATION_EVIDENCE",
            "INSPECT_POSITIVE_NEGATIVE_EVIDENCE",
            "VIEW_BLOCKED_DATA_LIMITED_STUDIES",
            "CREATE_GOVERNED_FUTURE_EXPERIMENT_PLANS",
            "EXPORT_RESEARCH_REPORTS",
        ],
        "can_execute_research": False,
        "can_mutate_frozen_evidence": False,
        "implementation_started": False,
    }
    return _with_hash(body, "research_workbench_scope_hash")


def evidence_registry_document(root: Path) -> dict[str, Any]:
    source_path = (
        root
        / "data/research/validation/family_a/v1/post_validation_closure/evidence/"
        "final_evidence_registry_v1.json"
    )
    source = _read_json(source_path)
    preserved_ids = [row["evidence_id"] for row in source["rows"]]
    body = {
        "registry_spec_version": "INTERSIGNAL_EVIDENCE_REGISTRY_SPEC_V1",
        "classifications": list(EVIDENCE_CLASSIFICATIONS),
        "required_fields": ["EVIDENCE_ID", "FAMILY_ID", "CLASSIFICATION", "STATUS", "FINDING", "SOURCE_HASH", "CREATED_AT", "LINEAGE_IDS"],
        "preserved_a_to_g_evidence_ids": preserved_ids,
        "family_c_canonical_observation_id": "EDGE-EVIDENCE-C-COMPRESSION-001",
        "family_c_source_registry_id": "EVIDENCE-C-COMPRESSION-001",
        "family_c_id_relationship": "CANONICAL_OBSERVATION_ALIAS_PRESERVES_EXISTING_SOURCE_ID",
        "source_registry_hash": source["a_to_g_final_governance_evidence_registry_hash"],
        "ids_mutated": False,
        "implementation_started": False,
    }
    return _with_hash(body, "evidence_registry_spec_hash")


def strategy_registry_document() -> dict[str, Any]:
    body = {
        "registry_spec_version": "INTERSIGNAL_STRATEGY_REGISTRY_SPEC_V1",
        "lifecycle": list(STRATEGY_LIFECYCLE),
        "required_fields": ["STRATEGY_ID", "FAMILY_ID", "VERSION", "LIFECYCLE_STATE", "CONFIGURATION_HASH", "EVIDENCE_IDS", "AUTHORIZATION_STATE", "VALIDATION_STATE", "PRODUCTION_READINESS"],
        "current_governance_states": {
            "A_TO_G": "COMPLETE_NO_VALIDATED_STRATEGY",
            "FAMILY_A": "CLOSED_NOT_ADVANCED",
            "STRATEGY_RESEARCH": "PAUSED",
            "STRATEGY_V2": "NOT_CREATED",
            "FAMILY_H": "NOT_PLANNED",
            "PAPER": "NOT_READY",
            "LIVE": "NOT_READY",
        },
        "current_families_upgraded": False,
        "production_candidates_created": 0,
        "implementation_started": False,
    }
    return _with_hash(body, "strategy_registry_spec_hash")


def risk_analytics_document() -> dict[str, Any]:
    body = {
        "risk_analytics_version": "INTERSIGNAL_PORTFOLIO_RISK_ANALYTICS_SCOPE_V1",
        "planned_metrics": ["TOTAL_EQUITY", "CASH", "EXPOSURE", "SECTOR_EXPOSURE", "CONCENTRATION", "TURNOVER", "TRANSACTION_COSTS", "DRAWDOWN", "VOLATILITY", "ROLLING_RETURNS", "CONTRIBUTION", "BENCHMARK_RELATIVE_PERFORMANCE", "RISK_LIMITS"],
        "metric_definitions_require_lineage": True,
        "risk_limits_enforced": False,
        "implementation_started": False,
    }
    return _with_hash(body, "portfolio_risk_analytics_scope_hash")


def shadow_document() -> dict[str, Any]:
    body = {
        "shadow_governance_version": "INTERSIGNAL_RESEARCH_SHADOW_GOVERNANCE_V1",
        "mode": "RESEARCH_SHADOW_MODE",
        "purpose": "Track frozen research hypotheses against genuinely new future data.",
        "status": "DESIGN_ONLY_NOT_ACTIVATED",
        "new_data_requirement": "DATA_MUST_NOT_HAVE_BEEN_USED_FOR_MODEL_SELECTION",
        "family_a": {"status": "FROZEN_RESEARCH_BENCHMARK", "production_candidate": False},
        "family_c": {"evidence_id": "EDGE-EVIDENCE-C-COMPRESSION-001", "status": "SIGNAL_LEVEL_RESEARCH_OBSERVATION_ONLY", "strategy_created": False},
        "prohibitions": ["PLACE_ORDERS", "SIMULATE_DEPLOYMENT_READINESS", "MUTATE_STRATEGY", "USE_KNOWN_HOLDOUT_FOR_MODEL_SELECTION"],
        "shadow_mode_started": False,
        "paper_trading_started": False,
        "live_trading_started": False,
    }
    return _with_hash(body, "shadow_mode_governance_hash")


def broker_document() -> dict[str, Any]:
    body = {
        "broker_contract_version": "INTERSIGNAL_BROKER_ABSTRACTION_CONTRACT_V1",
        "potential_adapters": ["GROWW", "ZERODHA", "FUTURE_BROKERS"],
        "conceptual_capabilities": ["MARKET_DATA", "ACCOUNT_INFO", "HOLDINGS", "POSITIONS", "ORDERS", "ORDER_STATUS", "HISTORICAL_DATA"],
        "contract_layers": ["DOMAIN_PORT", "BROKER_NEUTRAL_DTO", "ADAPTER", "PROVIDER_CLIENT"],
        "orders_capability_status": "FUTURE_CONTRACT_ONLY",
        "broker_connected": False,
        "broker_calls": 0,
        "orders_placed": 0,
        "credentials_required": False,
        "implementation_started": False,
    }
    return _with_hash(body, "broker_abstraction_contract_hash")


def governance_document() -> dict[str, Any]:
    body = {
        "governance_version": "INTERSIGNAL_PLATFORM_GOVERNANCE_AUDIT_V1",
        "ui_fields": ["STRATEGY_STATUS", "HASHES", "EXPERIMENT_HISTORY", "VALIDATION_STATE", "EVIDENCE_CLASSIFICATION", "BLOCKED_REASONS", "DATA_QUALITY", "AUTHORIZATION_STATE", "RUN_COUNT", "PRODUCTION_READINESS"],
        "append_only_audit_events": ["DATA_INGEST", "RESEARCH_RUN", "CONFIGURATION_FREEZE", "AUTHORIZATION", "VALIDATION", "STRATEGY_LIFECYCLE_CHANGE", "BROKER_ACTION", "MANUAL_OVERRIDE"],
        "audit_event_required_fields": ["EVENT_ID", "EVENT_TYPE", "TIMESTAMP", "ACTOR", "OBJECT_ID", "OBJECT_VERSION", "BEFORE_HASH", "AFTER_HASH", "AUTHORIZATION_ID", "REASON"],
        "audit_log_append_only": True,
        "current_states": {
            "A_TO_G": "COMPLETE_NO_VALIDATED_STRATEGY",
            "PROGRAM_REVIEW": "COMPLETE",
            "PRIMARY_PROGRAMME": "PRODUCT_PLATFORM_PROGRAM",
            "SECONDARY_PROGRAMME": "FORWARD_DATA_PROGRAM",
            "MONTH_1": "ACTIVE_PLATFORM_CHARTER",
            "STRATEGY_RESEARCH": "PAUSED",
            "STRATEGY_V2": "NOT_CREATED",
            "PAPER": "NOT_READY",
            "LIVE": "NOT_READY",
        },
        "implementation_started": False,
    }
    return _with_hash(body, "platform_governance_audit_hash")


def alerting_document() -> dict[str, Any]:
    body = {
        "alerting_version": "INTERSIGNAL_ALERT_MONITORING_SCOPE_V1",
        "planned_alerts": ["DATA_FEED_OUTAGE", "STALE_DATA", "JOB_FAILURE", "BROKER_DISCONNECT", "RISK_BREACH", "STRATEGY_ERROR_CONDITION", "MISSING_SOURCE", "VALIDATION_INTEGRITY_ISSUE"],
        "lifecycle": ["OPEN", "ACKNOWLEDGED", "RESOLVED", "SUPPRESSED_WITH_REASON"],
        "required_metadata": ["SEVERITY", "SOURCE", "OWNER", "FIRST_SEEN", "LAST_SEEN", "OBJECT_ID", "RUNBOOK", "AUDIT_EVENT_ID"],
        "alerting_active": False,
        "implementation_started": False,
    }
    return _with_hash(body, "alert_monitoring_scope_hash")


def non_goals_document() -> dict[str, Any]:
    body = {
        "non_goals_version": "INTERSIGNAL_MONTH_1_NON_GOALS_V1",
        "non_goals": ["PRODUCTION_TRADING", "AUTONOMOUS_EXECUTION", "NEW_ALPHA_DISCOVERY", "FAMILY_H", "STRATEGY_V2", "AUTO_OPTIMIZING_INDICATORS", "UNRESTRICTED_AI_STRATEGY_GENERATION", "FAMILY_D_OR_F_DATA_ACQUISITION", "LIVE_CAPITAL_DEPLOYMENT"],
        "deferred_modules": list(DEFERRED_MODULES),
        "month_2_started": False,
    }
    return _with_hash(body, "month_1_non_goals_hash")


def decision_rows() -> list[dict[str, Any]]:
    return [
        {"decision_id": "PO-001", "decision": "FIRST_IMPLEMENTATION_MODULE", "current_state": "UNDECIDED", "approval_required": True},
        {"decision_id": "PO-002", "decision": "SHADOW_OBSERVATION_ACTIVATION", "current_state": "NOT_AUTHORIZED", "approval_required": True},
        {"decision_id": "PO-003", "decision": "BROKER_CONNECTION", "current_state": "NOT_AUTHORIZED", "approval_required": True},
        {"decision_id": "PO-004", "decision": "DATA_ACQUISITION", "current_state": "NOT_AUTHORIZED", "approval_required": True},
        {"decision_id": "PO-005", "decision": "FAMILY_D_F_FEASIBILITY_EXECUTION", "current_state": "NOT_AUTHORIZED", "approval_required": True},
        {"decision_id": "PO-006", "decision": "PAPER_TRADING", "current_state": "NOT_READY", "approval_required": True},
        {"decision_id": "PO-007", "decision": "LIVE_TRADING", "current_state": "NOT_READY", "approval_required": True},
    ]


def decisions_document() -> dict[str, Any]:
    body = {
        "decisions_version": "INTERSIGNAL_PRODUCT_OWNER_DECISIONS_V1",
        "decisions": decision_rows(),
        "default_without_approval": "DO_NOT_START",
    }
    return _with_hash(body, "product_owner_decisions_hash")


def ui_document() -> dict[str, Any]:
    body = {
        "ui_ia_version": "INTERSIGNAL_UI_INFORMATION_ARCHITECTURE_V1",
        "pages": {
            "Home / Command Center": ["SYSTEM_STATUS", "MARKET_STATE", "PORTFOLIO_STATE", "RESEARCH_STATUS", "DATA_FRESHNESS", "STRATEGY_STATUS", "ALERTS", "BROKER_CONNECTIVITY"],
            "Research": ["FAMILY_MATRIX", "EXPERIMENT_TIMELINE", "EVIDENCE", "VALIDATION", "BLOCKED_STUDIES", "REPORTS", "ARTIFACTS"],
            "Strategies": ["LIFECYCLE", "CONFIGURATION_HASH", "AUTHORIZATION", "VALIDATION_STATE", "PRODUCTION_READINESS"],
            "Evidence": ["CLASSIFICATION", "SOURCE", "LINEAGE", "HASH", "POSITIVE_NEGATIVE_BLOCKED_VIEWS"],
            "Portfolio": ["HOLDINGS", "ALLOCATION", "PERFORMANCE", "RISK", "CASH", "BENCHMARKS", "BROKER_SYNC", "GOALS"],
            "Market": ["MARKET_STATE", "BENCHMARKS", "BREADTH", "CALENDAR", "INSTRUMENT_UNIVERSE"],
            "Data": ["SOURCES", "COVERAGE", "FRESHNESS", "QUALITY", "LINEAGE", "INGESTION_RUNS", "FAILURES", "LICENSING_STATUS"],
            "Governance": ["AUTHORIZATIONS", "VALIDATION_RUNS", "STRATEGY_LIFECYCLE", "AUDIT_LOG", "POLICY_VIOLATIONS", "MANUAL_OVERRIDES"],
            "Alerts": ["OPEN_ALERTS", "SEVERITY", "OWNERSHIP", "ACKNOWLEDGEMENT", "HISTORY"],
            "Settings": ["MARKET", "EXCHANGE", "CALENDAR", "CURRENCY", "DATA_SOURCE", "BROKER_ADAPTER", "POLICY_CONFIGURATION"],
        },
        "command_center_no_signal_rule": "NO_SIGNAL_RECOMMENDATION_WHEN_NO_VALIDATED_STRATEGY_EXISTS",
        "current_validated_strategy_count": 0,
        "ui_coding_started": False,
    }
    return _with_hash(body, "ui_information_architecture_hash")


def deliverable_rows() -> list[dict[str, Any]]:
    names = [
        "PLATFORM_ARCHITECTURE_DOCUMENT",
        "MODULE_DEPENDENCY_MAP",
        "CANONICAL_DOMAIN_MODEL",
        "DATA_LINEAGE_SPEC",
        "STRATEGY_EVIDENCE_REGISTRY_SPEC",
        "PORTFOLIO_OS_DOMAIN_MODEL",
        "SHADOW_MODE_GOVERNANCE_SPEC",
        "BROKER_ABSTRACTION_CONTRACT",
        "REAL_TIME_ENGINE_DESIGN",
        "UI_INFORMATION_ARCHITECTURE",
        "MONTH_2_BACKLOG_CATEGORIES",
    ]
    return [
        {"deliverable_id": f"M1-{index:02d}", "deliverable": name, "status": "FROZEN_IN_CHARTER", "implementation": False}
        for index, name in enumerate(names, start=1)
    ]


def deliverables_document() -> dict[str, Any]:
    body = {
        "deliverables_version": "INTERSIGNAL_MONTH_1_DELIVERABLES_V1",
        "deliverables": deliverable_rows(),
        "implementation_deliverables": 0,
    }
    return _with_hash(body, "month_1_deliverables_hash")


def month_2_backlog_document() -> dict[str, Any]:
    categories = [
        ("M2-B01", "FOUNDATION_IMPLEMENTATION_CANDIDATE"),
        ("M2-B02", "REGISTRY_AND_LINEAGE"),
        ("M2-B03", "PORTFOLIO_OS"),
        ("M2-B04", "UI_SHELL_AND_READ_MODELS"),
        ("M2-B05", "DATA_OBSERVABILITY"),
        ("M2-B06", "SHADOW_DESIGN_READINESS"),
        ("M2-B07", "BROKER_CONTRACTS"),
        ("M2-B08", "PORTFOLIO_AND_RISK_ANALYTICS"),
        ("M2-B09", "GOVERNANCE_AUDIT_AND_ALERTING"),
    ]
    body = {
        "backlog_version": "INTERSIGNAL_MONTH_2_BACKLOG_CATEGORIES_V1",
        "categories": [
            {"backlog_id": item_id, "category": name, "status": "REQUIRES_PRODUCT_OWNER_APPROVAL", "implementation_command_generated": False}
            for item_id, name in categories
        ],
        "implementation_commands_generated": 0,
        "month_2_started": False,
    }
    return _with_hash(body, "month_2_backlog_categories_hash")


def success_criteria_document() -> dict[str, Any]:
    criteria = [
        "ARCHITECTURE_FROZEN",
        "MODULE_BOUNDARIES_CLEAR",
        "LINEAGE_MODEL_COMPLETE",
        "REGISTRY_MODELS_COMPLETE",
        "PORTFOLIO_OS_SCOPE_COMPLETE",
        "SHADOW_GOVERNANCE_COMPLETE",
        "BROKER_ABSTRACTION_DEFINED",
        "REALTIME_INDICATOR_ARCHITECTURE_DOCUMENTED",
        "UI_IA_DOCUMENTED",
        "PRIORITIZED_MONTH_2_BACKLOG_APPROVED",
    ]
    body = {
        "success_criteria_version": "INTERSIGNAL_MONTH_1_SUCCESS_CRITERIA_V1",
        "criteria": [{"criterion": item, "required": True} for item in criteria],
        "charter_definition_complete": True,
        "month_2_backlog_approved": False,
        "month_1_program_complete": False,
    }
    return _with_hash(body, "month_1_success_criteria_hash")


def risk_rows() -> list[dict[str, Any]]:
    return [
        {"risk_id": "R-001", "risk": "SCOPE_CREEP", "impact": "HIGH", "mitigation": "Use the frozen priorities, non-goals, and product-owner gates."},
        {"risk_id": "R-002", "risk": "PREMATURE_EXECUTION_FOCUS", "impact": "HIGH", "mitigation": "Keep Trade and broker order paths inactive until validation and separate approval."},
        {"risk_id": "R-003", "risk": "OVERENGINEERING", "impact": "MEDIUM", "mitigation": "Implement only an approved vertical slice against stable contracts."},
        {"risk_id": "R-004", "risk": "VENDOR_LOCK_IN", "impact": "HIGH", "mitigation": "Require broker and data adapter interfaces with provider-neutral domain logic."},
        {"risk_id": "R-005", "risk": "DATA_LICENSING", "impact": "HIGH", "mitigation": "Track rights and provenance; require approval before D/F acquisition."},
        {"risk_id": "R-006", "risk": "RESEARCH_PRODUCT_COUPLING", "impact": "HIGH", "mitigation": "Separate research, registry, portfolio, data, and execution boundaries."},
        {"risk_id": "R-007", "risk": "AI_OVERREACH", "impact": "HIGH", "mitigation": "Prohibit autonomous strategy selection and unrestricted strategy generation."},
        {"risk_id": "R-008", "risk": "UNCLEAR_PRODUCTION_READINESS_SEMANTICS", "impact": "HIGH", "mitigation": "Expose explicit lifecycle, authorization, validation, and readiness fields."},
    ]


def risks_document() -> dict[str, Any]:
    body = {
        "risks_version": "INTERSIGNAL_PRODUCT_PLATFORM_PROGRAM_RISKS_V1",
        "risks": risk_rows(),
    }
    return _with_hash(body, "product_platform_program_risks_hash")


def _ensure_fresh(root: Path) -> None:
    destination = output_root(root)
    staging = destination.parent / ".platform_charter_staging_v1"
    reports = [root / "data/reports" / name for name in REPORT_NAMES]
    existing = [path for path in (destination, staging, *reports) if path.exists()]
    if existing:
        raise ProductPlatformCharterImmutabilityError(
            "INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_ALREADY_EXISTS: "
            + ", ".join(str(path) for path in existing)
        )


def _priority_report_rows(priorities: Mapping[str, Any]) -> list[dict[str, Any]]:
    planned = [
        {"scope_type": "PLANNED_MODULE", "scope_id": row["module_id"], "scope": row["module"], "priority": row["priority"], "implementation_started": row["implementation_started"]}
        for row in priorities["modules"]
    ]
    deferred = [
        {"scope_type": "DEFERRED_CAPABILITY", "scope_id": row["scope_id"], "scope": row["scope_id"], "priority": row["priority"], "implementation_started": row["implementation_started"]}
        for row in priorities["deferred"]
    ]
    return planned + deferred


def _seal_outputs(
    root: Path,
    *,
    components: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    final = output_root(root)
    staging = final.parent / ".platform_charter_staging_v1"
    reports = staging / "_reports"
    paths = {
        "vision": "architecture/product_vision_v1.json",
        "architecture": "architecture/platform_architecture_v1.json",
        "realtime": "architecture/realtime_indicator_pattern_design_v1.json",
        "research_workbench": "modules/research_workbench_scope_v1.json",
        "priorities": "modules/module_priorities_v1.json",
        "boundaries": "modules/module_boundaries_v1.json",
        "domain_model": "domain_model/canonical_domain_model_v1.json",
        "portfolio_os": "domain_model/portfolio_os_domain_model_v1.json",
        "risk_analytics": "domain_model/portfolio_risk_analytics_scope_v1.json",
        "lineage": "lineage/data_lineage_spec_v1.json",
        "market_data": "lineage/market_data_architecture_v1.json",
        "evidence_registry": "governance/evidence_registry_spec_v1.json",
        "strategy_registry": "governance/strategy_registry_spec_v1.json",
        "governance": "governance/platform_governance_audit_v1.json",
        "alerting": "governance/alert_monitoring_scope_v1.json",
        "non_goals": "governance/month_1_non_goals_v1.json",
        "decisions": "governance/product_owner_decisions_v1.json",
        "risks": "governance/program_risks_v1.json",
        "shadow": "shadow/shadow_mode_governance_v1.json",
        "broker": "broker/broker_abstraction_contract_v1.json",
        "ui": "ui/ui_information_architecture_v1.json",
        "deliverables": "backlog/month_1_deliverables_v1.json",
        "month_2_backlog": "backlog/month_2_backlog_categories_v1.json",
        "success_criteria": "backlog/month_1_success_criteria_v1.json",
    }
    for key, relative in paths.items():
        write_json(staging / relative, components[key])
    write_csv(staging / "modules/module_priorities_v1.csv", _priority_report_rows(components["priorities"]))
    write_csv(staging / "modules/module_boundaries_v1.csv", components["boundaries"]["boundaries"])
    write_csv(staging / "governance/product_owner_decisions_v1.csv", components["decisions"]["decisions"])
    write_csv(staging / "governance/program_risks_v1.csv", components["risks"]["risks"])
    write_csv(staging / "backlog/month_1_deliverables_v1.csv", components["deliverables"]["deliverables"])
    write_csv(staging / "backlog/month_2_backlog_categories_v1.csv", components["month_2_backlog"]["categories"])
    write_json(staging / "manifests/intersignal_product_platform_charter_manifest_v1.json", manifest)

    write_json(reports / REPORT_NAMES[0], summary)
    write_csv(reports / REPORT_NAMES[1], _priority_report_rows(components["priorities"]))
    write_csv(reports / REPORT_NAMES[2], components["priorities"]["modules"])
    write_csv(reports / REPORT_NAMES[3], components["boundaries"]["boundaries"])
    write_csv(reports / REPORT_NAMES[4], components["deliverables"]["deliverables"])
    write_csv(reports / REPORT_NAMES[5], components["decisions"]["decisions"])
    write_csv(reports / REPORT_NAMES[6], components["risks"]["risks"])

    staging.replace(final)
    for source in list((final / "_reports").iterdir()):
        source.replace(root / "data/reports" / source.name)
    (final / "_reports").rmdir()


def build_product_platform_charter(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _ensure_fresh(root)
    inputs = verify_charter_inputs(root)
    protected_before = _protected_artifact_hashes(root)
    created_at = utc_now()
    components = {
        "vision": vision_document(),
        "architecture": architecture_document(),
        "realtime": realtime_design_document(),
        "research_workbench": research_workbench_document(),
        "priorities": priorities_document(),
        "boundaries": boundaries_document(),
        "domain_model": domain_model_document(),
        "portfolio_os": portfolio_os_document(),
        "risk_analytics": risk_analytics_document(),
        "lineage": lineage_document(),
        "market_data": market_data_document(),
        "evidence_registry": evidence_registry_document(root),
        "strategy_registry": strategy_registry_document(),
        "governance": governance_document(),
        "alerting": alerting_document(),
        "non_goals": non_goals_document(),
        "decisions": decisions_document(),
        "risks": risks_document(),
        "shadow": shadow_document(),
        "broker": broker_document(),
        "ui": ui_document(),
        "deliverables": deliverables_document(),
        "month_2_backlog": month_2_backlog_document(),
        "success_criteria": success_criteria_document(),
    }
    protected_after = _protected_artifact_hashes(root)
    if protected_before != protected_after:
        raise ProductPlatformCharterInputMismatch(
            "Protected research artifacts changed during charter generation"
        )
    component_hashes = {
        key: [value for name, value in document.items() if name.endswith("_hash")][-1]
        for key, document in components.items()
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": created_at,
        "post_research_program_review_hash": PROGRAM_REVIEW_HASH,
        "family_a_post_validation_closure_hash": FAMILY_A_CLOSURE_HASH,
        "product_vision": "InterSignal = Investment Intelligence Platform",
        "priority_order": ["P0", "P1", "P2", "DEFERRED"],
        "component_hashes": component_hashes,
        "governance_status": components["governance"]["current_states"],
        "proof_protected_artifacts_unchanged": {
            "unchanged": True,
            "file_hashes_before": protected_before,
            "file_hashes_after": protected_after,
        },
        "implementation_started": False,
        "backend_features_implemented": False,
        "frontend_features_implemented": False,
        "broker_connected": False,
        "shadow_mode_started": False,
        "strategy_v2_created": False,
        "family_h_created": False,
        "new_strategy_created": False,
        "strategy_run_performed": False,
        "validation_run_performed": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "data_acquisition_started": False,
        "month_2_started": False,
        "reports": list(REPORT_NAMES),
        "documentation": list(DOCUMENTATION_PATHS),
        "security": {
            "network_required": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "credentials_written": 0,
            "migrations": 0,
            "supabase_writes": 0,
        },
    }
    manifest = _with_hash(manifest_body, "product_platform_charter_hash")
    summary = {
        **manifest,
        "inputs_verified": inputs["checks"],
        "components": components,
        "manifest_path": (
            output_root(root)
            / "manifests/intersignal_product_platform_charter_manifest_v1.json"
        ).relative_to(root).as_posix(),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    _seal_outputs(root, components=components, manifest=manifest, summary=summary)
    return summary


def finalize_product_platform_charter(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    out = output_root(root)
    manifest = _read_json(
        out / "manifests/intersignal_product_platform_charter_manifest_v1.json"
    )
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    if _document_hash(manifest, "product_platform_charter_hash") != manifest.get(
        "product_platform_charter_hash"
    ):
        raise ProductPlatformCharterInputMismatch("Platform charter manifest mismatch")
    if _protected_artifact_hashes(root) != manifest[
        "proof_protected_artifacts_unchanged"
    ]["file_hashes_after"]:
        raise ProductPlatformCharterInputMismatch("Protected research artifacts changed")
    values = (backend_targeted_tests, backend_full_tests, frontend_build, regressions)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
        "ready_for_review": all(value.startswith("PASS") for value in values),
        "finalized_at": utc_now(),
        "manifest_unchanged": True,
        "protected_artifacts_unchanged": True,
    }
    record_body = {
        "verification": verification,
        "product_platform_charter_hash": manifest["product_platform_charter_hash"],
    }
    record = _with_hash(record_body, "product_platform_charter_verification_hash")
    target = out / "governance/verification_record_v1.json"
    if target.exists():
        raise ProductPlatformCharterImmutabilityError(
            "Product platform charter already finalized"
        )
    write_json(target, record)
    summary["verification"] = verification
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "DEFERRED_MODULES",
    "EVIDENCE_CLASSIFICATIONS",
    "FAMILY_A_CLOSURE_HASH",
    "LINEAGE_STAGES",
    "MANIFEST_VERSION",
    "PROGRAM_REVIEW_HASH",
    "REPORT_NAMES",
    "STRATEGY_LIFECYCLE",
    "build_product_platform_charter",
    "finalize_product_platform_charter",
    "module_rows",
    "output_root",
    "verify_charter_inputs",
)
