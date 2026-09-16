from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.08 / Command 01"
COMMAND_VERSION = "CROSS_FAMILY_EVIDENCE_SYNTHESIS_V1"
COMMAND_PROFILE = "STRATEGY_DISCOVERY_A_TO_G_SYNTHESIS_V1"
MANIFEST_VERSION = "CROSS_FAMILY_EVIDENCE_SYNTHESIS_MANIFEST_V1"
MILESTONE_COMMIT = "a405e9ffef9cd1c9de3d9f9b92ff6b2547e1bdd1"

PRIMARY_QUESTION_RESULT = "YES"
FAMILY_A_VALIDATION_CANDIDACY = "PASS"
CANDIDATE_SELECTION_CLASSIFICATION = "SINGLE_LEADING_CANDIDATE"
PROVISIONAL_CANDIDATE_ID = "PROVISIONAL_VALIDATION_CANDIDATE_V1"
PROVISIONAL_CANDIDATE_STATUS = "SELECTED_FOR_VALIDATION_DESIGN_ONLY"
VALIDATION_DESIGN_READINESS = "YES"
NEXT_PLANNED_PHASE = "DESIGN_FAMILY_A_VALIDATION"
FAMILY_H_STATUS = "NOT_PLANNED"
STRATEGY_V2_STATUS = "NOT_CREATED"
DISCOVERY_CYCLE_STATUS = "COMPLETE_FOR_CURRENT_RESEARCH_CYCLE"

CLASSIFICATION_BUCKETS = (
    "VALIDATION_CANDIDATE",
    "PROMISING_BUT_NOT_READY",
    "REUSABLE_SIGNAL_EVIDENCE",
    "DATA_BLOCKED",
    "SOURCE_BLOCKED",
    "NEGATIVE_DEVELOPMENT_EVIDENCE",
    "REJECTED_VALIDATION",
    "INCONCLUSIVE",
)
DIMENSION_VALUES = ("STRONG", "MODERATE", "WEAK", "NOT_AVAILABLE", "BLOCKED")

FAMILY_CLOSURE_HASHES = {
    "A": "51e2190c25f3146609ac173cc345e2a8adc0b6c9efb824633d735dc976581250",
    "B": "32e510424551e01fd54aac4711fa90fa08c711856c80b812d797b3a2f8faf6b0",
    "C": "e1146522bed8e81b87af8123f481045697a788c3af9e3f7654279b20724910d1",
    "D": "1628774e5a6032487ac6e15e9beba21cbf52c96389b83aca7d4e87a46e577414",
    "E": "4899cdbfe54b0ea636faa8ff0b4504b6ef60242e7eabdf682b2b913cfb001c00",
    "F": "515bd3dc996c1e119e3e422f182ba82abfa8f2d312346df2c7a5751322d7716d",
    "G": "2cb2102b207da24b4730cd673869aab1c00534ae8fa09c281639aafaaee6c179",
}

FAMILY_FINAL_STATUSES = {
    "A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
    "B": "PAUSED_NO_VALIDATION_CANDIDATE",
    "C": "PAUSED_NO_VALIDATION_CANDIDATE",
    "D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
    "E": "PAUSED_NO_VALIDATION_CANDIDATE",
    "F": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
    "G": "PAUSED_NO_VALIDATION_CANDIDATE",
}

FAMILY_CLASSIFICATIONS = {
    "A": "VALIDATION_CANDIDATE",
    "B": "NEGATIVE_DEVELOPMENT_EVIDENCE",
    "C": "REUSABLE_SIGNAL_EVIDENCE",
    "D": "DATA_BLOCKED",
    "E": "NEGATIVE_DEVELOPMENT_EVIDENCE",
    "F": "SOURCE_BLOCKED",
    "G": "NEGATIVE_DEVELOPMENT_EVIDENCE",
}

INPUT_FILE_HASHES = {
    "data/reports/strategy_diagnostic_v1_synthesis_summary.json": (
        "fd8ecb0dcb45d86bffcc88cc9404b3391398b16e848ae8eac86b10ff9d35ea48"
    ),
    "data/reports/rr_cap4_validation_v1_summary.json": (
        "0ddee689c39a47774dcdd9e3bba12be6f8a42975303f31c9b54aa1c7bcd23daf"
    ),
    "data/reports/family_a_closure_v1_summary.json": (
        "beb80a111c30ff6a6e4221cea3f461101b52e16453d8bbecdd84056f512fff7c"
    ),
    "data/reports/family_b_closure_v1_summary.json": (
        "65d5d5c378461b30451c27552a984ee3f1f5dbf79e9d47ad719d273b24a76c81"
    ),
    "data/reports/family_c_closure_v1_summary.json": (
        "111adf1b113aded2852817d0c99c30f6efb9aaa2768bc55125767c41be311e71"
    ),
    "data/reports/family_d_closure_v1_summary.json": (
        "f7950808a519ce78a4b9eae775dcf339be27aa1c93e1902c3415bfefd50edc9c"
    ),
    "data/reports/family_e_closure_v1_summary.json": (
        "f10c1e7b5c760b8b169b523392325a003554f83ef758943a72d2734bcb883121"
    ),
    "data/reports/family_f_closure_v1_summary.json": (
        "d09b6ac29584e52e014c9e9a59b3630f56bc60ff50676187d559cabb3be2b1d1"
    ),
    "data/reports/family_g_closure_v1_summary.json": (
        "8658f912c42d1d3274a3f48999c85a5ec79db9c2305acb6e591a1a1ee7b43867"
    ),
    "data/research/strategy_families/family_d/v1/closure/manifest/family_d_closure_manifest_v1.json": (
        "eeb7058c892422f8f88df6a61abd28f4f09e2880b32556449a049ef0542bd559"
    ),
    "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json": (
        "92a74e267806ca38c2409c105d6d7acac5b8cc6bd84cb7fc603e2ff5c9698135"
    ),
    "data/research/strategy_families/family_a/v1/phase2/registry/a2_002_preregistration_v1.json": (
        "261ee7e8c6a4a5a96b8027a3ac35d20ebc267d9d4592c270f9d1ed65eea30065"
    ),
    "data/research/strategy_families/family_a/v1/phase2/development_evaluation/a2_002/development_result_v1.json": (
        "083350f4a86b4ff502814159dc4b39c02c7d05ad88e7f7daf9b1422e089d367d"
    ),
}

REPORT_NAMES = (
    "cross_family_synthesis_v1_summary.json",
    "cross_family_synthesis_v1_family_matrix.csv",
    "cross_family_synthesis_v1_evidence_dimensions.csv",
    "cross_family_synthesis_v1_positive_evidence.csv",
    "cross_family_synthesis_v1_negative_evidence.csv",
    "cross_family_synthesis_v1_blocked_research.csv",
    "cross_family_synthesis_v1_candidate_gate.csv",
    "cross_family_synthesis_v1_validation_risks.csv",
    "cross_family_synthesis_v1_recommendation.csv",
)

CONTAMINATION_DISCLOSURE = (
    "The project has previously seen aggregate diagnostics over later periods in "
    "other contexts, so formal Family A validation is governed/sealed but cannot be "
    "described as philosophically pristine laboratory-grade unseen data."
)

SYNTHESIS_ROADMAP_COMPONENT_HASH = (
    "f84554613f900a0975042aeb83b210e1364ced7933609f27c4c22beb2311a448"
)
AUTHORIZED_ROADMAP_SUCCESSOR_HASHES = {
    SYNTHESIS_ROADMAP_COMPONENT_HASH,
    "c6356132461b170c5d8b3468c271a490f792390860787426bfad6c737f02cdf9",
}


class CrossFamilySynthesisInputMismatch(RuntimeError):
    pass


class CrossFamilySynthesisImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/cross_family_synthesis/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def verify_git_milestone(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ancestry = _git(root, "merge-base", "--is-ancestor", MILESTONE_COMMIT, "HEAD")
    if any(result.returncode for result in (head, branch, upstream)):
        raise CrossFamilySynthesisInputMismatch("Unable to verify Git checkpoint")
    result = {
        "milestone_commit": MILESTONE_COMMIT,
        "head": head.stdout.strip(),
        "branch": branch.stdout.strip(),
        "upstream": upstream.stdout.strip(),
        "milestone_is_ancestor": ancestry.returncode == 0,
    }
    if result["branch"] != "main" or result["upstream"] != "origin/main":
        raise CrossFamilySynthesisInputMismatch("Unexpected branch or upstream")
    if not result["milestone_is_ancestor"]:
        raise CrossFamilySynthesisInputMismatch("Required milestone is not an ancestor")
    return result


def _closure_hashes(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {
        "A": documents["A"]["closure"]["family_a_closure_hash"],
        "B": documents["B"]["closure"]["family_b_closure_hash"],
        "C": documents["C"]["family_c_closure_hash"],
        "D": documents["D"]["family_d_closure_hash"],
        "E": documents["E"]["family_e_closure_hash"],
        "F": documents["F"]["family_f_closure_hash"],
        "G": documents["G"]["family_g_closure_hash"],
    }


def verify_synthesis_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    missing = [relative for relative in INPUT_FILE_HASHES if not (root / relative).is_file()]
    if missing:
        raise CrossFamilySynthesisInputMismatch(f"Missing synthesis inputs: {missing}")
    observed_hashes = {
        relative: file_sha256(root / relative) for relative in INPUT_FILE_HASHES
    }
    changed = [
        relative
        for relative, expected in INPUT_FILE_HASHES.items()
        if observed_hashes[relative] != expected
    ]
    if changed:
        raise CrossFamilySynthesisInputMismatch(f"Frozen synthesis inputs changed: {changed}")

    reports = root / "data/reports"
    documents = {
        letter: _read_json(reports / f"family_{letter.lower()}_closure_v1_summary.json")
        for letter in "ABCDEFG"
    }
    strategy_v1 = _read_json(reports / "strategy_diagnostic_v1_synthesis_summary.json")
    cap4 = _read_json(reports / "rr_cap4_validation_v1_summary.json")
    d_manifest = _read_json(
        root
        / "data/research/strategy_families/family_d/v1/closure/manifest/"
        "family_d_closure_manifest_v1.json"
    )
    mom_a_002 = _read_json(
        root / "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json"
    )
    a2_002 = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/registry/"
        "a2_002_preregistration_v1.json"
    )
    a2_result = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/"
        "development_evaluation/a2_002/development_result_v1.json"
    )

    statuses = {
        "A": documents["A"]["statuses"]["FAMILY_A_RESEARCH_STATUS"],
        "B": documents["B"]["statuses"]["FAMILY_B_RESEARCH_STATUS"],
        "C": documents["C"]["final_statuses"]["FAMILY_C_RESEARCH_STATUS"],
        "D": documents["D"]["final_statuses"]["FAMILY_D_RESEARCH_STATUS"],
        "E": documents["E"]["final_statuses"]["FAMILY_E_RESEARCH_STATUS"],
        "F": documents["F"]["statuses"]["FAMILY_F_RESEARCH_STATUS"],
        "G": documents["G"]["statuses"]["FAMILY_G_RESEARCH_STATUS"],
    }
    checks = {
        "all_input_file_hashes_exact": observed_hashes == INPUT_FILE_HASHES,
        "all_family_closure_hashes_exact": _closure_hashes(documents) == FAMILY_CLOSURE_HASHES,
        "all_family_statuses_exact": statuses == FAMILY_FINAL_STATUSES,
        "strategy_v1_weak": strategy_v1["classifications"]["STRATEGY_V1_RESEARCH_RESULT"]
        == "WEAK_AND_REQUIRES_RESEARCH",
        "cap4_validation_failed": cap4["classifications"]
        == {
            "RR_CAP4_HOLDOUT_VALIDATION_RESULT": "FAILED",
            "RR_CAP4_GENERALIZATION_RESULT": "DOES_NOT_GENERALIZE",
            "RR_CAP4_SCORE_CHANGE_READINESS": "REJECTED",
            "PROMOTED_TO_STRATEGY_V1": False,
        },
        "family_a_reference_exact": mom_a_002["experiment_id"] == "MOM-A-002"
        and mom_a_002["parameter_hash"]
        == "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8",
        "family_a_500k_reference_exact": a2_002["experiment_id"] == "A2-002"
        and a2_002["parameters"]["starting_capital_inr"] == "500000"
        and a2_002["preregistration_hash"]
        == "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897",
        "family_a_result_exact": a2_result["development_result_hash"]
        == "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27"
        and a2_result["performance"]["net_ending_equity"] == "955331.6799"
        and a2_result["validation_accessed"] is False,
        "family_g_reproduced_family_a": documents["G"]["evidence"]["control"]
        ["net_ending_equity_rupees"]
        == "955331.6799"
        and documents["G"]["evidence"]["family_a_preservation"]
        ["family_a_evidence_upgraded_to_validated"]
        is False,
        "family_d_continuity_block_exact": d_manifest["data_finding"]
        == {
            "complete_exact_prior20_continuity": 3752,
            "coverage_classification": "INSUFFICIENT",
            "coverage_pct": "77.826177",
            "incomplete": 1069,
            "target_sessions": 4821,
        },
        "family_f_source_gate_exact": documents["F"]["source_evidence"]
        ["positive_evidence"]["trusted_publication_timestamp_quality_percent"]
        == 95.24
        and documents["F"]["license_gate"]["status"]
        == "BLOCKING_HISTORICAL_ACQUISITION",
        "family_g_hash_exact": documents["G"]["family_g_closure_hash"]
        == FAMILY_CLOSURE_HASHES["G"],
        "family_f_hash_exact": documents["F"]["family_f_closure_hash"]
        == FAMILY_CLOSURE_HASHES["F"],
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise CrossFamilySynthesisInputMismatch(f"Synthesis checks failed: {failed}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "git": verify_git_milestone(root),
        "source_file_hashes": observed_hashes,
        "source_snapshot_hash": canonical_hash(observed_hashes),
        "family_closure_hashes": FAMILY_CLOSURE_HASHES,
        "family_final_statuses": statuses,
    }


def family_matrix_rows() -> list[dict[str, Any]]:
    return [
        {
            "entity": "STRATEGY_V1",
            "entity_type": "HISTORICAL_BASELINE",
            "architecture": "SHORT_HORIZON_BREAKOUT_SCORING",
            "final_status": "WEAK_AND_REQUIRES_RESEARCH",
            "primary_classification": "NEGATIVE_DEVELOPMENT_EVIDENCE",
            "performance_status": "HISTORICAL_DEVELOPMENT_CONTEXT",
            "validation_status": "NOT_A_CANDIDATE",
            "decision": "DO_NOT_SELECT",
            "evidence_summary": "Broad diagnostics left Strategy V1 weak and requiring research.",
        },
        {
            "entity": "CAP4",
            "entity_type": "HISTORICAL_VALIDATION_CONTROL",
            "architecture": "RR_SCORE_CAP_4",
            "final_status": "DOES_NOT_GENERALIZE_REJECTED",
            "primary_classification": "REJECTED_VALIDATION",
            "performance_status": "DEVELOPMENT_PROMISING_VALIDATION_FAILED",
            "validation_status": "CONSUMED_FAILED",
            "decision": "DO_NOT_SELECT",
            "evidence_summary": "The failed one-shot holdout shows why development evidence is insufficient.",
        },
        {
            "entity": "FAMILY_A",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "MEDIUM_TERM_CROSS_SECTIONAL_MOMENTUM",
            "final_status": FAMILY_FINAL_STATUSES["A"],
            "primary_classification": FAMILY_CLASSIFICATIONS["A"],
            "performance_status": "PROMISING_DEVELOPMENT_EVIDENCE_NOT_VALIDATED",
            "validation_status": "NOT_ACCESSED",
            "decision": PROVISIONAL_CANDIDATE_STATUS,
            "evidence_summary": "MOM-A-002/A2-002 was positive after costs, temporally positive in each development year, implementation-tested at INR 500k, and independently reproduced by Family G.",
        },
        {
            "entity": "FAMILY_B",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "RELATIVE_PLUS_ABSOLUTE_MOMENTUM",
            "final_status": FAMILY_FINAL_STATUSES["B"],
            "primary_classification": FAMILY_CLASSIFICATIONS["B"],
            "performance_status": "NO_CLEAR_INCREMENTAL_EDGE_OVER_RELATIVE_MOMENTUM",
            "validation_status": "NOT_ACCESSED",
            "decision": "DO_NOT_ADVANCE",
            "evidence_summary": "B001 was redundant; B002's apparent strength was primarily a history-availability artifact and became weak/sparse after remediation.",
        },
        {
            "entity": "FAMILY_C",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "BREAKOUT_CONTINUATION",
            "final_status": FAMILY_FINAL_STATUSES["C"],
            "primary_classification": FAMILY_CLASSIFICATIONS["C"],
            "performance_status": "POSITIVE_COMPRESSION_SIGNAL_NOT_PORTFOLIO_READY",
            "validation_status": "NOT_ACCESSED",
            "decision": "PRESERVE_SIGNAL_EVIDENCE_ONLY",
            "evidence_summary": "Compression <=8% improved event quality, while the control, volume treatment, and compression-priority portfolio ranking did not justify advancement.",
        },
        {
            "entity": "FAMILY_D",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "OPENING_RANGE_STOCKS_IN_PLAY",
            "final_status": FAMILY_FINAL_STATUSES["D"],
            "primary_classification": FAMILY_CLASSIFICATIONS["D"],
            "performance_status": "NOT_EVALUATED",
            "validation_status": "NOT_ACCESSED",
            "decision": "DATA_BLOCKED_NOT_STRATEGY_FAILED",
            "evidence_summary": "Exact prior-20 continuity reached 77.826177%, below the frozen >=95% threshold.",
        },
        {
            "entity": "FAMILY_E",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "PULLBACK_RECLAIM_CONTINUATION",
            "final_status": FAMILY_FINAL_STATUSES["E"],
            "primary_classification": FAMILY_CLASSIFICATIONS["E"],
            "performance_status": "PULLBACK_RECLAIM_V1_NOT_SUPPORTED",
            "validation_status": "NOT_ACCESSED",
            "decision": "DO_NOT_ADVANCE",
            "evidence_summary": "The control was weak/nonviable and the SMA50 structure treatment failed while removing a descriptively better cohort.",
        },
        {
            "entity": "FAMILY_F",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "CATALYST_MOMENTUM",
            "final_status": FAMILY_FINAL_STATUSES["F"],
            "primary_classification": FAMILY_CLASSIFICATIONS["F"],
            "performance_status": "NOT_EVALUATED",
            "validation_status": "NOT_ACCESSED",
            "decision": "SOURCE_BLOCKED_NOT_STRATEGY_FAILED",
            "evidence_summary": "Timestamp and linkage feasibility was demonstrated, but historical acquisition authorization remains unresolved.",
        },
        {
            "entity": "FAMILY_G",
            "entity_type": "DISCOVERY_FAMILY",
            "architecture": "QUARTERLY_REGIME_VOLATILITY_PARTICIPATION",
            "final_status": FAMILY_FINAL_STATUSES["G"],
            "primary_classification": FAMILY_CLASSIFICATIONS["G"],
            "performance_status": "SMA200_GATE_NOT_SUPPORTED_FOR_ADVANCEMENT",
            "validation_status": "NOT_ACCESSED",
            "decision": "DO_NOT_ADVANCE_GATE",
            "evidence_summary": "The exact SMA200 all-in/all-cash gate materially reduced return, worsened drawdown, and skipped two profitable control quarters.",
        },
    ]


def evidence_dimension_rows() -> list[dict[str, str]]:
    dimensions = (
        "A_EXECUTABLE_DEVELOPMENT_PROFITABILITY",
        "B_COST_ROBUSTNESS",
        "C_DRAWDOWN_ACCEPTABILITY",
        "D_TEMPORAL_CONSISTENCY",
        "E_SAMPLE_ADEQUACY",
        "F_CAPITAL_CAPACITY_REALISM",
        "G_DATA_INTEGRITY",
        "H_ATTRIBUTION_CLARITY",
        "I_REPRODUCTION_EVIDENCE",
        "J_PARAMETER_SEARCH_RISK",
        "K_IMPLEMENTATION_SIMPLICITY",
        "L_VALIDATION_READINESS",
    )
    ratings = {
        "A": ("STRONG", "MODERATE", "MODERATE", "MODERATE", "WEAK", "STRONG", "STRONG", "STRONG", "STRONG", "MODERATE", "STRONG", "STRONG"),
        "B": ("WEAK", "MODERATE", "MODERATE", "WEAK", "WEAK", "STRONG", "STRONG", "STRONG", "MODERATE", "MODERATE", "STRONG", "WEAK"),
        "C": ("WEAK", "WEAK", "WEAK", "MODERATE", "STRONG", "WEAK", "STRONG", "STRONG", "NOT_AVAILABLE", "MODERATE", "MODERATE", "WEAK"),
        "D": ("NOT_AVAILABLE", "NOT_AVAILABLE", "NOT_AVAILABLE", "NOT_AVAILABLE", "BLOCKED", "BLOCKED", "BLOCKED", "NOT_AVAILABLE", "NOT_AVAILABLE", "MODERATE", "MODERATE", "BLOCKED"),
        "E": ("WEAK", "MODERATE", "WEAK", "WEAK", "STRONG", "WEAK", "STRONG", "STRONG", "NOT_AVAILABLE", "MODERATE", "MODERATE", "WEAK"),
        "F": ("NOT_AVAILABLE", "NOT_AVAILABLE", "NOT_AVAILABLE", "NOT_AVAILABLE", "BLOCKED", "NOT_AVAILABLE", "BLOCKED", "NOT_AVAILABLE", "STRONG", "NOT_AVAILABLE", "NOT_AVAILABLE", "BLOCKED"),
        "G": ("WEAK", "STRONG", "WEAK", "WEAK", "WEAK", "STRONG", "STRONG", "STRONG", "STRONG", "STRONG", "STRONG", "WEAK"),
    }
    notes = {
        "A": "Positive after frozen costs; three years and ten completed rebalance periods limit inference.",
        "B": "Clean attribution was strong, but incremental filter evidence was redundant or sparse.",
        "C": "Large event sample supported compression discrimination, not an executable portfolio candidate.",
        "D": "Performance dimensions are unavailable because the frozen data-continuity gate failed.",
        "E": "Adequate event volume did not translate to positive executable evidence; capacity pressure was material.",
        "F": "The bounded source pilot reproduced well, but authorization blocks historical strategy evaluation.",
        "G": "A simple, well-attributed test reproduced the control but the treatment failed key return/drawdown objectives.",
    }
    return [
        {"family": family, "dimension": dimension, "rating": rating, "note": notes[family]}
        for family, family_ratings in ratings.items()
        for dimension, rating in zip(dimensions, family_ratings, strict=True)
    ]


def positive_evidence_rows() -> list[dict[str, str]]:
    return [
        {"evidence_id": "CROSS-POSITIVE-A-MOMENTUM-001", "source_family": "A", "level": "STRATEGY_LEVEL", "status": "DEVELOPMENT_ONLY_NOT_VALIDATED", "finding": "Frozen medium-term cross-sectional momentum was executable and positive after costs in DEVELOPMENT.", "reuse_rule": "Advance only through the frozen provisional candidate and a separately authorized validation design."},
        {"evidence_id": "CROSS-POSITIVE-A-QUARTERLY-001", "source_family": "A", "level": "STRATEGY_LEVEL", "status": "DEVELOPMENT_ONLY_NOT_VALIDATED", "finding": "Quarterly rebalancing was operationally viable with 8 of 10 completed net rebalance periods positive.", "reuse_rule": "This is portfolio-period evidence, not a trade win-rate claim."},
        {"evidence_id": "CROSS-POSITIVE-A-CAPITAL-001", "source_family": "A", "level": "STRATEGY_LEVEL", "status": "SUPPORTED_IMPLEMENTATION_EVIDENCE", "finding": "The INR 500k whole-share implementation materially reduced the distortion observed at INR 100k.", "reuse_rule": "Treat INR 500k as a research implementation reference, not an alpha parameter or live recommendation."},
        {"evidence_id": "CROSS-POSITIVE-G-A-REPRODUCTION-001", "source_family": "G", "level": "STRATEGY_LEVEL", "status": "INDEPENDENT_DEVELOPMENT_REPRODUCTION", "finding": "CONTROL-G-000 exactly reproduced the frozen Family A INR 500k control metrics.", "reuse_rule": "Reproduction increases lineage confidence but does not upgrade evidence to validation."},
        {"evidence_id": "EDGE-EVIDENCE-C-COMPRESSION-001", "source_family": "C", "level": "SIGNAL_LEVEL", "status": "RESEARCH_EVIDENCE_NOT_VALIDATED", "finding": "Pre-breakout compression <=8% improved event-level signal quality in DEVELOPMENT.", "reuse_rule": "Not portfolio-ready; reuse requires a genuinely new independently preregistered architecture."},
        {"evidence_id": "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001", "source_family": "F", "level": "DATA_INFRASTRUCTURE_LEVEL", "status": "TECHNICALLY_SUITABLE_PENDING_AUTHORIZATION", "finding": "The bounded NSE corporate-announcement pilot achieved 95.24% trusted timestamps and 100% linkage, identity, and reproducibility.", "reuse_rule": "No historical collection until an authorization gate is satisfied."},
    ]


def negative_evidence_rows() -> list[dict[str, str]]:
    return [
        {"evidence_id": "CAP4-VALIDATION-FAILURE", "source": "CAP4", "scope": "VALIDATION", "finding": "Promising DEVELOPMENT evidence failed formal validation.", "result": "DOES_NOT_GENERALIZE_REJECTED", "prohibited_inference": "DEVELOPMENT_STRENGTH_IS_SUFFICIENT_FOR_PROMOTION"},
        {"evidence_id": "EDGE-NEGATIVE-B-POSITIVE-RETURN-001", "source": "FAMILY_B", "scope": "FROZEN_B001", "finding": "The 6M positive-return filter removed zero of 302 top-decile candidates.", "result": "REDUNDANT", "prohibited_inference": "ALL_ABSOLUTE_MOMENTUM_IS_USELESS"},
        {"evidence_id": "EDGE-NEGATIVE-B-SMA200-001", "source": "FAMILY_B", "scope": "FROZEN_B002", "finding": "Apparent SMA200 strength was primarily a history-availability artifact; clean evidence had one genuine exclusion among 302 candidates.", "result": "CONFOUNDED_THEN_WEAK_SPARSE", "prohibited_inference": "ALL_TREND_FILTERS_FAIL"},
        {"evidence_id": "EDGE-NEGATIVE-C-VOLUME-001", "source": "FAMILY_C", "scope": "FROZEN_BRK_C_002", "finding": "The tested 1.5x breakout-day volume filter did not improve the strategy.", "result": "FAILED", "prohibited_inference": "ALL_VOLUME_FILTERS_FAIL"},
        {"evidence_id": "IMPLEMENTATION-NEGATIVE-C-COMPRESSION-RANK-001", "source": "FAMILY_C", "scope": "FROZEN_C1_IMP_001", "finding": "Tightest-compression-first capacity ranking failed to improve implementation quality.", "result": "FAILED", "prohibited_inference": "THE_COMPRESSION_SIGNAL_HAS_NO_VALUE"},
        {"evidence_id": "EDGE-NEGATIVE-E-PULLBACK-RECLAIM-001", "source": "FAMILY_E", "scope": "FROZEN_CONTROL_E_000", "finding": "The tested pullback/reclaim control did not produce positive portfolio-level DEVELOPMENT edge after costs.", "result": "WEAK_NONVIABLE", "prohibited_inference": "ALL_PULLBACK_STRATEGIES_FAIL"},
        {"evidence_id": "EDGE-NEGATIVE-E-SMA50-STRUCTURE-001", "source": "FAMILY_E", "scope": "FROZEN_PBR_E_001", "finding": "The SMA50 structure filter removed a descriptively better event cohort and worsened the treatment.", "result": "FAILED_NEGATIVE_ATTRIBUTION", "prohibited_inference": "ALL_SMA50_USE_FAILS"},
        {"evidence_id": "EDGE-NEGATIVE-G-SMA200-GATE-001", "source": "FAMILY_G", "scope": "FROZEN_REGIME_G_001", "finding": "The quarterly NIFTY 500 close>SMA200 all-in/all-cash gate reduced returns, worsened drawdown, and skipped two profitable control quarters.", "result": "PARTIALLY_SUPPORTED_NOT_ADVANCED", "prohibited_inference": "ALL_REGIME_FILTERS_OR_SMA200_METHODS_FAIL"},
    ]


def blocked_research_rows() -> list[dict[str, str]]:
    return [
        {"family": "D", "classification": "DATA_BLOCKED", "blocker": "CONTINUOUS_INTRADAY_DATA", "evidence": "Exact prior-20 continuity was 77.826177% versus the frozen >=95% requirement; 1,069 of 4,821 targets remained incomplete.", "strategy_result": "NOT_PERFORMANCE_EVALUATED", "resume_condition": "An approved source must satisfy the unchanged continuity and quality gates.", "failed_strategy": "False"},
        {"family": "F", "classification": "SOURCE_BLOCKED", "blocker": "CATALYST_SOURCE_AUTHORIZATION", "evidence": "The NSE corporate-announcement pilot was technically suitable, but systematic historical acquisition authorization remains unresolved.", "strategy_result": "NOT_PERFORMANCE_EVALUATED", "resume_condition": "Obtain authorized NSE delivery, an equivalent licensed feed, or an official alternative passing identical gates.", "failed_strategy": "False"},
    ]


def family_a_candidate_gate_rows() -> list[dict[str, Any]]:
    evidence = (
        "A2-002 ended at INR 955,331.6799 from INR 500,000 after costs (+91.06633598%).",
        "The frozen INDIA_EQUITY_COST_MODEL_V1/COST-SCENARIO-002 is included; total modeled costs were INR 17,629.90.",
        "Frozen Family A inputs are point-in-time and Family G independently reproduced the result; no known history-availability artifact explains it.",
        "At INR 500k there were no unaffordable names, average invested capital was 97.351%, and tracking distortion was materially lower than at INR 100k.",
        "All three DEVELOPMENT calendar years were positive and 8/10 completed net rebalance periods were positive; the short window remains a validation risk.",
        "No unresolved methodology or data blocker prevents designing a validation; numeric-label caveats remain disclosed and raw metrics govern.",
        "MOM-A-002 and A2-002 parameters, execution, and costs are frozen and hash-linked.",
        "Family A closure, preregistration, result, ledgers, and independent Family G reproduction provide sufficient lineage.",
        "The exact candidate has not undergone or failed formal validation.",
        "No candidate-specific validation outcomes drove tuning; aggregate later-period project knowledge is disclosed separately.",
    )
    names = (
        "POSITIVE_EXECUTABLE_DEVELOPMENT_EVIDENCE",
        "COSTS_INCLUDED",
        "NO_KNOWN_DATA_ARTIFACT_EXPLANATION",
        "IMPLEMENTATION_DISTORTION_CONTROLLED",
        "REASONABLY_STABLE_TEMPORAL_EVIDENCE",
        "NO_UNRESOLVED_METHODOLOGY_BLOCKER",
        "ARCHITECTURE_FROZEN",
        "SUFFICIENT_ARTIFACT_LINEAGE",
        "NO_PRIOR_VALIDATION_FAILURE_FOR_EXACT_CANDIDATE",
        "NO_OUTCOME_DRIVEN_VALIDATION_TUNING",
    )
    caveats = (
        "DEVELOPMENT_ONLY",
        "COST_SENSITIVITY_REMAINS_A_VALIDATION_RISK",
        "REPRODUCTION_IS_DEVELOPMENT_NOT_VALIDATION",
        "INR_500K_IS_A_RESEARCH_REFERENCE_NOT_A_LIVE_RECOMMENDATION",
        "ONLY_THREE_YEARS_AND_TEN_COMPLETED_PERIODS",
        "COMMAND_04_LABELS_WERE_DESCRIPTIVE_NOT_PREREGISTERED",
        "ANY_CHANGE_REQUIRES_A_NEW_VERSION",
        "LINEAGE_DOES_NOT_PROVE_GENERALIZATION",
        "VALIDATION_REMAINS_SEALED",
        "NOT_PHILOSOPHICALLY_PRISTINE_DUE_TO_AGGREGATE_LATER_PERIOD_KNOWLEDGE",
    )
    return [
        {"candidate": "MOM-A-002+A2-002", "gate_number": index, "gate": name, "result": "PASS", "evidence": item, "caveat": caveat}
        for index, (name, item, caveat) in enumerate(zip(names, evidence, caveats, strict=True), start=1)
    ]


def alternative_candidate_rows() -> list[dict[str, str]]:
    return [
        {"family": "B", "result": "FAIL", "first_failed_gate": "1", "reason": "No distinct positive executable edge over the Family A reference."},
        {"family": "C", "result": "FAIL", "first_failed_gate": "1", "reason": "Positive event-level compression evidence did not become a robust executable portfolio."},
        {"family": "D", "result": "FAIL", "first_failed_gate": "1", "reason": "Performance was not evaluated because the data gate failed."},
        {"family": "E", "result": "FAIL", "first_failed_gate": "1", "reason": "Control and treatment evidence were unfavorable."},
        {"family": "F", "result": "FAIL", "first_failed_gate": "1", "reason": "Performance was not evaluated because source authorization is unresolved."},
        {"family": "G", "result": "FAIL", "first_failed_gate": "1", "reason": "The regime treatment did not preserve return or improve drawdown."},
    ]


def validation_risk_rows() -> list[dict[str, str]]:
    return [
        {"risk_id": "VAL-RISK-A-001", "risk": "ONLY_THREE_DEVELOPMENT_YEARS", "severity": "HIGH", "implication": "A short window can overrepresent favorable conditions.", "design_response": "Use the untouched governed window once, without retuning."},
        {"risk_id": "VAL-RISK-A-002", "risk": "REGIME_CONCENTRATION", "severity": "HIGH", "implication": "2022-2024 may not span enough market states.", "design_response": "Predeclare regime reporting without turning it into a gate or tuning dimension."},
        {"risk_id": "VAL-RISK-A-003", "risk": "LIMITED_QUARTERLY_OBSERVATIONS", "severity": "HIGH", "implication": "Only ten completed rebalance periods support the 80% period-success observation.", "design_response": "Treat period counts as limited and predeclare exact inference boundaries."},
        {"risk_id": "VAL-RISK-A-004", "risk": "SELECTION_BREADTH", "severity": "MODERATE", "implication": "Top-decile breadth and constituent availability may shift.", "design_response": "Preserve point-in-time membership and frozen minimum portfolio rules."},
        {"risk_id": "VAL-RISK-A-005", "risk": "TURNOVER_AND_COST_SENSITIVITY", "severity": "MODERATE", "implication": "Costs consumed 3.52598 percentage points of initial capital in DEVELOPMENT.", "design_response": "Freeze identical cost and turnover accounting before validation."},
        {"risk_id": "VAL-RISK-A-006", "risk": "IMPLEMENTATION_AND_CAPITAL_ASSUMPTIONS", "severity": "MODERATE", "implication": "INR 500k reduced but did not eliminate idealized-tracking differences.", "design_response": "Keep whole shares, INR 500k, cash, and next-open semantics unchanged."},
        {"risk_id": "VAL-RISK-A-007", "risk": "PRIOR_AGGREGATE_LATER_PERIOD_KNOWLEDGE", "severity": "HIGH", "implication": CONTAMINATION_DISCLOSURE, "design_response": "Separate formal sealed governance from any claim of pristine unseen data."},
    ]


def provisional_candidate_document() -> dict[str, Any]:
    body = {
        "candidate_id": PROVISIONAL_CANDIDATE_ID,
        "status": PROVISIONAL_CANDIDATE_STATUS,
        "candidate_selection_classification": CANDIDATE_SELECTION_CLASSIFICATION,
        "strategy_v2": False,
        "validation_run_authorized": False,
        "architecture_reference": "MOM-A-002",
        "implementation_reference": "A2-002",
        "reference_capital_inr": "500000",
        "frozen_references": {
            "mom_a_002": {
                "path": "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json",
                "parameter_hash": "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8",
            },
            "a2_002_preregistration": {
                "path": "data/research/strategy_families/family_a/v1/phase2/registry/a2_002_preregistration_v1.json",
                "preregistration_hash": "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897",
            },
            "a2_002_result": {
                "path": "data/research/strategy_families/family_a/v1/phase2/development_evaluation/a2_002/development_result_v1.json",
                "result_hash": "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27",
            },
        },
        "preserved_architecture": [
            "POINT_IN_TIME_NIFTY_500",
            "FROZEN_PRICE_GATE",
            "FROZEN_LIQUIDITY_GATE",
            "SIX_MONTH_MOMENTUM_RANKING",
            "TOP_DECILE_SELECTION",
            "QUARTERLY_REBALANCE",
            "EQUAL_WEIGHT",
            "INR_500K_REFERENCE_CAPITAL",
            "WHOLE_SHARES",
            "FROZEN_COST_SEMANTICS",
            "FROZEN_NEXT_OPEN_EXECUTION_SEMANTICS",
        ],
        "excluded_overlays": [
            "NO_FAMILY_B_FILTER",
            "NO_FAMILY_C_COMPRESSION_OVERLAY",
            "NO_FAMILY_G_REGIME_GATE",
            "NO_CROSS_FAMILY_HYBRID",
        ],
        "selection_basis": "ONLY_EXISTING_ARCHITECTURE_PASSING_ALL_TEN_VALIDATION_DESIGN_GATES",
        "interpretation": "A provisional design candidate, not a proven strategy, validation result, production approval, or Strategy V2.",
    }
    return {**body, "provisional_candidate_hash": canonical_hash(body)}


def candidate_selection_document() -> dict[str, Any]:
    gates = family_a_candidate_gate_rows()
    alternatives = alternative_candidate_rows()
    return {
        "version": "CROSS_FAMILY_CANDIDATE_SELECTION_V1",
        "family_a_candidate": "MOM-A-002+A2-002",
        "family_a_gate_results": gates,
        "all_ten_gates_pass": all(row["result"] == "PASS" for row in gates),
        "FAMILY_A_VALIDATION_CANDIDACY": FAMILY_A_VALIDATION_CANDIDACY,
        "alternative_candidate_results": alternatives,
        "ALTERNATIVE_VALIDATION_CANDIDATE": "NONE",
        "candidate_selection_classification": CANDIDATE_SELECTION_CLASSIFICATION,
        "proven_strategy": False,
        "provisional_candidate": provisional_candidate_document(),
    }


def validation_readiness_document() -> dict[str, Any]:
    return {
        "version": "CROSS_FAMILY_VALIDATION_READINESS_V1",
        "primary_question": "After the controlled A-G discovery programme, is there sufficient evidence to nominate one existing strategy architecture for formal validation design?",
        "primary_question_result": PRIMARY_QUESTION_RESULT,
        "VALIDATION_DESIGN_READINESS": VALIDATION_DESIGN_READINESS,
        "NEXT_PLANNED_PHASE": NEXT_PLANNED_PHASE,
        "FAMILY_H_STATUS": FAMILY_H_STATUS,
        "family_h_reason": "No additional family is justified before the synthesis decision is carried into a governed Family A validation design.",
        "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        "validation_accessed": False,
        "family_performance_rerun": False,
        "new_strategy_created": False,
        "hybrid_strategy_created": False,
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "win_rate_assessment": {
            "original_aspiration": "60_TO_65_PERCENT",
            "selection_rule": "WIN_RATE_ALONE_MUST_NOT_DETERMINE_CANDIDATE_SELECTION",
            "family_a_available_metric": "8_OF_10_COMPLETED_NET_PORTFOLIO_REBALANCE_PERIODS_POSITIVE_80_PERCENT",
            "terminology": "PORTFOLIO_REBALANCE_PERIOD_NOT_TRADE_WIN_RATE",
            "trade_level_win_rate_claimed": False,
        },
        "risks": validation_risk_rows(),
    }


def _component_paths(root: Path) -> dict[str, Path]:
    base = output_root(root)
    return {
        "family_matrix": base / "family_matrix/family_matrix_v1.json",
        "positive_evidence": base / "positive_evidence/positive_evidence_registry_v1.json",
        "negative_evidence": base / "negative_evidence/negative_evidence_registry_v1.json",
        "blocked_research": base / "blocked_research/blocked_research_registry_v1.json",
        "candidate_selection": base / "candidate_selection/candidate_selection_gate_v1.json",
        "validation_readiness": base / "validation_readiness/validation_readiness_v1.json",
    }


def _write_immutable_manifest(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists():
        raise CrossFamilySynthesisImmutabilityError(
            f"Refusing to overwrite immutable cross-family synthesis manifest: {path}"
        )
    write_json(path, document)


def _assert_roadmap(root: Path) -> None:
    text = (Path(root) / "docs/strategy-family-research-roadmap-v2.md").read_text(
        encoding="utf-8"
    )
    synthesis_state = any(
        item in text
        for item in (
            "CROSS_FAMILY_EVIDENCE_SYNTHESIS_STATUS = ACTIVE",
            "CROSS_FAMILY_EVIDENCE_SYNTHESIS_STATUS = COMPLETE",
        )
    )
    validation_state = any(
        item in text
        for item in (
            "VALIDATION_DESIGN_STATUS = NEXT_PLANNED",
            "VALIDATION_DESIGN_STATUS = ACTIVE",
        )
    )
    if not (
        synthesis_state
        and validation_state
        and "FAMILY_H_STATUS = NOT_PLANNED" in text
    ):
        raise CrossFamilySynthesisInputMismatch("Roadmap is missing synthesis lifecycle state")


def synthesis_component_hash_matches(relative: str, expected: str, observed: str) -> bool:
    if relative == "docs/strategy-family-research-roadmap-v2.md":
        return (
            expected == SYNTHESIS_ROADMAP_COMPONENT_HASH
            and observed in AUTHORIZED_ROADMAP_SUCCESSOR_HASHES
        )
    return observed == expected


def build_cross_family_evidence_synthesis(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _assert_roadmap(root)
    input_verification = verify_synthesis_inputs(root)
    timestamp = utc_now()
    reports = root / "data/reports"
    paths = _component_paths(root)

    family_matrix = {
        "version": "CROSS_FAMILY_FAMILY_MATRIX_V1",
        "classification_buckets": list(CLASSIFICATION_BUCKETS),
        "rows": family_matrix_rows(),
    }
    positive = {
        "version": "CROSS_FAMILY_POSITIVE_EVIDENCE_REGISTRY_V1",
        "rows": positive_evidence_rows(),
    }
    negative = {
        "version": "CROSS_FAMILY_NEGATIVE_EVIDENCE_REGISTRY_V1",
        "rows": negative_evidence_rows(),
    }
    blocked = {
        "version": "CROSS_FAMILY_BLOCKED_RESEARCH_REGISTRY_V1",
        "rows": blocked_research_rows(),
        "blocked_is_not_failed": True,
    }
    candidate = candidate_selection_document()
    readiness = validation_readiness_document()
    for key, document in (
        ("family_matrix", family_matrix),
        ("positive_evidence", positive),
        ("negative_evidence", negative),
        ("blocked_research", blocked),
        ("candidate_selection", candidate),
        ("validation_readiness", readiness),
    ):
        write_json(paths[key], document)

    matrix_rows = family_matrix["rows"]
    dimension_rows = evidence_dimension_rows()
    write_csv(reports / REPORT_NAMES[1], matrix_rows)
    write_csv(reports / REPORT_NAMES[2], dimension_rows)
    write_csv(reports / REPORT_NAMES[3], positive["rows"])
    write_csv(reports / REPORT_NAMES[4], negative["rows"])
    write_csv(reports / REPORT_NAMES[5], blocked["rows"])
    candidate_csv_rows = [
        {**row, "row_type": "FAMILY_A_GATE", "family": "A", "reason": ""}
        for row in candidate["family_a_gate_results"]
    ] + [
        {
            "candidate": f"FAMILY_{row['family']}",
            "gate_number": row["first_failed_gate"],
            "gate": "ALTERNATIVE_CANDIDATE_SUMMARY",
            "result": row["result"],
            "evidence": row["reason"],
            "caveat": "NO_ALTERNATIVE_SELECTED",
            "row_type": "ALTERNATIVE_SUMMARY",
            "family": row["family"],
            "reason": row["reason"],
        }
        for row in candidate["alternative_candidate_results"]
    ]
    write_csv(reports / REPORT_NAMES[6], candidate_csv_rows)
    write_csv(reports / REPORT_NAMES[7], readiness["risks"])
    write_csv(
        reports / REPORT_NAMES[8],
        [
            {
                "primary_question_result": PRIMARY_QUESTION_RESULT,
                "family_a_validation_candidacy": FAMILY_A_VALIDATION_CANDIDACY,
                "alternative_validation_candidate": "NONE",
                "candidate_selection_classification": CANDIDATE_SELECTION_CLASSIFICATION,
                "provisional_candidate_id": PROVISIONAL_CANDIDATE_ID,
                "provisional_candidate_status": PROVISIONAL_CANDIDATE_STATUS,
                "validation_design_readiness": VALIDATION_DESIGN_READINESS,
                "next_planned_phase": NEXT_PLANNED_PHASE,
                "family_h_status": FAMILY_H_STATUS,
                "strategy_v2_status": STRATEGY_V2_STATUS,
            }
        ],
    )

    component_files = list(paths.values()) + [
        reports / name for name in REPORT_NAMES[1:]
    ] + [
        root / "docs/cross-family-evidence-synthesis-a-to-g-v1.md",
        root / "docs/strategy-family-research-roadmap-v2.md",
    ]
    component_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in component_files
    }
    lessons = {
        "simplicity": "Across tested A-G definitions, evidence provisionally favors one simple standalone architecture over adding the tested overlays; this is not a universal proof against multi-factor designs.",
        "filter_additions": "Family B absolute-momentum filters added no clear distinct edge; Family G's exact SMA200 gate damaged return/drawdown; Family C volume and compression-priority filters and Family E's SMA50 structure filter did not improve executable evidence.",
        "implementation": "Capital scale and whole shares can distort portfolios; capacity, costs, point-in-time history, continuous intraday data, and source licensing are first-class research constraints.",
    }
    safety = {
        "network_accessed": False,
        "credentials_written": False,
        "performance_rerun": False,
        "validation_accessed": False,
        "validation_rows_loaded": 0,
        "new_strategy_created": False,
        "hybrid_strategy_created": False,
        "family_h_created": False,
        "strategy_v2_created": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "external_writes": 0,
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "checkpoint": input_verification["git"],
        "input_verification": input_verification,
        "discovery_cycle_status": DISCOVERY_CYCLE_STATUS,
        "family_final_statuses": FAMILY_FINAL_STATUSES,
        "family_closure_hashes": FAMILY_CLOSURE_HASHES,
        "classifications": {
            "STRATEGY_V1": "NEGATIVE_DEVELOPMENT_EVIDENCE",
            "CAP4": "REJECTED_VALIDATION",
            **{f"FAMILY_{key}": value for key, value in FAMILY_CLASSIFICATIONS.items()},
        },
        "candidate_selection": {
            "FAMILY_A_VALIDATION_CANDIDACY": FAMILY_A_VALIDATION_CANDIDACY,
            "alternative_validation_candidate": "NONE",
            "classification": CANDIDATE_SELECTION_CLASSIFICATION,
            "provisional_candidate_id": PROVISIONAL_CANDIDATE_ID,
            "provisional_candidate_hash": candidate["provisional_candidate"]
            ["provisional_candidate_hash"],
        },
        "readiness": {
            "primary_question_result": PRIMARY_QUESTION_RESULT,
            "VALIDATION_DESIGN_READINESS": VALIDATION_DESIGN_READINESS,
            "NEXT_PLANNED_PHASE": NEXT_PLANNED_PHASE,
            "FAMILY_H_STATUS": FAMILY_H_STATUS,
            "STRATEGY_V2_STATUS": STRATEGY_V2_STATUS,
        },
        "lessons": lessons,
        "component_hashes": component_hashes,
        "governance": {
            "validation_design_only": True,
            "candidate_is_proven_strategy": False,
            "cross_family_combination_created": False,
            "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        },
        "regressions": {
            "Strategy_V1": "PRESERVED",
            "CAP4": "PRESERVED",
            **{f"Family_{letter}": "PRESERVED" for letter in "ABCDEFG"},
            "all_closure_hashes_unchanged": True,
        },
        "safety": safety,
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    manifest = {
        **manifest_body,
        "cross_family_synthesis_hash": canonical_hash(manifest_body),
    }
    manifest_path = output_root(root) / "manifests/cross_family_evidence_synthesis_manifest_v1.json"
    _write_immutable_manifest(manifest_path, manifest)

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "primary_question_result": PRIMARY_QUESTION_RESULT,
        "input_verification": input_verification,
        "cycle": {"A_TO_G_DISCOVERY": DISCOVERY_CYCLE_STATUS, "cross_family_synthesis": "ACTIVE"},
        "family_matrix": matrix_rows,
        "evidence_dimensions": dimension_rows,
        "positive_evidence": positive["rows"],
        "negative_evidence": negative["rows"],
        "blocked_research": blocked["rows"],
        "candidate_selection": candidate,
        "validation_readiness": readiness,
        "research_lessons": lessons,
        "regressions": manifest["regressions"],
        "safety": safety,
        "cross_family_synthesis_hash": manifest["cross_family_synthesis_hash"],
        "manifest": manifest_path.relative_to(root).as_posix(),
        "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        "documentation": "docs/cross-family-evidence-synthesis-a-to-g-v1.md",
        "roadmap": "docs/strategy-family-research-roadmap-v2.md",
        "known_limitations": [
            "Family A evidence is DEVELOPMENT-only over 2022-2024 with ten completed rebalance periods.",
            "The INR 500k reference reduces but does not eliminate implementation assumptions or tracking differences.",
            "Family C evidence is signal-level, while Families D and F remain unevaluated because of data/source blocks.",
            "Family A validation can be formally governed but cannot be described as philosophically pristine unseen data.",
            "A passing design gate nominates a candidate; it does not establish generalization or production readiness.",
        ],
        "recommended_next_action": "Design—but do not yet run—the one-shot governed validation for the exact frozen MOM-A-002 plus A2-002 architecture.",
        "verification": manifest["verification"],
    }
    write_json(reports / REPORT_NAMES[0], summary)
    return summary


def finalize_cross_family_evidence_synthesis(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = output_root(root) / "manifests/cross_family_evidence_synthesis_manifest_v1.json"
    summary = _read_json(summary_path)
    manifest = _read_json(manifest_path)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": all(
            value.startswith("PASS")
            for value in (backend_targeted_tests, backend_full_tests, frontend_build)
        ),
        "finalized_at": utc_now(),
    }
    manifest["verification"] = verification
    manifest["cross_family_synthesis_hash"] = _document_hash(
        manifest, "cross_family_synthesis_hash"
    )
    write_json(manifest_path, manifest)
    summary["verification"] = verification
    summary["cross_family_synthesis_hash"] = manifest["cross_family_synthesis_hash"]
    write_json(summary_path, summary)
    return summary


__all__ = [
    "AUTHORIZED_ROADMAP_SUCCESSOR_HASHES",
    "CANDIDATE_SELECTION_CLASSIFICATION",
    "CLASSIFICATION_BUCKETS",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "CONTAMINATION_DISCLOSURE",
    "DISCOVERY_CYCLE_STATUS",
    "FAMILY_A_VALIDATION_CANDIDACY",
    "FAMILY_CLASSIFICATIONS",
    "FAMILY_CLOSURE_HASHES",
    "FAMILY_FINAL_STATUSES",
    "FAMILY_H_STATUS",
    "INPUT_FILE_HASHES",
    "MANIFEST_VERSION",
    "MILESTONE_COMMIT",
    "NEXT_PLANNED_PHASE",
    "PRIMARY_QUESTION_RESULT",
    "PROVISIONAL_CANDIDATE_ID",
    "PROVISIONAL_CANDIDATE_STATUS",
    "REPORT_NAMES",
    "STRATEGY_V2_STATUS",
    "SYNTHESIS_ROADMAP_COMPONENT_HASH",
    "VALIDATION_DESIGN_READINESS",
    "build_cross_family_evidence_synthesis",
    "candidate_selection_document",
    "evidence_dimension_rows",
    "family_a_candidate_gate_rows",
    "family_matrix_rows",
    "finalize_cross_family_evidence_synthesis",
    "synthesis_component_hash_matches",
    "verify_git_milestone",
    "verify_synthesis_inputs",
]
