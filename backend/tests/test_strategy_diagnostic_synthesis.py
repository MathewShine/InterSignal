from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.strategy_diagnostic_synthesis import (
    EVIDENCE_STRENGTH_VALUES,
    EXPECTED_EXPERIMENT_IDS,
    EXPECTED_REGISTRY_FINGERPRINT,
    HYPOTHESIS_STATUS_VALUES,
    IMPLEMENTATION_COMPLEXITY_VALUES,
    IMPACT_SCOPE_VALUES,
    OVERFITTING_RISK_VALUES,
    PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY,
    PRIORITY_CLASS_VALUES,
    PRIORITY_WEIGHTS,
    SYNTHESIS_PROFILE,
    SYNTHESIS_VERSION,
    build_hypothesis_catalog,
    next_experiment_proposals,
    infrastructure_priorities,
    registry_fingerprint,
    validate_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_synthesis_summary.json"
REGISTRY_PATH = DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def load_registry() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_synthesis_identity_and_registry_remains_49() -> None:
    summary = load_summary()
    assert SYNTHESIS_VERSION == "STRATEGY_DIAGNOSTIC_SYNTHESIS_V1"
    assert SYNTHESIS_PROFILE == "SWING_STRATEGY_RESEARCH_SYNTHESIS_V1"
    assert summary["synthesis_version"] == SYNTHESIS_VERSION
    assert summary["synthesis_profile"] == SYNTHESIS_PROFILE
    assert summary["completed_experiments_synthesized"] == 49
    assert summary["registry_experiment_count_after_synthesis"] == 49
    assert summary["registry_verification"]["synthesis_record_added"] is False


def test_registry_allowlist_hash_completion_and_no_promotion() -> None:
    registry = load_registry()
    verification = validate_registry(registry)
    assert tuple(row["experiment_id"] for row in registry["experiments"]) == EXPECTED_EXPERIMENT_IDS
    assert len(EXPECTED_EXPERIMENT_IDS) == 49
    assert registry_fingerprint(registry) == EXPECTED_REGISTRY_FINGERPRINT
    assert verification["all_previous_hashes_unchanged"] is True
    assert verification["failed_experiment_count"] == 0
    assert verification["promoted_experiment_count"] == 0


def test_registry_validation_stops_on_count_id_status_or_hash_change() -> None:
    original = load_registry()
    changed_count = copy.deepcopy(original)
    changed_count["experiments"].pop()
    with pytest.raises(ValueError, match="exactly 49"):
        validate_registry(changed_count)
    changed_id = copy.deepcopy(original)
    changed_id["experiments"][0]["experiment_id"] = "EXP-UNAUTHORIZED-001"
    with pytest.raises(ValueError, match="unauthorized"):
        validate_registry(changed_id)
    changed_status = copy.deepcopy(original)
    changed_status["experiments"][0]["status"] = "FAILED"
    with pytest.raises(ValueError, match="COMPLETE"):
        validate_registry(changed_status)
    changed_hash = copy.deepcopy(original)
    changed_hash["experiments"][0]["parameter_hash"] = "changed"
    with pytest.raises(ValueError, match="hashes differ"):
        validate_registry(changed_hash)


def test_hypothesis_catalog_exact_ids_and_allowed_states() -> None:
    rows = build_hypothesis_catalog()
    expected = {
        "H-RANK-01", "H-HOLD-01", "H-GAP-01", "H-EXIT-01", "H-EXIT-02", "H-EXIT-03",
        "H-ENTRYQ-01", "H-SCORE-01", "H-SCORE-02", "H-RR-01", "H-REGIME-01",
        "H-REGIME-02", "H-BREADTH-01", "H-PERSIST-01", "H-SLOT-01", "H-COST-01",
        "H-ROBUST-01", "H-BASELINE-01",
    }
    assert {row["hypothesis_id"] for row in rows} == expected
    assert len(rows) == 18
    assert all(row["status"] in HYPOTHESIS_STATUS_VALUES for row in rows)
    assert all(row["evidence_strength"] in EVIDENCE_STRENGTH_VALUES for row in rows)
    assert all(row["overfitting_risk"] in OVERFITTING_RISK_VALUES for row in rows)
    assert all(row["implementation_complexity"] in IMPLEMENTATION_COMPLEXITY_VALUES for row in rows)
    assert all(row["impact_scope"] in IMPACT_SCOPE_VALUES for row in rows)
    assert all(row["priority_class"] in PRIORITY_CLASS_VALUES for row in rows)


def test_priority_method_is_non_performance_and_weights_are_locked() -> None:
    summary = load_summary()
    method = summary["priority_methodology"]
    assert method["weights"] == PRIORITY_WEIGHTS
    assert sum(method["weights"].values()) == 100
    assert method["historical_return_cagr_drawdown_used"] is False
    assert method["direct_historical_winner_selection"] is False
    assert set(method["performance_fields_excluded"]) == set(PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY)
    for row in summary["hypotheses"]:
        assert row["priority_inputs"]["historical_performance_metrics_used"] is False
        assert not set(row["priority_inputs"]) & set(PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY)


def test_priority_a_records_meet_the_declared_candidate_rule() -> None:
    for row in build_hypothesis_catalog():
        if row["priority_class"] != "PRIORITY_A":
            continue
        assert row["status"] not in {"NOT_SUPPORTED", "DEPRIORITIZED", "ALREADY_DISPROVEN_SIMPLE_FORM"}
        assert row["sample_quality"] in {"ADEQUATE", "LIMITED"}
        assert row["overfitting_risk"] in {"LOW", "MODERATE"}
        assert row["priority_inputs"]["parameter_dimensions"] <= 1
        assert row["priority_inputs"]["post_hoc_threshold_mining"] is False
        assert row["falsification_criteria"]


def test_proposal_limits_single_dimension_and_falsification() -> None:
    proposals = next_experiment_proposals()
    infrastructure = infrastructure_priorities()
    assert len(proposals) == 3
    assert len(infrastructure) == 3
    assert len({row["hypothesis_id"] for row in proposals}) == 3
    assert all(row["one_changed_dimension"] and row["falsification_criteria"] for row in proposals)
    assert all(row["promotion_prohibited"] and not row["executed"] for row in proposals)
    assert all(not row["implemented"] for row in infrastructure)


def test_no_strategy_v2_live_or_promotion_actions() -> None:
    summary = load_summary()
    policies = summary["policies"]
    assert policies["strategy_v2_created"] is False
    assert policies["score_v2_created"] is False
    assert policies["risk_v2_created"] is False
    assert policies["regime_v2_created"] is False
    assert policies["new_strategy_variant_run"] is False
    assert policies["new_experiment_executed"] is False
    assert policies["experiment_promoted"] is False
    assert policies["historical_winner_selected"] is False
    assert policies["optimizer_grid_search_or_ml_run"] is False
    assert summary["readiness"]["LIVE_TRADING_READY"] is False
    assert summary["readiness"]["SMALL_CAPITAL_LIVE_READY"] is False


def test_traceability_and_manual_validation_are_complete() -> None:
    summary = load_summary()
    assert summary["traceability_verified"] is True
    assert len(summary["source_reports"]) == 5
    assert all(row["traceability"]["source_command"] for row in summary["hypotheses"])
    assert all(row["traceability"]["experiment_ids"] for row in summary["hypotheses"])
    assert all(row["traceability"]["source_report"] for row in summary["hypotheses"])
    assert len(summary["pilot_manual_validation"]) == 8
    assert all(row["passed"] for row in summary["pilot_manual_validation"])


def test_ruled_out_unresolved_data_gaps_and_coverage() -> None:
    summary = load_summary()
    assert summary["ruled_out_simple_form_count"] == 14
    assert summary["unresolved_core_question_count"] == 9
    assert len(summary["data_limitations"]) == 14
    assert {row["classification"] for row in summary["data_limitations"]} <= {"BLOCKS_LATER_TEST", "LIMITS_INTERPRETATION", "ACCEPTABLE_FOR_DIAGNOSTIC"}
    assert len(summary["diagnostic_coverage"]) == 13
    assert summary["classifications"]["DIAGNOSTIC_COVERAGE_RESULT"] == "BROAD"
    assert summary["multiple_comparison_risk"]["classification"] == "HIGH"


def test_temporal_protocol_samples_and_validation_is_untouched() -> None:
    protocol = load_summary()["temporal_validation_protocol"]
    assert protocol["development_source_opportunities"] == 2068
    assert protocol["development_admitted_trades"] == 478
    assert protocol["validation_source_opportunities"] == 1224
    assert protocol["validation_admitted_trades"] == 246
    assert protocol["validation_tuning_prohibited"] is True
    assert load_summary()["walk_forward_recommendation"]["implemented_now"] is False


def test_readiness_data_and_score_classifications() -> None:
    classifications = load_summary()["classifications"]
    assert classifications == {
        "DIAGNOSTIC_COVERAGE_RESULT": "BROAD",
        "OVERFITTING_RISK_RESULT": "HIGH",
        "STRATEGY_V1_RESEARCH_RESULT": "WEAK_AND_REQUIRES_RESEARCH",
        "DATA_READINESS_RESULT": "LIMITED_BUT_USABLE",
        "NEXT_PHASE_READINESS": "INFRASTRUCTURE_REQUIRED_FIRST",
        "SCORE_COMPLETENESS_RESULT": "LIMITED_BY_MISSING_COMPONENTS",
        "INTRADAY_DATA_PRIORITY": "CRITICAL",
        "TRANSACTION_COST_MODEL_PRIORITY": "HIGH_PRIORITY_INFRASTRUCTURE",
    }


def test_experiment_design_template_has_every_required_field() -> None:
    template = load_summary()["experiment_design_template"]
    assert set(template) == {
        "experiment_id", "hypothesis", "one_changed_dimension", "baseline_comparison",
        "predeclared_parameters", "primary_metrics", "secondary_metrics", "sample_size_requirement",
        "temporal_robustness_requirement", "falsification_criteria", "promotion_prohibited",
        "follow_up_decision_rule",
    }
    assert template["promotion_prohibited"] is True


def test_reproducibility_baseline_and_source_mutation_guards() -> None:
    summary = load_summary()
    assert summary["reproducibility"]["match"] is True
    assert summary["reproducibility"]["first_fingerprint"] == summary["reproducibility"]["second_fingerprint"]
    assert summary["baseline_mutation_violations"] == 0
    assert summary["source_reports_unchanged"] is True
    assert summary["registry_unchanged"] is True
    hashes = portfolio_backtest_regression_hashes(DATA_DIR)
    assert all(portfolio_backtest_regression_hash_checks(hashes).values())


def test_all_machine_reports_and_isolated_storage_exist() -> None:
    names = (
        "strategy_diagnostic_v1_synthesis_summary.json",
        "strategy_diagnostic_v1_synthesis_hypotheses.csv",
        "strategy_diagnostic_v1_synthesis_ruled_out.csv",
        "strategy_diagnostic_v1_synthesis_unresolved.csv",
        "strategy_diagnostic_v1_synthesis_priorities.csv",
        "strategy_diagnostic_v1_synthesis_data_gaps.csv",
        "strategy_diagnostic_v1_synthesis_research_branches.csv",
        "strategy_diagnostic_v1_synthesis_next_experiments.csv",
        "strategy_diagnostic_v1_synthesis_infrastructure.csv",
    )
    assert all((DATA_DIR / "reports" / name).exists() for name in names)
    root = DATA_DIR / "research/diagnostics/strategy/v1/synthesis_command_06"
    assert (root / "synthesis_payload_v1.json").exists()
    assert (root / "source_integrity_v1.json").exists()


def test_full_summary_gate_is_ready_after_final_validation() -> None:
    summary = load_summary()
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True


def test_source_has_no_network_optimizer_or_strategy_variant_engine() -> None:
    source = (REPO_ROOT / "backend/app/diagnostics/strategy_diagnostic_synthesis.py").read_text(encoding="utf-8").lower()
    assert "requests." not in source
    assert "httpx." not in source
    assert "urlopen(" not in source
    assert "sklearn" not in source
    assert "def optimize" not in source
    assert "gridsearch" not in source
    assert "run_portfolio_backtest" not in source
