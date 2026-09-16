from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.12 / Command 01"
COMMAND_VERSION = "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_V1"
COMMAND_PROFILE = "INTERSIGNAL_NEXT_CYCLE_DECISION_V1"
MANIFEST_VERSION = "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_MANIFEST_V1"

FAMILY_A_CLOSURE_HASH = "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"
CROSS_FAMILY_SYNTHESIS_HASH = "d05826bfae334b64a759b81de5864b25cc076da0267ac36d7b926a67f865d64e"
POST_OUTCOME_MANIFEST_HASH = "9323d59c72e1178379664706f5562abc00c1c7ca425ffd06baf431c3a977370b"

OPTION_IDS = (
    "OPTION_A_FORWARD_DATA_PROGRAM",
    "OPTION_B_DATA_INFRASTRUCTURE_PROGRAM",
    "OPTION_C_NEW_HYPOTHESIS_PROGRAM",
    "OPTION_D_PRODUCT_PLATFORM_PROGRAM",
)
NEXT_PROGRAM_PRIMARY_DIRECTION = "PRODUCT_PLATFORM_PROGRAM"
NEXT_PROGRAM_SECONDARY_DIRECTION = "FORWARD_DATA_PROGRAM"
STRATEGY_RESEARCH_PROGRAM_STATUS = "PRODUCT_PLATFORM_FOCUS"
STRATEGY_DISCOVERY_MODE = "PAUSED"
FAMILY_A_FORWARD_USE_STATUS = "FROZEN_RESEARCH_BENCHMARK"
FAMILY_C_FORWARD_USE_STATUS = "SIGNAL_LEVEL_RESEARCH_OBSERVATION_ONLY"
FAMILY_D_INFRASTRUCTURE_PRIORITY = "TARGETED_FEASIBILITY_SECONDARY"
FAMILY_F_INFRASTRUCTURE_PRIORITY = "TARGETED_FEASIBILITY_SECONDARY"
STRATEGY_V2_STATUS = "NOT_CREATED"
FAMILY_H_STATUS = "NOT_PLANNED"

REPORT_NAMES = (
    "program_review_v1_summary.json",
    "program_review_v1_options.csv",
    "program_review_v1_decision.csv",
    "program_review_v1_3_month_plan.csv",
    "program_review_v1_6_month_plan.csv",
    "program_review_v1_resources.csv",
    "program_review_v1_stop_conditions.csv",
)


class ProgramReviewInputMismatch(RuntimeError):
    pass


class ProgramReviewImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/program_review/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _verified_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _read_json(path)
    if document.get(field) != expected or _document_hash(document, field) != expected:
        raise ProgramReviewInputMismatch(f"Immutable review input mismatch: {path}")
    return document


def verify_program_review_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    closure_manifest = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_validation_closure/manifests/"
        "family_a_post_validation_closure_manifest_v1.json",
        "family_a_post_validation_closure_hash",
        FAMILY_A_CLOSURE_HASH,
    )
    closure_summary = _read_json(
        root / "data/reports/family_a_post_validation_closure_v1_summary.json"
    )
    synthesis = _verified_document(
        root
        / "data/research/cross_family_synthesis/v1/manifests/"
        "cross_family_evidence_synthesis_manifest_v1.json",
        "cross_family_synthesis_hash",
        CROSS_FAMILY_SYNTHESIS_HASH,
    )
    post_manifest = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_outcome_remediated/manifests/"
        "family_a_post_outcome_remediated_validation_manifest_v1.json",
        "family_a_post_outcome_remediated_validation_manifest_hash",
        POST_OUTCOME_MANIFEST_HASH,
    )
    checks = {
        "family_a_closure_ready": closure_summary.get("verification", {}).get(
            "ready_for_review"
        )
        is True,
        "family_a_closed_not_advanced": closure_manifest.get(
            "candidate_final_status"
        )
        == "CLOSED_NOT_ADVANCED",
        "formal_validation_inconclusive": closure_manifest.get(
            "formal_validation", {}
        ).get("FAMILY_A_FORMAL_VALIDATION_STATUS")
        == "INCONCLUSIVE",
        "post_outcome_unsupportive": closure_manifest.get(
            "post_outcome_remediated", {}
        ).get("generalization_indication")
        == "UNSUPPORTIVE",
        "holdout_contaminated": closure_manifest.get(
            "holdout_contamination_state"
        )
        == "CONTAMINATED_FOR_FUTURE_MODEL_SELECTION",
        "a_to_g_complete": closure_manifest.get("a_to_g_final_status")
        == "COMPLETE_NO_VALIDATED_STRATEGY",
        "strategy_v2_absent": closure_manifest.get("strategy_v2_status")
        == "NOT_CREATED",
        "family_h_not_planned": closure_manifest.get("family_h_status")
        == "NOT_PLANNED",
        "synthesis_exact": synthesis.get("manifest_version")
        == "CROSS_FAMILY_EVIDENCE_SYNTHESIS_MANIFEST_V1",
        "post_outcome_exact": post_manifest.get("POST_OUTCOME_REMEDIATED_RESULT")
        == "FAIL",
    }
    if not all(checks.values()):
        raise ProgramReviewInputMismatch(
            f"POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_INPUT_MISMATCH: {checks}"
        )
    return {
        "checks": checks,
        "closure_manifest": closure_manifest,
        "closure_summary": closure_summary,
        "synthesis": synthesis,
        "post_manifest": post_manifest,
    }


def _protected_artifact_hashes(root: Path) -> dict[str, str]:
    roots = (
        root / "data/research/cross_family_synthesis/v1",
        root / "data/research/validation/family_a/v1/evaluation",
        root / "data/research/validation/family_a/v1/post_validation_ca_audit",
        root / "data/research/validation/family_a/v1/ca_remediation",
        root / "data/research/validation/family_a/v1/post_outcome_remediated",
        root / "data/research/validation/family_a/v1/post_validation_closure",
    )
    paths = [path for base in roots for path in base.rglob("*") if path.is_file()]
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }


def _with_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def option_rows() -> list[dict[str, Any]]:
    return [
        {
            "option_id": OPTION_IDS[0],
            "direction": "FORWARD_DATA_PROGRAM",
            "definition": "Freeze selected hypotheses and wait for genuinely new unseen future data.",
            "expected_research_value": "HIGH",
            "scientific_cleanliness": "HIGH",
            "time_to_next_decision": "HIGH",
            "engineering_effort": "MEDIUM",
            "data_licensing_dependency": "LOW",
            "cost": "LOW",
            "reuse_across_intersignal": "MEDIUM",
            "risk_of_overfitting": "LOW",
            "strategic_optionality": "HIGH",
            "product_value_without_strategy": "MEDIUM",
            "decision": "SECONDARY",
            "rationale": (
                "Only genuinely new observations can restore unseen evidence, but the "
                "wait is long and no validated candidate currently justifies deployment rehearsal."
            ),
        },
        {
            "option_id": OPTION_IDS[1],
            "direction": "DATA_INFRASTRUCTURE_PROGRAM",
            "definition": "Resolve Family D intraday continuity and Family F authorized catalyst data blockers.",
            "expected_research_value": "MEDIUM",
            "scientific_cleanliness": "HIGH",
            "time_to_next_decision": "HIGH",
            "engineering_effort": "HIGH",
            "data_licensing_dependency": "HIGH",
            "cost": "HIGH",
            "reuse_across_intersignal": "HIGH",
            "risk_of_overfitting": "LOW",
            "strategic_optionality": "HIGH",
            "product_value_without_strategy": "HIGH",
            "decision": "DEFERRED_TARGETED_FEASIBILITY_ONLY",
            "rationale": (
                "Intraday and catalyst data have broad reuse, but continuity, authorization, "
                "licensing, and engineering burdens should be scoped before committing."
            ),
        },
        {
            "option_id": OPTION_IDS[2],
            "direction": "NEW_HYPOTHESIS_PROGRAM",
            "definition": "Develop a distinct economic or behavioral mechanism with independent preregistration.",
            "expected_research_value": "MEDIUM",
            "scientific_cleanliness": "MEDIUM",
            "time_to_next_decision": "HIGH",
            "engineering_effort": "MEDIUM",
            "data_licensing_dependency": "MEDIUM",
            "cost": "MEDIUM",
            "reuse_across_intersignal": "LOW",
            "risk_of_overfitting": "MEDIUM",
            "strategic_optionality": "HIGH",
            "product_value_without_strategy": "LOW",
            "decision": "DEFERRED_NOT_YET_JUSTIFIED",
            "rationale": (
                "No distinct mechanism with verified data readiness currently exists; "
                "continuing to Family H would force strategy production rather than follow evidence."
            ),
        },
        {
            "option_id": OPTION_IDS[3],
            "direction": "PRODUCT_PLATFORM_PROGRAM",
            "definition": "Pause strategy discovery and strengthen InterSignal as a research, portfolio, and governance platform.",
            "expected_research_value": "MEDIUM",
            "scientific_cleanliness": "HIGH",
            "time_to_next_decision": "MEDIUM",
            "engineering_effort": "HIGH",
            "data_licensing_dependency": "LOW",
            "cost": "MEDIUM",
            "reuse_across_intersignal": "HIGH",
            "risk_of_overfitting": "LOW",
            "strategic_optionality": "HIGH",
            "product_value_without_strategy": "HIGH",
            "decision": "PRIMARY",
            "rationale": (
                "It creates durable research, portfolio-intelligence, risk, lineage, and "
                "audit value regardless of alpha success while preserving future options."
            ),
        },
    ]


def options_document() -> dict[str, Any]:
    body = {
        "options_version": "POST_RESEARCH_PROGRAM_OPTIONS_V1",
        "rating_scale": ["HIGH", "MEDIUM", "LOW"],
        "rating_note": (
            "HIGH is favorable for value, cleanliness, reuse, and optionality; HIGH denotes "
            "greater burden for time, effort, dependency, cost, and overfitting risk."
        ),
        "options": option_rows(),
        "arbitrary_weighted_score_used": False,
    }
    return _with_hash(body, "post_research_program_options_hash")


def decision_document() -> dict[str, Any]:
    body = {
        "decision_version": "INTERSIGNAL_NEXT_CYCLE_DECISION_V1",
        "primary_question": (
            "What should InterSignal do next after completing A-G without a validated strategy?"
        ),
        "NEXT_PROGRAM_PRIMARY_DIRECTION": NEXT_PROGRAM_PRIMARY_DIRECTION,
        "NEXT_PROGRAM_SECONDARY_DIRECTION": NEXT_PROGRAM_SECONDARY_DIRECTION,
        "STRATEGY_RESEARCH_PROGRAM_STATUS": STRATEGY_RESEARCH_PROGRAM_STATUS,
        "STRATEGY_DISCOVERY_MODE": STRATEGY_DISCOVERY_MODE,
        "another_strategy_family_currently_justified": "NO",
        "primary_rationale": (
            "Product/platform work offers the highest durable value across Research, Portfolio OS, "
            "risk, lineage, auditability, and decision support even if no alpha strategy succeeds. "
            "It also prepares clean infrastructure for later forward observation without treating "
            "shadow data as deployment rehearsal."
        ),
        "option_rationales": {
            "OPTION_A_FORWARD_DATA_PROGRAM": (
                "Selected as secondary because new unseen data is scientifically necessary, but "
                "the time-to-decision is long and Family A is only a frozen benchmark."
            ),
            "OPTION_B_DATA_INFRASTRUCTURE_PROGRAM": (
                "Deferred to targeted feasibility because reusable value is high but licensing, "
                "continuity, engineering, and cost dependencies are high."
            ),
            "OPTION_C_NEW_HYPOTHESIS_PROGRAM": (
                "Deferred because no genuinely distinct, data-ready economic mechanism currently "
                "justifies another family."
            ),
            "OPTION_D_PRODUCT_PLATFORM_PROGRAM": (
                "Selected because it produces immediate program value independent of strategy-alpha "
                "success and retains the most future optionality."
            ),
        },
        "evidence_that_would_change_decision": [
            "A materially accumulated genuinely unseen forward dataset with a preregistered frozen benchmark.",
            "Acceptable licensed-data feasibility for reusable intraday or catalyst infrastructure.",
            "A distinct economic hypothesis with independent preregistration and verified data readiness.",
            "Evidence that platform engineering opportunity cost exceeds its cross-module value.",
        ],
        "selected_program_started": False,
    }
    return _with_hash(body, "post_research_program_decision_hash")


def forward_observation_document() -> dict[str, Any]:
    body = {
        "policy_version": "INTERSIGNAL_FORWARD_OBSERVATION_POLICY_V1",
        "paper_observation_mode": "RESEARCH_SHADOW_MODE",
        "paper_trading_readiness": "NO_VALIDATED_CANDIDATE",
        "deployment_rehearsal": False,
        "new_unseen_evidence_requirement": (
            "DATA_MUST_NOT_HAVE_BEEN_USED_FOR_MODEL_SELECTION"
        ),
        "performance_thresholds_defined": False,
        "FAMILY_A_FORWARD_USE_STATUS": FAMILY_A_FORWARD_USE_STATUS,
        "family_a_live_candidate": False,
        "FAMILY_C_FORWARD_USE_STATUS": FAMILY_C_FORWARD_USE_STATUS,
        "family_c_strategy_created": False,
        "forward_observation_started": False,
    }
    return _with_hash(body, "forward_observation_policy_hash")


def infrastructure_assessment_document() -> dict[str, Any]:
    body = {
        "assessment_version": "BLOCKED_DATA_INFRASTRUCTURE_ASSESSMENT_V1",
        "FAMILY_D_INFRASTRUCTURE_PRIORITY": FAMILY_D_INFRASTRUCTURE_PRIORITY,
        "family_d_reuse": [
            "INTRADAY_EXECUTION_RESEARCH",
            "MARKET_MICROSTRUCTURE",
            "ENTRY_TIMING",
            "FUTURE_STRATEGY_FAMILIES",
            "EXECUTION_QUALITY_ANALYTICS",
        ],
        "FAMILY_F_INFRASTRUCTURE_PRIORITY": FAMILY_F_INFRASTRUCTURE_PRIORITY,
        "family_f_reuse": [
            "RESEARCH_MODULE",
            "FUNDAMENTAL_CATALYST_INTELLIGENCE",
            "PORTFOLIO_ALERTS",
            "EVENT_RISK",
            "FUTURE_INVEST_RESEARCH_MODULES",
        ],
        "data_acquisition_started": False,
        "provider_selected": False,
    }
    return _with_hash(body, "blocked_data_infrastructure_assessment_hash")


def three_month_plan_rows() -> list[dict[str, Any]]:
    return [
        {
            "month": 1,
            "focus": "PROGRAM_CHARTER_AND_PRODUCT_PRIORITIES",
            "decision_milestones": (
                "Confirm product-owner priorities across Research, Portfolio OS, risk, audit, "
                "signal registry, and data lineage; freeze non-goals and governance boundaries."
            ),
            "implementation_started": False,
        },
        {
            "month": 2,
            "focus": "ARCHITECTURE_AND_FEASIBILITY_DECISIONS",
            "decision_milestones": (
                "Review module boundaries and resource tradeoffs; assess shadow-observation "
                "governance and scoped Family D/F data feasibility without acquisition."
            ),
            "implementation_started": False,
        },
        {
            "month": 3,
            "focus": "PROGRAM_GO_NO_GO_AND_SEQUENCE",
            "decision_milestones": (
                "Approve, revise, or stop the platform programme; sequence separately authorized "
                "work and decide whether passive forward observation should be activated."
            ),
            "implementation_started": False,
        },
    ]


def six_month_plan_rows() -> list[dict[str, Any]]:
    return [
        {
            "horizon": "MONTHS_1_TO_3",
            "objective": "Complete product charter, architecture, governance, and resource decisions.",
            "decision_point": "AUTHORIZE_REVISE_OR_STOP_PLATFORM_PROGRAM",
        },
        {
            "horizon": "MONTHS_4_TO_5_IF_SEPARATELY_AUTHORIZED",
            "objective": (
                "Establish reusable research auditability, lineage, portfolio intelligence, and "
                "shadow-observation foundations without live deployment."
            ),
            "decision_point": "VERIFY_PROGRAM_LEVEL_SUCCESS_CRITERIA",
        },
        {
            "horizon": "MONTH_6",
            "objective": "Review product value, forward-data accumulation, data-blocker feasibility, and hypothesis quality.",
            "decision_point": (
                "CHOOSE_CONTINUE_PLATFORM_VALIDATE_FORWARD_EVIDENCE_CHANGE_PROGRAM_OR_PAUSE_ALPHA_RESEARCH"
            ),
        },
    ]


def resource_rows() -> list[dict[str, Any]]:
    return [
        {
            "resource": "ENGINEERING_EFFORT",
            "level": "HIGH",
            "basis": "Cross-module architecture, lineage, registry, risk, audit, and portfolio capabilities.",
        },
        {
            "resource": "DATA_EFFORT",
            "level": "MEDIUM",
            "basis": "Existing-data lineage and readiness design plus D/F feasibility assessment.",
        },
        {
            "resource": "LICENSING_DATA_COST",
            "level": "LOW",
            "basis": "No acquisition in the selected programme; only feasibility review is included.",
        },
        {
            "resource": "COMPUTE_STORAGE_IMPACT",
            "level": "MEDIUM",
            "basis": "Registry, lineage, portfolio analytics, monitoring, and future shadow data retention.",
        },
        {
            "resource": "MANUAL_REVIEW_EFFORT",
            "level": "MEDIUM",
            "basis": "Product decisions, governance review, data-quality review, and audit acceptance.",
        },
    ]


def success_criteria_rows() -> list[dict[str, Any]]:
    return [
        {"criterion": "PRODUCT_PROGRAM_CHARTER", "success": "Owner-approved priorities, boundaries, and module sequence."},
        {"criterion": "RESEARCH_AUDITABILITY", "success": "Complete lineage, evidence, and decision-record requirements."},
        {"criterion": "SHADOW_OBSERVATION_READINESS", "success": "Governed research-shadow design ready for separate authorization."},
        {"criterion": "DATA_BLOCKER_DECISIONS", "success": "Explicit D/F feasibility decisions without unauthorized acquisition."},
        {"criterion": "PLATFORM_VALUE", "success": "Defined utility for research, portfolio intelligence, risk, and audit independent of alpha."},
        {"criterion": "NEXT_CANDIDATE_DECISION", "success": "Clean continue, change, or pause decision based on evidence rather than return targets."},
    ]


def stop_condition_rows() -> list[dict[str, Any]]:
    return [
        {"condition": "PERSISTENT_NON_GENERALIZATION", "action": "PAUSE_ALPHA_RESEARCH"},
        {"condition": "INSUFFICIENT_DATA_QUALITY", "action": "STOP_AFFECTED_RESEARCH_PATH"},
        {"condition": "EXCESSIVE_LICENSING_BURDEN", "action": "DEFER_DATA_DEPENDENT_PROGRAM"},
        {"condition": "NO_DISTINCT_ECONOMIC_HYPOTHESIS", "action": "DO_NOT_START_NEW_RESEARCH_CYCLE"},
        {"condition": "ENGINEERING_OPPORTUNITY_COST_TOO_HIGH", "action": "REDUCE_OR_STOP_PLATFORM_PROGRAM"},
        {"condition": "NO_PRODUCT_OWNER_VALUE_CONFIRMATION", "action": "REASSESS_PROGRAM_DIRECTION"},
    ]


def product_mapping_rows() -> list[dict[str, Any]]:
    return [
        {"module": "Trade", "interaction": "DEFERRED", "value": "No strategy execution or live automation."},
        {"module": "Invest", "interaction": "SECONDARY", "value": "Future catalyst intelligence, alerts, and decision support."},
        {"module": "Research", "interaction": "PRIMARY", "value": "Workbench, signal registry, experiment evidence, and auditability."},
        {"module": "Portfolio OS", "interaction": "PRIMARY", "value": "Portfolio intelligence, analytics, risk, monitoring, and decisions."},
        {"module": "Broker Connection", "interaction": "DESIGN_ONLY", "value": "Abstraction boundaries only; no broker calls or execution."},
        {"module": "Data Layer", "interaction": "PRIMARY", "value": "Lineage, quality, provenance, and future shadow-data governance."},
    ]


def roadmap_document() -> dict[str, Any]:
    body = {
        "roadmap_version": "POST_RESEARCH_STRATEGY_PROGRAM_ROADMAP_V1",
        "three_month_plan": three_month_plan_rows(),
        "six_month_plan": six_month_plan_rows(),
        "product_mapping": product_mapping_rows(),
        "programme_started": False,
    }
    return _with_hash(body, "post_research_program_roadmap_hash")


def resource_plan_document() -> dict[str, Any]:
    body = {
        "resource_plan_version": "POST_RESEARCH_PROGRAM_RESOURCE_PLAN_V1",
        "resources": resource_rows(),
        "success_criteria": success_criteria_rows(),
        "stop_conditions": stop_condition_rows(),
        "financial_return_target_defined": False,
    }
    return _with_hash(body, "post_research_program_resource_plan_hash")


def governance_document() -> dict[str, Any]:
    body = {
        "governance_version": "POST_RESEARCH_PROGRAM_GOVERNANCE_V1",
        "STRATEGY_RESEARCH_PROGRAM_STATUS": STRATEGY_RESEARCH_PROGRAM_STATUS,
        "STRATEGY_DISCOVERY_MODE": STRATEGY_DISCOVERY_MODE,
        "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        "FAMILY_H_STATUS": FAMILY_H_STATUS,
        "new_strategy_created": False,
        "validation_run_performed": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "data_acquisition_started": False,
        "infrastructure_implementation_started": False,
        "selected_program_started": False,
    }
    return _with_hash(body, "post_research_program_governance_hash")


def _ensure_fresh(root: Path) -> None:
    destination = output_root(root)
    staging = destination.parent / ".program_review_staging_v1"
    reports = [root / "data/reports" / name for name in REPORT_NAMES]
    existing = [path for path in (destination, staging, *reports) if path.exists()]
    if existing:
        raise ProgramReviewImmutabilityError(
            "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_ALREADY_EXISTS: "
            + ", ".join(str(path) for path in existing)
        )


def _decision_report_row(
    decision: Mapping[str, Any], governance: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "NEXT_PROGRAM_PRIMARY_DIRECTION": decision["NEXT_PROGRAM_PRIMARY_DIRECTION"],
        "NEXT_PROGRAM_SECONDARY_DIRECTION": decision["NEXT_PROGRAM_SECONDARY_DIRECTION"],
        "STRATEGY_RESEARCH_PROGRAM_STATUS": governance[
            "STRATEGY_RESEARCH_PROGRAM_STATUS"
        ],
        "STRATEGY_DISCOVERY_MODE": governance["STRATEGY_DISCOVERY_MODE"],
        "STRATEGY_V2_STATUS": governance["STRATEGY_V2_STATUS"],
        "FAMILY_H_STATUS": governance["FAMILY_H_STATUS"],
        "selected_program_started": governance["selected_program_started"],
    }


def _seal_outputs(
    root: Path,
    *,
    options: Mapping[str, Any],
    decision: Mapping[str, Any],
    roadmap: Mapping[str, Any],
    resources: Mapping[str, Any],
    governance: Mapping[str, Any],
    forward: Mapping[str, Any],
    infrastructure: Mapping[str, Any],
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    final = output_root(root)
    staging = final.parent / ".program_review_staging_v1"
    reports = staging / "_reports"
    write_json(staging / "options/program_options_v1.json", options)
    write_csv(staging / "options/program_options_v1.csv", options["options"])
    write_json(staging / "decision/program_decision_v1.json", decision)
    write_csv(staging / "decision/program_decision_v1.csv", [_decision_report_row(decision, governance)])
    write_json(staging / "roadmap/program_roadmap_v1.json", roadmap)
    write_csv(staging / "roadmap/three_month_plan_v1.csv", roadmap["three_month_plan"])
    write_csv(staging / "roadmap/six_month_plan_v1.csv", roadmap["six_month_plan"])
    write_csv(staging / "roadmap/product_mapping_v1.csv", roadmap["product_mapping"])
    write_json(staging / "resource_plan/resource_plan_v1.json", resources)
    write_csv(staging / "resource_plan/resources_v1.csv", resources["resources"])
    write_csv(staging / "resource_plan/success_criteria_v1.csv", resources["success_criteria"])
    write_csv(staging / "resource_plan/stop_conditions_v1.csv", resources["stop_conditions"])
    write_json(staging / "governance/program_state_v1.json", governance)
    write_json(staging / "governance/forward_observation_policy_v1.json", forward)
    write_json(staging / "governance/data_infrastructure_assessment_v1.json", infrastructure)
    write_json(
        staging / "manifests/post_research_strategy_program_review_manifest_v1.json",
        manifest,
    )

    write_json(reports / REPORT_NAMES[0], summary)
    write_csv(reports / REPORT_NAMES[1], options["options"])
    write_csv(reports / REPORT_NAMES[2], [_decision_report_row(decision, governance)])
    write_csv(reports / REPORT_NAMES[3], roadmap["three_month_plan"])
    write_csv(reports / REPORT_NAMES[4], roadmap["six_month_plan"])
    write_csv(reports / REPORT_NAMES[5], resources["resources"])
    write_csv(reports / REPORT_NAMES[6], resources["stop_conditions"])

    staging.replace(final)
    for source in list((final / "_reports").iterdir()):
        source.replace(root / "data/reports" / source.name)
    (final / "_reports").rmdir()


def build_post_research_strategy_program_review(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _ensure_fresh(root)
    inputs = verify_program_review_inputs(root)
    protected_before = _protected_artifact_hashes(root)
    created_at = utc_now()
    options = options_document()
    decision = decision_document()
    forward = forward_observation_document()
    infrastructure = infrastructure_assessment_document()
    roadmap = roadmap_document()
    resources = resource_plan_document()
    governance = governance_document()
    protected_after = _protected_artifact_hashes(root)
    if protected_before != protected_after:
        raise ProgramReviewInputMismatch("Protected research artifacts changed during review")

    component_hashes = {
        "post_research_program_options_hash": options["post_research_program_options_hash"],
        "post_research_program_decision_hash": decision[
            "post_research_program_decision_hash"
        ],
        "forward_observation_policy_hash": forward["forward_observation_policy_hash"],
        "blocked_data_infrastructure_assessment_hash": infrastructure[
            "blocked_data_infrastructure_assessment_hash"
        ],
        "post_research_program_roadmap_hash": roadmap[
            "post_research_program_roadmap_hash"
        ],
        "post_research_program_resource_plan_hash": resources[
            "post_research_program_resource_plan_hash"
        ],
        "post_research_program_governance_hash": governance[
            "post_research_program_governance_hash"
        ],
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": created_at,
        "family_a_post_validation_closure_hash": FAMILY_A_CLOSURE_HASH,
        "a_to_g_final_status": "COMPLETE_NO_VALIDATED_STRATEGY",
        "current_evidence_inputs": [
            "FAMILY_A_STRONG_DEVELOPMENT_LATER_UNSUPPORTIVE",
            "FAMILY_C_REUSABLE_COMPRESSION_SIGNAL",
            "FAMILY_D_DATA_BLOCK",
            "FAMILY_F_SOURCE_BLOCK",
            "FAMILY_G_NEGATIVE_REGIME_OVERLAY",
            "CAP4_VALIDATION_FAILURE",
            "CA_VALIDATION_INTEGRITY_LESSONS",
            "KNOWN_HOLDOUT_CONTAMINATION",
        ],
        "evaluated_options": list(OPTION_IDS),
        "NEXT_PROGRAM_PRIMARY_DIRECTION": NEXT_PROGRAM_PRIMARY_DIRECTION,
        "NEXT_PROGRAM_SECONDARY_DIRECTION": NEXT_PROGRAM_SECONDARY_DIRECTION,
        "STRATEGY_RESEARCH_PROGRAM_STATUS": STRATEGY_RESEARCH_PROGRAM_STATUS,
        "STRATEGY_DISCOVERY_MODE": STRATEGY_DISCOVERY_MODE,
        "FAMILY_A_FORWARD_USE_STATUS": FAMILY_A_FORWARD_USE_STATUS,
        "FAMILY_C_FORWARD_USE_STATUS": FAMILY_C_FORWARD_USE_STATUS,
        "FAMILY_D_INFRASTRUCTURE_PRIORITY": FAMILY_D_INFRASTRUCTURE_PRIORITY,
        "FAMILY_F_INFRASTRUCTURE_PRIORITY": FAMILY_F_INFRASTRUCTURE_PRIORITY,
        "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        "FAMILY_H_STATUS": FAMILY_H_STATUS,
        "component_hashes": component_hashes,
        "proof_protected_artifacts_unchanged": {
            "unchanged": True,
            "file_hashes_before": protected_before,
            "file_hashes_after": protected_after,
        },
        "program_started": False,
        "new_strategy_created": False,
        "validation_run_performed": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "data_acquisition_started": False,
        "infrastructure_implementation_started": False,
        "reports": list(REPORT_NAMES),
        "security": {
            "network_required": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "external_writes": 0,
            "credentials_written": 0,
            "migrations": 0,
            "supabase_writes": 0,
        },
    }
    manifest = _with_hash(manifest_body, "post_research_program_review_hash")
    summary = {
        **manifest,
        "inputs_verified": inputs["checks"],
        "options": options,
        "decision": decision,
        "forward_observation": forward,
        "infrastructure_assessment": infrastructure,
        "roadmap": roadmap,
        "resource_plan": resources,
        "governance": governance,
        "manifest_path": (
            output_root(root)
            / "manifests/post_research_strategy_program_review_manifest_v1.json"
        ).relative_to(root).as_posix(),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    _seal_outputs(
        root,
        options=options,
        decision=decision,
        roadmap=roadmap,
        resources=resources,
        governance=governance,
        forward=forward,
        infrastructure=infrastructure,
        manifest=manifest,
        summary=summary,
    )
    return summary


def finalize_post_research_strategy_program_review(
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
        out / "manifests/post_research_strategy_program_review_manifest_v1.json"
    )
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    if _document_hash(manifest, "post_research_program_review_hash") != manifest.get(
        "post_research_program_review_hash"
    ):
        raise ProgramReviewInputMismatch("Program-review manifest mismatch")
    if _protected_artifact_hashes(root) != manifest[
        "proof_protected_artifacts_unchanged"
    ]["file_hashes_after"]:
        raise ProgramReviewInputMismatch("Protected research artifacts changed")
    values = (
        backend_targeted_tests,
        backend_full_tests,
        frontend_build,
        regressions,
    )
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
        "post_research_program_review_hash": manifest[
            "post_research_program_review_hash"
        ],
    }
    record = _with_hash(record_body, "post_research_program_verification_hash")
    target = out / "governance/verification_record_v1.json"
    if target.exists():
        raise ProgramReviewImmutabilityError("Program review already finalized")
    write_json(target, record)
    summary["verification"] = verification
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "FAMILY_A_FORWARD_USE_STATUS",
    "FAMILY_C_FORWARD_USE_STATUS",
    "FAMILY_D_INFRASTRUCTURE_PRIORITY",
    "FAMILY_F_INFRASTRUCTURE_PRIORITY",
    "FAMILY_H_STATUS",
    "MANIFEST_VERSION",
    "NEXT_PROGRAM_PRIMARY_DIRECTION",
    "NEXT_PROGRAM_SECONDARY_DIRECTION",
    "OPTION_IDS",
    "REPORT_NAMES",
    "STRATEGY_RESEARCH_PROGRAM_STATUS",
    "STRATEGY_V2_STATUS",
    "build_post_research_strategy_program_review",
    "finalize_post_research_strategy_program_review",
    "output_root",
    "verify_program_review_inputs",
)
