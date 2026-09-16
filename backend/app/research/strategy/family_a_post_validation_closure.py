from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.11 / Command 01"
COMMAND_VERSION = "FAMILY_A_POST_VALIDATION_CLOSURE_V1"
COMMAND_PROFILE = "MOM_A_002_CANDIDATE_REJECTION_GOVERNANCE_V1"
MANIFEST_VERSION = "FAMILY_A_POST_VALIDATION_CLOSURE_MANIFEST_V1"

FORMAL_MANIFEST_HASH = "e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8"
FORMAL_RESULT_HASH = "be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9"
ROOT_CAUSE_AUDIT_HASH = "a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793"
CA_REMEDIATION_HASH = "ecdacd4dc4c348fe9002928fe37f78381e8833d2c5fb3cfa611e62237161db00"
POST_OUTCOME_MANIFEST_HASH = "9323d59c72e1178379664706f5562abc00c1c7ca425ffd06baf431c3a977370b"
POST_OUTCOME_RESULT_HASH = "075f8edaf033566d1719c043ff4460ac2c12eca990d0e7f9250b62ba960356b6"
DEVELOPMENT_RESULT_HASH = "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27"
CROSS_FAMILY_SYNTHESIS_HASH = "d05826bfae334b64a759b81de5864b25cc076da0267ac36d7b926a67f865d64e"
CANDIDATE_IDENTITY_HASH = "0e8ef3cc26d4146258f25fdd4c269867a383d2f098d9df0e367d4b0ff86beacc"

FAMILY_A_VALIDATION_CANDIDATE_STATUS = "CLOSED_NOT_ADVANCED"
FAMILY_A_STRATEGY_V2_CANDIDACY = "REJECTED_FOR_CURRENT_CYCLE"
FAMILY_A_FORMAL_VALIDATION_STATUS = "INCONCLUSIVE"
FAMILY_A_POST_OUTCOME_EVIDENCE_STATUS = "UNSUPPORTIVE"
FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION = "INSUFFICIENT_SUPPORT_FOR_ADVANCEMENT"
STRATEGY_V2_STATUS = "NOT_CREATED"
FAMILY_A_POST_VALIDATION_TUNING = "PROHIBITED_ON_CURRENT_HOLDOUT"
FAMILY_A_2025_2026_HOLDOUT_STATUS = "CONTAMINATED_FOR_FUTURE_MODEL_SELECTION"
STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS = "COMPLETE_NO_VALIDATED_STRATEGY"
PRODUCTION_READINESS = "NO"
PAPER_TRADING_READINESS = "NO_VALIDATED_CANDIDATE"
LIVE_TRADING_READINESS = "NOT_READY"
FAMILY_H_STATUS = "NOT_PLANNED"
NEXT_PLANNED_PHASE = "POST_RESEARCH_STRATEGY_PROGRAM_REVIEW"
NEGATIVE_EVIDENCE_ID = "EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001"

POST_OUTCOME_CAVEAT = (
    "This evaluation was performed after the original validation outcomes were "
    "observed and after a proven implementation defect was remediated. It is "
    "therefore post-outcome remediated evidence and must not be represented as "
    "pristine one-shot holdout validation."
)

REPORT_NAMES = (
    "family_a_post_validation_closure_v1_summary.json",
    "family_a_post_validation_closure_v1_evidence.csv",
    "family_a_post_validation_closure_v1_lessons.csv",
    "family_a_post_validation_closure_v1_cycle_status.csv",
    "family_a_post_validation_closure_v1_handoff.csv",
)


class FamilyAPostValidationClosureInputMismatch(RuntimeError):
    pass


class FamilyAPostValidationClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/validation/family_a/v1/post_validation_closure"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _verified_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _read_json(path)
    if document.get(field) != expected or _document_hash(document, field) != expected:
        raise FamilyAPostValidationClosureInputMismatch(
            f"Immutable dependency mismatch: {path}"
        )
    return document


def verify_closure_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    formal_manifest = _verified_document(
        root
        / "data/research/validation/family_a/v1/evaluation/manifests/"
        "family_a_one_shot_validation_manifest_v1.json",
        "family_a_one_shot_validation_manifest_hash",
        FORMAL_MANIFEST_HASH,
    )
    formal_result = _verified_document(
        root
        / "data/research/validation/family_a/v1/evaluation/results/validation_result_v1.json",
        "family_a_validation_result_hash",
        FORMAL_RESULT_HASH,
    )
    audit = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_validation_ca_audit/manifests/"
        "family_a_post_validation_ca_audit_manifest_v1.json",
        "family_a_post_validation_ca_audit_manifest_hash",
        ROOT_CAUSE_AUDIT_HASH,
    )
    remediation = _verified_document(
        root
        / "data/research/validation/family_a/v1/ca_remediation/manifests/"
        "family_a_ca_lookback_remediation_manifest_v1.json",
        "family_a_ca_lookback_remediation_manifest_hash",
        CA_REMEDIATION_HASH,
    )
    post_manifest = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_outcome_remediated/manifests/"
        "family_a_post_outcome_remediated_validation_manifest_v1.json",
        "family_a_post_outcome_remediated_validation_manifest_hash",
        POST_OUTCOME_MANIFEST_HASH,
    )
    post_result = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_outcome_remediated/results/"
        "post_outcome_result_v1.json",
        "family_a_post_outcome_result_hash",
        POST_OUTCOME_RESULT_HASH,
    )
    post_summary = _read_json(
        root / "data/reports/family_a_post_outcome_v1_summary.json"
    )
    development = _verified_document(
        root
        / "data/research/strategy_families/family_a/v1/phase2/development_evaluation/"
        "a2_002/development_result_v1.json",
        "development_result_hash",
        DEVELOPMENT_RESULT_HASH,
    )
    synthesis = _verified_document(
        root
        / "data/research/cross_family_synthesis/v1/manifests/"
        "cross_family_evidence_synthesis_manifest_v1.json",
        "cross_family_synthesis_hash",
        CROSS_FAMILY_SYNTHESIS_HASH,
    )
    checks = {
        "formal_validation_inconclusive": formal_result.get("VALIDATION_RESULT")
        == "INCONCLUSIVE",
        "formal_generalization_inconclusive": formal_result.get(
            "FAMILY_A_GENERALIZATION_RESULT"
        )
        == "INCONCLUSIVE",
        "formal_strategy_v2_no_decision": formal_result.get(
            "STRATEGY_V2_ADVANCEMENT_STATUS"
        )
        == "NO_DECISION",
        "formal_run_consumed": formal_result.get("completed_valid_formal_runs") == 1
        and formal_result.get("remaining_formal_runs") == 0,
        "root_cause_exact": audit.get("root_cause")
        == "IMPLEMENTATION_LOGIC_DEFECT",
        "remediation_exact": remediation.get("technical_readiness", {}).get(
            "FAMILY_A_CA_REMEDIATION_RESULT"
        )
        == "FIX_VERIFIED_STRUCTURALLY",
        "post_outcome_evidence_class": post_result.get("EVIDENCE_CLASS")
        == "POST_OUTCOME_REMEDIATED_VALIDATION",
        "post_outcome_not_pristine": post_result.get("PRISTINE_HOLDOUT_EVIDENCE")
        == "NO",
        "post_outcome_not_formal_replacement": post_result.get(
            "FORMAL_ONE_SHOT_REPLACEMENT"
        )
        == "NO",
        "post_outcome_fail": post_result.get("POST_OUTCOME_REMEDIATED_RESULT")
        == "FAIL",
        "post_outcome_unsupportive": post_result.get(
            "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"
        )
        == "UNSUPPORTIVE",
        "post_outcome_review_rejects": post_result.get(
            "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"
        )
        == "DOES_NOT_SUPPORT_CANDIDATE_REVIEW",
        "post_outcome_review_complete": post_summary.get("verification", {}).get(
            "ready_for_review"
        )
        is True,
        "candidate_unchanged": post_result.get("candidate_changed") is False,
        "criteria_unchanged": post_result.get("criteria_changed") is False,
        "strategy_v2_absent": post_result.get("strategy_v2_created") is False,
        "development_reference_exact": development.get("experiment_id") == "A2-002"
        and development.get("reference_experiment_id") == "MOM-A-002"
        and development.get("performance", {}).get("net_total_return_pct")
        == "91.0663359800",
        "cross_family_synthesis_exact": synthesis.get("manifest_version")
        == "CROSS_FAMILY_EVIDENCE_SYNTHESIS_MANIFEST_V1",
    }
    if not all(checks.values()):
        raise FamilyAPostValidationClosureInputMismatch(
            f"FAMILY_A_POST_VALIDATION_CLOSURE_INPUT_MISMATCH: {checks}"
        )
    return {
        "checks": checks,
        "formal_manifest": formal_manifest,
        "formal_result": formal_result,
        "audit": audit,
        "remediation": remediation,
        "post_manifest": post_manifest,
        "post_result": post_result,
        "post_summary": post_summary,
        "development": development,
        "synthesis": synthesis,
    }


def _protected_artifact_hashes(root: Path) -> dict[str, str]:
    roots = (
        root / "data/research/validation/family_a/v1/evaluation",
        root / "data/research/validation/family_a/v1/post_validation_ca_audit",
        root / "data/research/validation/family_a/v1/ca_remediation",
        root / "data/research/validation/family_a/v1/post_outcome_remediated",
        root / "data/research/cross_family_synthesis/v1",
    )
    paths = [path for base in roots for path in base.rglob("*") if path.is_file()]
    paths.append(
        root
        / "data/research/strategy_families/family_a/v1/phase2/development_evaluation/"
        "a2_002/development_result_v1.json"
    )
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }


def _with_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def final_status_document() -> dict[str, Any]:
    body = {
        "status_version": "FAMILY_A_POST_VALIDATION_FINAL_STATUS_V1",
        "FAMILY_A_VALIDATION_CANDIDATE_STATUS": FAMILY_A_VALIDATION_CANDIDATE_STATUS,
        "FAMILY_A_STRATEGY_V2_CANDIDACY": FAMILY_A_STRATEGY_V2_CANDIDACY,
        "FAMILY_A_FORMAL_VALIDATION_STATUS": FAMILY_A_FORMAL_VALIDATION_STATUS,
        "FAMILY_A_POST_OUTCOME_EVIDENCE_STATUS": FAMILY_A_POST_OUTCOME_EVIDENCE_STATUS,
        "FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION": FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION,
        "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        "INTERSIGNAL_AUTOMATED_STRATEGY_PRODUCTION_READINESS": PRODUCTION_READINESS,
        "INTERSIGNAL_STRATEGY_PAPER_TRADING_READINESS": PAPER_TRADING_READINESS,
        "INTERSIGNAL_LIVE_TRADING_READINESS": LIVE_TRADING_READINESS,
        "FAMILY_H_STATUS": FAMILY_H_STATUS,
        "decision_reason": (
            "The formally governed validation remains inconclusive because of an "
            "implementation defect. After independent audit and structural correction, "
            "the exact frozen candidate produced unsupportive post-outcome remediated "
            "evidence under unchanged strategy and criteria. This is not a pristine "
            "validation failure."
        ),
        "formal_record_rewritten": False,
        "strategy_v2_created": False,
        "paper_trading_started": False,
        "live_trading_started": False,
    }
    return _with_hash(body, "family_a_post_validation_final_status_hash")


def no_salvage_policy_document() -> dict[str, Any]:
    body = {
        "policy_version": "FAMILY_A_POST_VALIDATION_NO_SALVAGE_POLICY_V1",
        "FAMILY_A_POST_VALIDATION_TUNING": FAMILY_A_POST_VALIDATION_TUNING,
        "known_holdout": "2025-01-01_THROUGH_2026-08-13",
        "prohibited_on_known_holdout": [
            "3M_MOMENTUM",
            "9M_MOMENTUM",
            "12M_MOMENTUM",
            "MONTHLY_REBALANCE",
            "DIFFERENT_TOP_PERCENTILE",
            "DIFFERENT_PRICE_THRESHOLD",
            "DIFFERENT_LIQUIDITY_THRESHOLD",
            "SMA_FILTERS",
            "COMPRESSION_FILTERS",
            "REGIME_OVERLAYS",
            "DIFFERENT_COSTS",
            "DIFFERENT_CAPITAL",
        ],
        "variant_tested_by_closure": False,
        "performance_rerun_by_closure": False,
    }
    return _with_hash(body, "family_a_no_salvage_policy_hash")


def holdout_status_document() -> dict[str, Any]:
    body = {
        "status_version": "FAMILY_A_2025_2026_HOLDOUT_STATUS_V1",
        "FAMILY_A_2025_2026_HOLDOUT_STATUS": FAMILY_A_2025_2026_HOLDOUT_STATUS,
        "reason": "OUTCOMES_ARE_NOW_KNOWN",
        "permitted_uses": ["DIAGNOSTICS", "DOCUMENTATION"],
        "prohibited_use": "UNSEEN_VALIDATION_FOR_CANDIDATE_SELECTION",
        "future_model_selection_requirement": "NEW_TEMPORALLY_UNSEEN_PERIOD",
        "possible_source": "FORWARD_OR_PAPER_OBSERVATION_AFTER_CURRENT_RESEARCH_FREEZE",
        "future_dates_defined": False,
    }
    return _with_hash(body, "family_a_holdout_status_hash")


def lesson_documents() -> dict[str, dict[str, Any]]:
    development_body = {
        "lesson_version": "FAMILY_A_DEVELOPMENT_LESSON_V1",
        "lesson": (
            "Strong 2022–2024 development performance did not provide sufficient "
            "evidence of stable generalization into the later period. This reinforces "
            "the need for independent temporal validation."
        ),
        "development_net_return_pct": "91.06633598",
        "development_cagr_pct": "24.10585067",
        "development_max_drawdown_pct": "22.92216992",
    }
    validation_body = {
        "lesson_version": "FAMILY_A_VALIDATION_LESSON_V1",
        "lesson": (
            "Validation integrity depends on causal prehistory and data-pipeline parity "
            "between DEVELOPMENT and VALIDATION. Truncating feature or eligibility "
            "history at the validation boundary can create false eligibility failures."
        ),
        "root_cause": "IMPLEMENTATION_LOGIC_DEFECT",
        "remediation": "CAUSAL_PREHISTORY_SESSION_PLUMBING_RESTORED",
    }
    performance_body = {
        "lesson_version": "FAMILY_A_PERFORMANCE_LESSON_V1",
        "lesson": "The corrected later-period evidence did not retain the development edge.",
        "development_cagr_pct": "24.10585067",
        "post_outcome_remediated_cagr_pct": "-2.438579367208471",
        "post_outcome_caveat": POST_OUTCOME_CAVEAT,
        "interpretation": "DESCRIPTIVE_POST_OUTCOME_EVIDENCE",
    }
    win_rate_body = {
        "lesson_version": "FAMILY_A_NO_WIN_RATE_CHASING_V1",
        "desired_win_rate_pct": "60_TO_65_ASPIRATION_ONLY",
        "policy": "NO_STRATEGY_MAY_BE_MODIFIED_SOLELY_TO_ACHIEVE_A_TARGET_WIN_RATE",
        "threshold_or_selection_gate": False,
    }
    return {
        "development": _with_hash(development_body, "family_a_development_lesson_hash"),
        "validation": _with_hash(validation_body, "family_a_validation_lesson_hash"),
        "performance": _with_hash(performance_body, "family_a_performance_lesson_hash"),
        "win_rate": _with_hash(win_rate_body, "family_a_win_rate_policy_hash"),
    }


def evidence_rows() -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": "EDGE-POSITIVE-A-DEVELOPMENT-001",
            "family": "A",
            "category": "POSITIVE_DEVELOPMENT_EVIDENCE",
            "status": "HISTORICALLY_STRONG_DEVELOPMENT_EVIDENCE_NOT_GENERALIZED",
            "finding": "Strong 2022-2024 after-cost development performance.",
            "source_hash": DEVELOPMENT_RESULT_HASH,
        },
        {
            "evidence_id": "EDGE-POSITIVE-A-FAMILY-G-REPRODUCTION-001",
            "family": "A/G",
            "category": "POSITIVE_DEVELOPMENT_EVIDENCE",
            "status": "PRESERVED",
            "finding": "Family G independently reproduced the ungated Family A control behavior.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EDGE-POSITIVE-A-IMPLEMENTATION-REALISM-001",
            "family": "A",
            "category": "IMPLEMENTATION_EVIDENCE",
            "status": "PRESERVED",
            "finding": "Whole-share INR 500k implementation and quarterly architecture were feasible.",
            "source_hash": DEVELOPMENT_RESULT_HASH,
        },
        {
            "evidence_id": "EVIDENCE-A-FORMAL-VALIDATION-001",
            "family": "A",
            "category": "FORMAL_VALIDATION_EVIDENCE",
            "status": "INCONCLUSIVE",
            "finding": "Formal validation remains inconclusive due to an implementation defect.",
            "source_hash": FORMAL_RESULT_HASH,
        },
        {
            "evidence_id": NEGATIVE_EVIDENCE_ID,
            "family": "A",
            "category": "NEGATIVE_EVIDENCE",
            "status": "POST_OUTCOME_REMEDIATED_EVIDENCE",
            "finding": (
                "The exact frozen MOM-A-002 / A2-002 architecture produced unsupportive "
                "later-period results under corrected CA eligibility semantics."
            ),
            "source_hash": POST_OUTCOME_RESULT_HASH,
        },
        {
            "evidence_id": "DATA-LESSON-A-CAUSAL-PREHISTORY-001",
            "family": "A",
            "category": "DATA_QUALITY_LESSON",
            "status": "PRESERVED",
            "finding": "Feature and eligibility history must preserve causal prehistory at validation boundaries.",
            "source_hash": CA_REMEDIATION_HASH,
        },
        {
            "evidence_id": "EVIDENCE-B-NEGATIVE-DEVELOPMENT-001",
            "family": "B",
            "category": "NEGATIVE_EVIDENCE",
            "status": "NO_INCREMENTAL_EDGE",
            "finding": "No clear incremental edge over relative momentum.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EVIDENCE-C-COMPRESSION-001",
            "family": "C",
            "category": "REUSABLE_SIGNAL_EVIDENCE",
            "status": "SIGNAL_ONLY_NOT_PORTFOLIO_READY",
            "finding": "Compression remains reusable signal evidence only.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EVIDENCE-D-DATA-BLOCKED-001",
            "family": "D",
            "category": "BLOCKED_RESEARCH",
            "status": "DATA_BLOCKED",
            "finding": "Intraday continuity was below the frozen readiness threshold.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EVIDENCE-E-NEGATIVE-DEVELOPMENT-001",
            "family": "E",
            "category": "NEGATIVE_EVIDENCE",
            "status": "NOT_SUPPORTED",
            "finding": "Pullback/reclaim development evidence was negative.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EVIDENCE-F-SOURCE-BLOCKED-001",
            "family": "F",
            "category": "BLOCKED_RESEARCH",
            "status": "SOURCE_LICENSING_BLOCKED",
            "finding": "Catalyst history remains blocked by source authorization.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
        {
            "evidence_id": "EVIDENCE-G-NEGATIVE-OVERLAY-001",
            "family": "G",
            "category": "NEGATIVE_EVIDENCE",
            "status": "REGIME_OVERLAY_NOT_SUPPORTED",
            "finding": "The exact regime overlay was not supported for advancement.",
            "source_hash": CROSS_FAMILY_SYNTHESIS_HASH,
        },
    ]


def evidence_registry_document() -> dict[str, Any]:
    body = {
        "registry_version": "A_TO_G_FINAL_GOVERNANCE_EVIDENCE_REGISTRY_V1",
        "frozen_family_artifacts_changed": False,
        "rows": evidence_rows(),
    }
    return _with_hash(body, "a_to_g_final_governance_evidence_registry_hash")


def cycle_closure_document() -> dict[str, Any]:
    rows = [
        {"family": "A", "summary": "STRONG_DEVELOPMENT_NOT_ADVANCED_AFTER_LATER_PERIOD_EVIDENCE"},
        {"family": "B", "summary": "NO_INCREMENTAL_EDGE"},
        {"family": "C", "summary": "REUSABLE_COMPRESSION_SIGNAL_ONLY"},
        {"family": "D", "summary": "DATA_BLOCKED"},
        {"family": "E", "summary": "NEGATIVE_DEVELOPMENT_EVIDENCE"},
        {"family": "F", "summary": "SOURCE_LICENSING_BLOCKED"},
        {"family": "G", "summary": "NEGATIVE_REGIME_OVERLAY_EVIDENCE"},
    ]
    body = {
        "cycle_closure_version": "STRATEGY_DISCOVERY_A_TO_G_CYCLE_CLOSURE_V1",
        "STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS": STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS,
        "families": rows,
        "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        "FAMILY_H_STATUS": FAMILY_H_STATUS,
    }
    return _with_hash(body, "strategy_discovery_a_to_g_cycle_closure_hash")


def handoff_document() -> dict[str, Any]:
    options = [
        {
            "option": "A",
            "description": "Wait for new unseen market data and forward-test frozen hypotheses.",
        },
        {
            "option": "B",
            "description": "Design a fundamentally new research architecture.",
        },
        {
            "option": "C",
            "description": "Prioritize unresolved Family D/F infrastructure.",
        },
        {
            "option": "D",
            "description": "Focus on portfolio/product infrastructure before new strategy research.",
        },
    ]
    body = {
        "policy_version": "NEXT_RESEARCH_CYCLE_POLICY_V1",
        "NEXT_PLANNED_PHASE": NEXT_PLANNED_PHASE,
        "purpose": "CHOOSE_PROGRAM_DIRECTION_WITHOUT_AUTOMATIC_EXECUTION",
        "new_cycle_requirement": "EXPLICIT_RESEARCH_HYPOTHESIS_BASED_ON_A_TO_G_LESSONS",
        "sequential_family_extension_default": "PROHIBITED",
        "future_validation_data_policy": "NEW_TEMPORALLY_UNSEEN_PERIOD_REQUIRED",
        "possible_future_source": "FORWARD_OR_PAPER_OBSERVATION_AFTER_CURRENT_RESEARCH_FREEZE",
        "future_dates_defined": False,
        "options": options,
        "option_selected": None,
        "next_phase_started": False,
    }
    return _with_hash(body, "next_research_cycle_policy_hash")


def _lesson_rows(lessons: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "lesson": name.upper(),
            "version": document["lesson_version"],
            "statement": document.get("lesson", document.get("policy")),
        }
        for name, document in lessons.items()
    ]


def _cycle_rows(
    status: Mapping[str, Any], cycle: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = [
        {"scope": "A_TO_G", "status": cycle["STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS"]}
    ]
    rows.extend(
        {"scope": f"FAMILY_{row['family']}", "status": row["summary"]}
        for row in cycle["families"]
    )
    rows.extend(
        [
            {"scope": "STRATEGY_V2", "status": status["STRATEGY_V2_STATUS"]},
            {"scope": "PAPER_TRADING", "status": status["INTERSIGNAL_STRATEGY_PAPER_TRADING_READINESS"]},
            {"scope": "LIVE_TRADING", "status": status["INTERSIGNAL_LIVE_TRADING_READINESS"]},
            {"scope": "FAMILY_H", "status": status["FAMILY_H_STATUS"]},
        ]
    )
    return rows


def _ensure_fresh(root: Path) -> None:
    destination = output_root(root)
    staging = destination.parent / ".post_validation_closure_staging_v1"
    reports = [root / "data/reports" / name for name in REPORT_NAMES]
    existing = [path for path in (destination, staging, *reports) if path.exists()]
    if existing:
        raise FamilyAPostValidationClosureImmutabilityError(
            "FAMILY_A_POST_VALIDATION_CLOSURE_ALREADY_EXISTS: "
            + ", ".join(str(path) for path in existing)
        )


def _seal_outputs(
    root: Path,
    *,
    evidence: Mapping[str, Any],
    final_status: Mapping[str, Any],
    no_salvage: Mapping[str, Any],
    holdout: Mapping[str, Any],
    lessons: Mapping[str, Mapping[str, Any]],
    cycle: Mapping[str, Any],
    handoff: Mapping[str, Any],
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    final = output_root(root)
    staging = final.parent / ".post_validation_closure_staging_v1"
    report_staging = staging / "_reports"
    write_json(staging / "evidence/final_evidence_registry_v1.json", evidence)
    write_csv(staging / "evidence/final_evidence_registry_v1.csv", evidence["rows"])
    write_json(
        staging / "evidence/family_a_later_period_negative_evidence_v1.json",
        next(row for row in evidence["rows"] if row["evidence_id"] == NEGATIVE_EVIDENCE_ID),
    )
    write_json(staging / "governance/family_a_final_status_v1.json", final_status)
    write_json(staging / "governance/no_salvage_policy_v1.json", no_salvage)
    write_json(staging / "governance/holdout_status_v1.json", holdout)
    write_json(staging / "lessons/family_a_development_lesson_v1.json", lessons["development"])
    write_json(staging / "lessons/family_a_validation_lesson_v1.json", lessons["validation"])
    write_json(staging / "lessons/family_a_performance_lesson_v1.json", lessons["performance"])
    write_json(staging / "lessons/no_win_rate_chasing_v1.json", lessons["win_rate"])
    write_json(staging / "cycle_closure/a_to_g_final_status_v1.json", cycle)
    write_csv(staging / "cycle_closure/a_to_g_final_summary_v1.csv", cycle["families"])
    write_json(staging / "handoff/next_research_cycle_policy_v1.json", handoff)
    write_csv(staging / "handoff/program_review_options_v1.csv", handoff["options"])
    write_json(
        staging / "manifests/family_a_post_validation_closure_manifest_v1.json",
        manifest,
    )

    write_json(report_staging / REPORT_NAMES[0], summary)
    write_csv(report_staging / REPORT_NAMES[1], evidence["rows"])
    write_csv(report_staging / REPORT_NAMES[2], _lesson_rows(lessons))
    write_csv(report_staging / REPORT_NAMES[3], _cycle_rows(final_status, cycle))
    write_csv(report_staging / REPORT_NAMES[4], handoff["options"])

    staging.replace(final)
    for source in list((final / "_reports").iterdir()):
        destination = root / "data/reports" / source.name
        source.replace(destination)
    (final / "_reports").rmdir()


def build_family_a_post_validation_closure(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _ensure_fresh(root)
    inputs = verify_closure_inputs(root)
    protected_before = _protected_artifact_hashes(root)
    created_at = utc_now()
    final_status = final_status_document()
    no_salvage = no_salvage_policy_document()
    holdout = holdout_status_document()
    lessons = lesson_documents()
    evidence = evidence_registry_document()
    cycle = cycle_closure_document()
    handoff = handoff_document()
    protected_after = _protected_artifact_hashes(root)
    if protected_before != protected_after:
        raise FamilyAPostValidationClosureInputMismatch(
            "Protected validation or family evidence changed during closure"
        )

    component_hashes = {
        "family_a_post_validation_final_status_hash": final_status[
            "family_a_post_validation_final_status_hash"
        ],
        "family_a_no_salvage_policy_hash": no_salvage[
            "family_a_no_salvage_policy_hash"
        ],
        "family_a_holdout_status_hash": holdout["family_a_holdout_status_hash"],
        "family_a_development_lesson_hash": lessons["development"][
            "family_a_development_lesson_hash"
        ],
        "family_a_validation_lesson_hash": lessons["validation"][
            "family_a_validation_lesson_hash"
        ],
        "family_a_performance_lesson_hash": lessons["performance"][
            "family_a_performance_lesson_hash"
        ],
        "family_a_win_rate_policy_hash": lessons["win_rate"][
            "family_a_win_rate_policy_hash"
        ],
        "a_to_g_final_governance_evidence_registry_hash": evidence[
            "a_to_g_final_governance_evidence_registry_hash"
        ],
        "strategy_discovery_a_to_g_cycle_closure_hash": cycle[
            "strategy_discovery_a_to_g_cycle_closure_hash"
        ],
        "next_research_cycle_policy_hash": handoff[
            "next_research_cycle_policy_hash"
        ],
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": created_at,
        "formal_validation": {
            "manifest_hash": FORMAL_MANIFEST_HASH,
            "result_hash": FORMAL_RESULT_HASH,
            "FAMILY_A_FORMAL_VALIDATION_STATUS": FAMILY_A_FORMAL_VALIDATION_STATUS,
            "formal_generalization_result": "INCONCLUSIVE",
            "formal_strategy_v2_advancement": "NO_DECISION",
            "rewritten": False,
        },
        "root_cause_audit_hash": ROOT_CAUSE_AUDIT_HASH,
        "CA_remediation_hash": CA_REMEDIATION_HASH,
        "post_outcome_remediated": {
            "manifest_hash": POST_OUTCOME_MANIFEST_HASH,
            "result_hash": POST_OUTCOME_RESULT_HASH,
            "evidence_class": "POST_OUTCOME_REMEDIATED_VALIDATION",
            "result": "FAIL",
            "generalization_indication": "UNSUPPORTIVE",
            "strategy_v2_review_status": "DOES_NOT_SUPPORT_CANDIDATE_REVIEW",
            "pristine_holdout": False,
            "formal_replacement": False,
        },
        "development_reference": {
            "result_hash": DEVELOPMENT_RESULT_HASH,
            "candidate_identity_hash": CANDIDATE_IDENTITY_HASH,
            "net_return_pct": "91.06633598",
            "net_cagr_pct": "24.10585067",
            "max_drawdown_pct": "22.92216992",
            "classification": "HISTORICALLY_STRONG_DEVELOPMENT_EVIDENCE_NOT_GENERALIZED",
        },
        "candidate_final_status": FAMILY_A_VALIDATION_CANDIDATE_STATUS,
        "family_a_strategy_v2_candidacy": FAMILY_A_STRATEGY_V2_CANDIDACY,
        "current_generalization_conclusion": FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION,
        "strategy_v2_status": STRATEGY_V2_STATUS,
        "holdout_contamination_state": FAMILY_A_2025_2026_HOLDOUT_STATUS,
        "post_validation_tuning_policy": FAMILY_A_POST_VALIDATION_TUNING,
        "a_to_g_final_status": STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS,
        "readiness": {
            "automated_strategy_production": PRODUCTION_READINESS,
            "paper_trading": PAPER_TRADING_READINESS,
            "live_trading": LIVE_TRADING_READINESS,
        },
        "family_h_status": FAMILY_H_STATUS,
        "next_phase_planning": {
            "NEXT_PLANNED_PHASE": NEXT_PLANNED_PHASE,
            "started": False,
            "option_selected": None,
        },
        "component_hashes": component_hashes,
        "proof_protected_artifacts_unchanged": {
            "unchanged": True,
            "file_hashes_before": protected_before,
            "file_hashes_after": protected_after,
        },
        "performance_rerun": False,
        "strategy_mutation": False,
        "new_strategy_created": False,
        "strategy_v2_created": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "family_h_created": False,
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
    manifest = _with_hash(manifest_body, "family_a_post_validation_closure_hash")
    summary = {
        **manifest,
        "inputs_verified": inputs["checks"],
        "final_status": final_status,
        "no_salvage_policy": no_salvage,
        "holdout_status": holdout,
        "lessons": lessons,
        "evidence_registry": evidence,
        "cycle_closure": cycle,
        "handoff": handoff,
        "manifest_path": (
            output_root(root)
            / "manifests/family_a_post_validation_closure_manifest_v1.json"
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
        evidence=evidence,
        final_status=final_status,
        no_salvage=no_salvage,
        holdout=holdout,
        lessons=lessons,
        cycle=cycle,
        handoff=handoff,
        manifest=manifest,
        summary=summary,
    )
    return summary


def finalize_family_a_post_validation_closure(
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
        out / "manifests/family_a_post_validation_closure_manifest_v1.json"
    )
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    if _document_hash(manifest, "family_a_post_validation_closure_hash") != manifest.get(
        "family_a_post_validation_closure_hash"
    ):
        raise FamilyAPostValidationClosureInputMismatch("Closure manifest mismatch")
    if _protected_artifact_hashes(root) != manifest[
        "proof_protected_artifacts_unchanged"
    ]["file_hashes_after"]:
        raise FamilyAPostValidationClosureInputMismatch("Protected artifacts changed")
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
        "closure_manifest_unchanged": True,
        "protected_artifacts_unchanged": True,
    }
    record_body = {
        "verification": verification,
        "family_a_post_validation_closure_hash": manifest[
            "family_a_post_validation_closure_hash"
        ],
    }
    record = _with_hash(record_body, "family_a_post_validation_verification_hash")
    path = out / "governance/verification_record_v1.json"
    if path.exists():
        raise FamilyAPostValidationClosureImmutabilityError(
            "Closure verification already finalized"
        )
    write_json(path, record)
    summary["verification"] = verification
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "FAMILY_A_2025_2026_HOLDOUT_STATUS",
    "FAMILY_A_CURRENT_GENERALIZATION_CONCLUSION",
    "FAMILY_A_FORMAL_VALIDATION_STATUS",
    "FAMILY_A_POST_OUTCOME_EVIDENCE_STATUS",
    "FAMILY_A_POST_VALIDATION_TUNING",
    "FAMILY_A_STRATEGY_V2_CANDIDACY",
    "FAMILY_A_VALIDATION_CANDIDATE_STATUS",
    "FAMILY_H_STATUS",
    "MANIFEST_VERSION",
    "NEGATIVE_EVIDENCE_ID",
    "NEXT_PLANNED_PHASE",
    "PAPER_TRADING_READINESS",
    "REPORT_NAMES",
    "STRATEGY_DISCOVERY_A_TO_G_FINAL_STATUS",
    "STRATEGY_V2_STATUS",
    "build_family_a_post_validation_closure",
    "finalize_family_a_post_validation_closure",
    "output_root",
    "verify_closure_inputs",
)
