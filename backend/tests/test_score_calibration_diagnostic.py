from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.score_calibration_diagnostic import (
    CLASSIFICATION_RULES,
    COMPONENT_FIELDS,
    COMPONENT_LEVELS,
    SCORE_CALIBRATION_COMMAND_VERSION,
    SCORE_CALIBRATION_EXPERIMENT_IDS,
    ScoreCalibrationRegistry,
    average_ranks,
    build_score_calibration_definitions,
    calculate_score_calibration_pre_registration_hash,
    correlation_direction,
    pearson,
    sample_size_flag,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_score_calibration_summary.json"


def test_exact_command_04_allowlist_and_preregistration_policy() -> None:
    definitions = build_score_calibration_definitions("2026-01-01T00:00:00+00:00")
    assert SCORE_CALIBRATION_COMMAND_VERSION == "STRATEGY_DIAGNOSTIC_SCORE_CALIBRATION_V1"
    assert tuple(row.experiment_id for row in definitions) == SCORE_CALIBRATION_EXPERIMENT_IDS
    assert len(definitions) == 10
    assert {row.family for row in definitions} == {"SCORE_CALIBRATION_DIAGNOSTIC"}
    assert all(row.pre_registered and row.parameters_locked_before_run for row in definitions)
    assert all(row.diagnostic_only and not row.eligible_for_promotion for row in definitions)


def test_score_calibration_registry_rejects_extra_or_wrong_family() -> None:
    definition = build_score_calibration_definitions("2026-01-01T00:00:00+00:00")[0]
    with pytest.raises(ValueError, match="Unauthorized"):
        ScoreCalibrationRegistry({"frozen": "hash"}).register(
            replace(definition, experiment_id="EXP-SCORECAL-011")
        )
    with pytest.raises(ValueError, match="SCORE_CALIBRATION_DIAGNOSTIC"):
        ScoreCalibrationRegistry({"frozen": "hash"}).register(
            replace(definition, family="OTHER")
        )


def test_preregistration_hash_covers_score_identity_parameters_and_baselines() -> None:
    definition = build_score_calibration_definitions("2026-01-01T00:00:00+00:00")[1]
    changed = replace(definition, parameters=definition.parameters + (("changed", True),))
    baseline = {"score_v1": "abc"}
    assert calculate_score_calibration_pre_registration_hash(definition, baseline)
    assert calculate_score_calibration_pre_registration_hash(definition, baseline) != calculate_score_calibration_pre_registration_hash(changed, baseline)
    assert calculate_score_calibration_pre_registration_hash(definition, baseline) != calculate_score_calibration_pre_registration_hash(definition, {"score_v1": "changed"})


def test_frozen_score_identity_and_component_mappings_are_exact() -> None:
    summary = load_summary()
    frozen = summary["frozen_score"]
    assert frozen["version"] == CURRENT_STRATEGY_SCORE_VERSION
    assert frozen["profile"] == CURRENT_STRATEGY_SCORE_PROFILE
    assert frozen["config_hash"] == CURRENT_STRATEGY_SCORE_CONFIG_HASH
    assert frozen["entry_eligible_threshold"] == 80
    assert frozen["high_conviction_threshold"] == 90
    assert frozen["score_rewrite_performed"] is False
    assert frozen["component_levels"] == {
        key: list(values) for key, values in COMPONENT_LEVELS.items()
    }


def test_source_and_admitted_populations_and_score_arithmetic() -> None:
    summary = load_summary()
    integrity = summary["population_integrity"]
    assert integrity == {
        "source_opportunities": 3296,
        "entry_eligible_opportunities": 3296,
        "admitted_trades": 728,
        "skipped_opportunities": 2568,
        "slot_skipped_opportunities": 2398,
        "unchanged": True,
        "ranking_changed": False,
        "portfolio_rerun_performed": False,
    }
    for case in summary["pilot"]["cases"]:
        assert sum(case[field] for field in COMPONENT_FIELDS.values()) == case["raw_strategy_score"]
        assert case["arithmetic_sum"] == case["raw_strategy_score"]


@pytest.mark.parametrize(
    ("experiment_id", "component"),
    [
        ("EXP-SCORECAL-002", "SETUP"),
        ("EXP-SCORECAL-003", "MOMENTUM"),
        ("EXP-SCORECAL-004", "RVOL"),
        ("EXP-SCORECAL-005", "RS"),
        ("EXP-SCORECAL-006", "REGIME"),
        ("EXP-SCORECAL-007", "RR"),
    ],
)
def test_component_discrimination_tables_cover_levels_and_populations(
    experiment_id: str,
    component: str,
) -> None:
    rows = load_summary()["tables"][experiment_id]
    assert {row["component_value"] for row in rows} == set(COMPONENT_LEVELS[component])
    assert {row["population"] for row in rows} == {"SOURCE", "ADMITTED", "SKIPPED", "SLOT_SKIPPED"}
    assert all(
        {
            "sample_size",
            "mean_mfe_r",
            "mean_mae_r",
            "mean_realized_r",
            "positive_trade_rate_pct",
            "target_first_pct",
            "stop_first_pct",
            "target_rate_pct",
            "stop_rate_pct",
            "time_rate_pct",
            "time_exits",
        }
        <= set(row)
        for row in rows
    )


def test_score_profiles_and_decomposition_cover_80_through_85() -> None:
    summary = load_summary()
    profiles = summary["score_profiles"]
    assert [row["raw_strategy_score"] for row in profiles] == [80, 81, 82, 83, 84, 85]
    assert sum(row["sample_size"] for row in profiles) == 3296
    assert sum(row["admitted_count"] for row in profiles) == 728
    decomposition = summary["tables"]["EXP-SCORECAL-009"]
    assert len(decomposition) == 6
    for row in decomposition:
        score = row["raw_strategy_score"]
        component_total = sum(
            Decimal(str(row[f"mean_{field}"])) for field in COMPONENT_FIELDS.values()
        )
        assert abs(component_total - Decimal(score)) <= Decimal("0.000000001")
        assert all(f"{field}_contribution_pct" in row for field in COMPONENT_FIELDS.values())


def test_component_vectors_are_exact_and_sample_safe() -> None:
    summary = load_summary()
    rows = summary["tables"]["EXP-SCORECAL-008"]
    assert len(rows) == summary["auxiliary_analyses"]["unique_source_component_vectors"]
    assert sum(row["sample_size"] for row in rows) == 3296
    assert sum(bool(row["top_20"]) for row in rows) == min(20, len(rows))
    assert all(row["sample_size_flag"] == sample_size_flag(row["sample_size"]) for row in rows)
    assert all(len(row["component_vector"].split("|")) == 6 for row in rows)


def test_component_correlations_and_redundancy_are_descriptive() -> None:
    summary = load_summary()
    correlations = summary["correlations"]
    redundancy = [row for row in correlations if row["section"] == "COMPONENT_REDUNDANCY"]
    assert len(redundancy) == 30
    assert {row["population"] for row in redundancy} == {"SOURCE", "ADMITTED"}
    assert all(row["descriptive_only"] is True for row in correlations)
    assert all(row["significance_tested"] is False for row in correlations)
    assert summary["classifications"]["COMPONENT_REDUNDANCY_RESULT"] in {
        "LOW",
        "MODERATE_ACCEPTABLE",
        "POTENTIAL_DOUBLE_COUNTING",
        "HIGH",
        "INCONCLUSIVE",
    }


def test_leave_one_out_is_arithmetic_only_and_does_not_rerun_portfolio() -> None:
    rows = load_summary()["auxiliary_analyses"]["leave_one_out_dependency"]
    assert {row["component"] for row in rows} == set(COMPONENT_FIELDS)
    assert all(row["arithmetic_only"] for row in rows)
    assert all(row["renormalized"] is False for row in rows)
    assert all(row["portfolio_rerun"] is False for row in rows)
    assert all(row["drop_below_80_count"] + row["retained_at_or_above_80_count"] == 3296 for row in rows)


def test_yearly_stability_covers_all_years_components_and_levels() -> None:
    summary = load_summary()
    rows = summary["tables"]["EXP-SCORECAL-010"]
    overviews = [row for row in rows if row["section"] == "YEAR_COMPONENT_OVERVIEW"]
    assert {(row["year"], row["component"]) for row in overviews} == {
        (year, component) for year in range(2022, 2027) for component in COMPONENT_FIELDS
    }
    assert all(row["period_status"] == ("PARTIAL" if row["year"] == 2026 else "COMPLETE") for row in rows)
    assert set(summary["auxiliary_analyses"]["yearly_stability"]) == set(COMPONENT_FIELDS)


def test_small_sample_boundaries_are_locked() -> None:
    assert sample_size_flag(0) == "VERY_SMALL"
    assert sample_size_flag(29) == "VERY_SMALL"
    assert sample_size_flag(30) == "SMALL"
    assert sample_size_flag(99) == "SMALL"
    assert sample_size_flag(100) == "LIMITED"
    assert sample_size_flag(299) == "LIMITED"
    assert sample_size_flag(300) == "ADEQUATE_FOR_DESCRIPTION"


def test_correlation_helpers_are_deterministic_and_handle_direction() -> None:
    assert average_ranks([1, 2, 2, 4]) == [1.0, 2.5, 2.5, 4.0]
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert correlation_direction(0.1) == "POSITIVE"
    assert correlation_direction(-0.1) == "NEGATIVE"
    assert correlation_direction(0.01) == "NEUTRAL"
    assert correlation_direction(None) == "INCONCLUSIVE"


def test_classifications_are_finite_and_no_promotion_or_rewrite_occurred() -> None:
    summary = load_summary()
    assert set(CLASSIFICATION_RULES) <= {
        "TOTAL_SCORE_MONOTONICITY",
        "COMPONENT_DISCRIMINATION",
        "COMPONENT_REDUNDANCY",
        "YEARLY_STABILITY",
        "TOTAL_SCORE_CALIBRATION",
        "SCORE_84_85",
    }
    assert summary["promotion_allowed"] is False
    assert summary["experiments_promoted"] == 0
    assert summary["automatic_selection_performed"] is False
    assert summary["score_weight_changed"] is False
    assert summary["score_threshold_changed"] is False
    assert summary["optimizer_or_ml_run"] is False
    assert summary["population_integrity"]["portfolio_rerun_performed"] is False


def test_full_summary_registry_reproducibility_and_readiness() -> None:
    summary = load_summary()
    assert summary["newly_registered_experiment_ids"] == list(SCORE_CALIBRATION_EXPERIMENT_IDS)
    assert summary["newly_registered_experiment_count"] == 10
    assert summary["registry_preservation"] == {
        "previous_experiment_count": 29,
        "previous_parameter_and_preregistration_hashes_unchanged": True,
        "combined_registry_count": 39,
    }
    assert summary["all_experiments_reproducible"] is True
    assert summary["failed_experiment_count"] == 0
    assert summary["baseline_mutation_violations"] == 0
    assert summary["pilot"]["passed"] is True
    assert summary["pilot"]["real_case_count"] == 14
    assert summary["classifications"]["FRAMEWORK_RESULT"] == "CLEAN"
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True


def test_previous_29_registry_records_and_frozen_hashes_are_unchanged() -> None:
    summary = load_summary()
    registry = json.loads((DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json").read_text(encoding="utf-8"))
    score_calibration = [row for row in registry["experiments"] if row["experiment_id"] in SCORE_CALIBRATION_EXPERIMENT_IDS]
    assert len(score_calibration) == 10
    assert len(registry["experiments"]) >= 39
    assert all(row["status"] == "COMPLETE" for row in registry["experiments"])
    assert all(row["parameter_hash"] and row["pre_registration_hash"] for row in registry["experiments"])
    assert summary["registry_preservation"]["previous_parameter_and_preregistration_hashes_unchanged"] is True
    hashes = portfolio_backtest_regression_hashes(DATA_DIR)
    assert all(portfolio_backtest_regression_hash_checks(hashes).values())


def test_required_reports_and_isolated_runs_exist() -> None:
    filenames = (
        "strategy_diagnostic_v1_score_calibration_summary.json",
        "strategy_diagnostic_v1_score_calibration_totals.csv",
        "strategy_diagnostic_v1_score_calibration_setup.csv",
        "strategy_diagnostic_v1_score_calibration_momentum.csv",
        "strategy_diagnostic_v1_score_calibration_rvol.csv",
        "strategy_diagnostic_v1_score_calibration_rs.csv",
        "strategy_diagnostic_v1_score_calibration_regime.csv",
        "strategy_diagnostic_v1_score_calibration_rr.csv",
        "strategy_diagnostic_v1_score_calibration_vectors.csv",
        "strategy_diagnostic_v1_score_calibration_score_decomposition.csv",
        "strategy_diagnostic_v1_score_calibration_correlations.csv",
        "strategy_diagnostic_v1_score_calibration_yearly.csv",
        "strategy_diagnostic_v1_score_calibration_pilot.csv",
    )
    assert all((DATA_DIR / "reports" / filename).exists() for filename in filenames)
    root = DATA_DIR / "research/diagnostics/strategy/v1/score_calibration_command_04"
    assert (root / "registry/score_calibration_experiment_registry_v1_preregistered.json").exists()
    assert (root / "registry/score_calibration_experiment_registry_v1.json").exists()
    assert all((root / "runs" / item / "result.json").exists() for item in SCORE_CALIBRATION_EXPERIMENT_IDS)


def test_no_model_optimizer_threshold_search_or_winner_selector() -> None:
    source = (REPO_ROOT / "backend/app/diagnostics/score_calibration_diagnostic.py").read_text(encoding="utf-8").lower()
    assert "sklearn" not in source
    assert "statsmodels" not in source
    assert "def optimize" not in source
    assert "def select_best" not in source
    assert "best_component" not in source
    assert "optimal_weight" not in source
    assert "winning_score" not in source


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
