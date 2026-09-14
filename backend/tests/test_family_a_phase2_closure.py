from __future__ import annotations

import json
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_phase2_closure import (
    A2_001_RESEARCH_STATUS,
    A2_002_RESEARCH_STATUS,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_CLOSURE_HASH,
    FAMILY_A_EVIDENCE_STATUS,
    FAMILY_A_RESEARCH_STATUS,
    FAMILY_A_STRATEGY_V2_STATUS,
    FAMILY_A_VALIDATION_STATUS,
    GOVERNANCE_FINDING_ID,
    GOVERNANCE_POLICY_VERSION,
    NEXT_PLANNED_RESEARCH_FAMILY,
    PRACTICAL_CAPITAL_REFERENCE,
    PRIMARY_ARCHITECTURE_REFERENCE,
    PREREGISTRATION_CHECKLIST,
    REPORT_NAMES,
    RETENTION_BAND_CONCEPT_STATUS,
    SMALL_CAPITAL_REFERENCE,
    closure_baseline_snapshot,
    governance_policy,
    verify_closure_inputs,
)
from app.research.strategy.family_a_phase2_development_evaluation import EXPECTED_RESULT_HASHES
from app.research.strategy.family_a_phase2_research import EXPECTED_PHASE2_EXPERIMENT_HASHES


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_a_closure_v1_summary.json"


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_exact_command_identity() -> None:
    assert COMMAND_VERSION == "FAMILY_A_PHASE2_CLOSURE_V1"
    assert COMMAND_PROFILE == "FAMILY_A_RESEARCH_FREEZE_AND_GOVERNANCE_V1"


def test_all_frozen_inputs_and_result_hashes_verify() -> None:
    verified = verify_closure_inputs(REPO_ROOT)
    assert verified["status"] == "VERIFIED"
    assert all(verified["checks"].values())
    assert verified["results"]["A2-001"]["development_result_hash"] == EXPECTED_RESULT_HASHES["A2-001"]
    assert verified["results"]["A2-002"]["development_result_hash"] == EXPECTED_RESULT_HASHES["A2-002"]


def test_a2_001_is_closed_without_advancement_or_retuning() -> None:
    result = summary()
    assert A2_001_RESEARCH_STATUS == "CLOSED_NOT_ADVANCED"
    assert result["statuses"]["A2_001_RESEARCH_STATUS"] == A2_001_RESEARCH_STATUS
    assert result["governance"]["retention_retuned"] is False


def test_retention_concept_is_deprioritized_not_permanently_banned() -> None:
    assert RETENTION_BAND_CONCEPT_STATUS == "DEPRIORITIZED_FOR_CURRENT_FAMILY_A_VERSION"
    resume_conditions = summary()["closure"]["family_a_resume_conditions"]
    assert "GENUINELY_NEW_HYPOTHESIS" in resume_conditions


def test_a2_002_is_retained_as_implementation_evidence() -> None:
    assert A2_002_RESEARCH_STATUS == "SUPPORTED_IMPLEMENTATION_EVIDENCE"
    assert summary()["statuses"]["A2_002_RESEARCH_STATUS"] == A2_002_RESEARCH_STATUS


def test_capital_references_are_exact_and_preserved() -> None:
    result = summary()
    assert PRACTICAL_CAPITAL_REFERENCE == 500_000
    assert SMALL_CAPITAL_REFERENCE == 100_000
    assert result["capital_references"]["FAMILY_A_PRACTICAL_RESEARCH_CAPITAL_REFERENCE_V1_INR"] == 500_000
    assert result["capital_references"]["SMALL_CAPITAL_REFERENCE_INR"] == 100_000


def test_capital_reference_is_not_an_alpha_or_live_capital_claim() -> None:
    interpretation = summary()["capital_references"]["interpretation"]
    assert interpretation["alpha_parameter"] is False
    assert interpretation["profitability_threshold"] is False
    assert interpretation["live_capital_recommendation"] is False
    assert interpretation["proof_larger_capital_always_performs_better"] is False


def test_mom_a_002_is_reference_without_winner_label() -> None:
    architecture = summary()["architecture_reference"]
    assert PRIMARY_ARCHITECTURE_REFERENCE == "MOM-A-002"
    assert architecture["PRIMARY_ARCHITECTURE_REFERENCE"] == "MOM-A-002"
    assert architecture["role"] == "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL"
    assert architecture["role"] not in {"BEST", "WINNER", "OPTIMAL"}


def test_family_status_evidence_validation_and_v2_are_exact() -> None:
    statuses = summary()["statuses"]
    assert statuses["FAMILY_A_RESEARCH_STATUS"] == FAMILY_A_RESEARCH_STATUS
    assert statuses["FAMILY_A_EVIDENCE_STATUS"] == FAMILY_A_EVIDENCE_STATUS
    assert statuses["FAMILY_A_VALIDATION_STATUS"] == FAMILY_A_VALIDATION_STATUS == "NOT_ACCESSED"
    assert statuses["FAMILY_A_STRATEGY_V2_STATUS"] == FAMILY_A_STRATEGY_V2_STATUS == "NOT_CREATED"


def test_no_performance_rerun_new_metric_search_or_capital_search() -> None:
    governance = summary()["governance"]
    assert governance["performance_recomputed"] is False
    assert governance["new_performance_experiments"] == 0
    assert governance["new_strategy_metrics_created"] is False
    assert governance["retention_retuned"] is False
    assert governance["alternate_capital_tested"] is False


def test_governance_finding_and_policy_v2() -> None:
    result = summary()["governance"]
    assert result["finding"]["finding_id"] == GOVERNANCE_FINDING_ID
    assert result["policy"]["policy_version"] == GOVERNANCE_POLICY_VERSION
    assert result["finding"]["classification_treatment"] == "COMMAND_04_LABELS_ARE_DESCRIPTIVE_NOT_PREREGISTERED"
    assert result["finding"]["raw_metric_precedence"] is True


def test_numeric_threshold_rule_is_prospective() -> None:
    policy = governance_policy()
    assert policy["historical_experiment_records_rewritten"] is False
    assert "before performance evaluation" in policy["numeric_threshold_rule"]["required"]
    assert policy["numeric_threshold_rule"]["evidence_precedence"] == (
        "IMMUTABLE_RAW_METRICS_TAKE_PRECEDENCE_OVER_LABELS"
    )


def test_full_preregistration_checklist_is_present() -> None:
    policy = governance_policy()
    assert len(PREREGISTRATION_CHECKLIST) == 14
    assert policy["required_preregistration_checklist"] == list(PREREGISTRATION_CHECKLIST)
    assert "numerical_success_criteria_where_applicable" in PREREGISTRATION_CHECKLIST
    assert "validation_eligibility_rule" in PREREGISTRATION_CHECKLIST


def test_closure_manifest_hash_recomputes_exactly() -> None:
    manifest = summary()["closure"]
    body = {key: value for key, value in manifest.items() if key != "family_a_closure_hash"}
    assert manifest["family_a_closure_hash"] == EXPECTED_CLOSURE_HASH
    assert canonical_hash(body) == EXPECTED_CLOSURE_HASH


def test_closure_registry_preserves_all_prior_hashes() -> None:
    result = summary()
    registry = json.loads((REPO_ROOT / result["storage"]["registry"]).read_text(encoding="utf-8"))
    assert [row["result_hash"] for row in registry["phase2_experiments"]] == [
        EXPECTED_RESULT_HASHES["A2-001"],
        EXPECTED_RESULT_HASHES["A2-002"],
    ]
    assert [row["preregistration_hash"] for row in registry["phase2_experiments"]] == [
        EXPECTED_PHASE2_EXPERIMENT_HASHES["A2-001"]["preregistration_hash"],
        EXPECTED_PHASE2_EXPERIMENT_HASHES["A2-002"]["preregistration_hash"],
    ]


def test_family_b_is_planning_note_only() -> None:
    handoff = summary()["family_b_handoff"]
    assert handoff["NEXT_PLANNED_RESEARCH_FAMILY"] == NEXT_PLANNED_RESEARCH_FAMILY
    assert handoff["status"] == "NEXT_PLANNED"
    assert handoff["parameters_defined"] is False
    assert handoff["experiments_registered"] == 0
    assert handoff["code_implemented"] is False
    assert handoff["backtest_run"] is False
    assert handoff["authorized_to_start"] is False


def test_roadmap_preserves_family_a_status_after_later_family_handoffs() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |" in roadmap
    for family in "EFG":
        assert f"| Family {family} |" in roadmap
    assert roadmap.count("PLANNED_NOT_STARTED") >= 3


def test_closure_baseline_snapshot_is_stable_and_clean() -> None:
    before = closure_baseline_snapshot(REPO_ROOT)
    after = closure_baseline_snapshot(REPO_ROOT)
    assert before == after
    assert before["cap4_validation_state"] == "EVALUATED"
    assert before["cap4_validation_run_count"] == 1


def test_all_reports_and_required_output_subdirectories_exist() -> None:
    result = summary()
    assert len(REPORT_NAMES) == 4
    assert all((REPO_ROOT / "data/reports" / name).exists() for name in REPORT_NAMES)
    output_root = REPO_ROOT / result["storage"]["root"]
    assert all((output_root / name).is_dir() for name in ("manifest", "governance", "handoff"))
