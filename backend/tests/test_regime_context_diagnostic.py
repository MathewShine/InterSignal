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
from app.diagnostics.regime_context_diagnostic import (
    BORDERLINE_BUCKETS,
    BREADTH_BUCKETS,
    BULLISH_STRENGTH_BUCKETS,
    GAP_BUCKETS,
    NEUTRAL_POSITION_BUCKETS,
    REGIME_CONTEXT_COMMAND_VERSION,
    REGIME_CONTEXT_EXPERIMENT_IDS,
    REGIME_SCORE_BUCKETS,
    RR_BUCKETS,
    SECTOR_BUCKETS,
    STREAK_BUCKETS,
    TREND_BUCKETS,
    RegimeContextRegistry,
    bucket_for,
    build_regime_context_definitions,
    calculate_regime_context_pre_registration_hash,
    in_bucket,
    sample_size_flag,
)
from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_regime_context_summary.json"


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_exact_command_05_allowlist_and_preregistration_policy() -> None:
    definitions = build_regime_context_definitions("2026-01-01T00:00:00+00:00")
    assert REGIME_CONTEXT_COMMAND_VERSION == "STRATEGY_DIAGNOSTIC_REGIME_CONTEXT_V1"
    assert tuple(row.experiment_id for row in definitions) == REGIME_CONTEXT_EXPERIMENT_IDS
    assert len(definitions) == 10
    assert {row.family for row in definitions} == {"REGIME_CONTEXT_DIAGNOSTIC"}
    assert all(row.pre_registered and row.parameters_locked_before_run for row in definitions)
    assert all(row.diagnostic_only and not row.eligible_for_promotion for row in definitions)


def test_registry_rejects_extra_ids_wrong_family_and_promotion() -> None:
    definition = build_regime_context_definitions("2026-01-01T00:00:00+00:00")[0]
    registry = RegimeContextRegistry({"frozen": "hash"})
    with pytest.raises(ValueError, match="Unauthorized"):
        registry.register(replace(definition, experiment_id="EXP-REGIME-011"))
    with pytest.raises(ValueError, match="REGIME_CONTEXT_DIAGNOSTIC"):
        registry.register(replace(definition, family="OTHER"))
    with pytest.raises(ValueError, match="promotion"):
        registry.register(replace(definition, eligible_for_promotion=True))


def test_preregistration_hash_covers_frozen_parameters_and_baselines() -> None:
    definition = build_regime_context_definitions("2026-01-01T00:00:00+00:00")[1]
    changed = replace(definition, parameters=definition.parameters + (("changed", True),))
    baseline = {"regime": "abc"}
    assert calculate_regime_context_pre_registration_hash(definition, baseline)
    assert calculate_regime_context_pre_registration_hash(definition, baseline) != calculate_regime_context_pre_registration_hash(changed, baseline)
    assert calculate_regime_context_pre_registration_hash(definition, baseline) != calculate_regime_context_pre_registration_hash(definition, {"regime": "changed"})


def test_frozen_regime_identity_weights_thresholds_and_missing_components() -> None:
    frozen = load_summary()["frozen_regime"]
    config = MarketRegimeConfig()
    assert frozen["version"] == MARKET_REGIME_VERSION
    assert frozen["config_hash"] == config.config_hash()
    assert frozen["weights"] == config.snapshot()["weights"]
    assert frozen["classification"] == config.snapshot()["classification"]
    assert frozen["unavailable_historical_components"] == ["GLOBAL_GIFT", "INDIA_VIX", "INTRADAY_CONFIRMATION"]
    assert frozen["rule_changed"] is False
    assert frozen["weight_changed"] is False
    assert frozen["threshold_changed"] is False


def test_frozen_normal_and_separate_research_populations() -> None:
    integrity = load_summary()["population_integrity"]
    assert integrity == {
        "normal_source_opportunities": 3296,
        "admitted_trades": 728,
        "skipped_opportunities": 2568,
        "slot_skipped_opportunities": 2398,
        "bullish_source": 3253,
        "neutral_source": 43,
        "bullish_admitted": 690,
        "neutral_admitted": 38,
        "bearish_exceptional_review_rows": 324,
        "bearish_exceptional_valid_path_rows": 190,
        "unavailable_preview_rows": 28,
        "unchanged": True,
        "ranking_changed": False,
        "portfolio_rerun_performed": False,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("-60"), "LE_NEG_60"),
        (Decimal("-59.9"), "NEG_59_TO_NEG_30"),
        (Decimal("-30"), "NEG_59_TO_NEG_30"),
        (Decimal("-29.9"), "NEG_29_TO_NEG_10"),
        (Decimal("-10"), "NEG_29_TO_NEG_10"),
        (Decimal("-9.9"), "NEG_9_TO_POS_9"),
        (Decimal("9.9"), "NEG_9_TO_POS_9"),
        (Decimal("10"), "POS_10_TO_29"),
        (Decimal("30"), "POS_30_TO_49"),
        (Decimal("50"), "POS_50_TO_69"),
        (Decimal("70"), "GE_POS_70"),
    ],
)
def test_regime_score_bucket_boundaries(value: Decimal, expected: str) -> None:
    assert bucket_for(value, REGIME_SCORE_BUCKETS) == expected


def test_bullish_and_neutral_boundaries_are_exact() -> None:
    assert bucket_for(Decimal("30"), BULLISH_STRENGTH_BUCKETS) == "BULLISH_LOW"
    assert bucket_for(Decimal("45"), BULLISH_STRENGTH_BUCKETS) == "BULLISH_MEDIUM"
    assert bucket_for(Decimal("60"), BULLISH_STRENGTH_BUCKETS) == "BULLISH_STRONG"
    assert bucket_for(Decimal("75"), BULLISH_STRENGTH_BUCKETS) == "BULLISH_VERY_STRONG"
    assert bucket_for(Decimal("-29"), NEUTRAL_POSITION_BUCKETS) == "NEGATIVE_NEUTRAL"
    assert bucket_for(Decimal("-10"), NEUTRAL_POSITION_BUCKETS) == "NEGATIVE_NEUTRAL"
    assert bucket_for(Decimal("0"), NEUTRAL_POSITION_BUCKETS) == "MID_NEUTRAL"
    assert bucket_for(Decimal("10"), NEUTRAL_POSITION_BUCKETS) == "POSITIVE_NEUTRAL"


def test_component_bucket_boundaries_are_locked() -> None:
    assert bucket_for(Decimal("-20"), TREND_BUCKETS) == "LE_NEG_20"
    assert bucket_for(Decimal("20"), TREND_BUCKETS) == "GE_POS_20"
    assert bucket_for(Decimal("-12"), BREADTH_BUCKETS) == "LE_NEG_12"
    assert bucket_for(Decimal("12"), BREADTH_BUCKETS) == "GE_POS_12"
    assert bucket_for(Decimal("-9"), SECTOR_BUCKETS) == "LE_NEG_9"
    assert bucket_for(Decimal("9"), SECTOR_BUCKETS) == "GE_POS_9"


def test_other_fixed_bucket_boundaries_are_locked() -> None:
    assert bucket_for(Decimal("1.5"), RR_BUCKETS) == "RR_1_5_TO_LT_2"
    assert bucket_for(Decimal("2"), RR_BUCKETS) == "RR_2_TO_LT_2_5"
    assert bucket_for(Decimal("2.5"), RR_BUCKETS) == "RR_GE_2_5"
    assert bucket_for(Decimal("0"), GAP_BUCKETS) == "GAP_LE_ZERO"
    assert bucket_for(Decimal("0.5"), GAP_BUCKETS) == "GAP_POS_TO_0_5"
    assert bucket_for(Decimal("0.5001"), GAP_BUCKETS) == "GAP_GT_0_5"
    assert bucket_for(Decimal("1"), STREAK_BUCKETS) == "STREAK_1"
    assert bucket_for(Decimal("21"), STREAK_BUCKETS) == "STREAK_GT_20"
    assert all(in_bucket(Decimal(value), bucket) for value, bucket in (("30", BORDERLINE_BUCKETS[0]), ("25", BORDERLINE_BUCKETS[1]), ("-25", BORDERLINE_BUCKETS[2]), ("-30", BORDERLINE_BUCKETS[3])))


@pytest.mark.parametrize(
    ("experiment_id", "buckets"),
    [
        ("EXP-REGIME-002", REGIME_SCORE_BUCKETS),
        ("EXP-REGIME-003", BULLISH_STRENGTH_BUCKETS),
        ("EXP-REGIME-004", NEUTRAL_POSITION_BUCKETS),
        ("EXP-REGIME-005", TREND_BUCKETS),
        ("EXP-REGIME-006", BREADTH_BUCKETS),
        ("EXP-REGIME-007", SECTOR_BUCKETS),
    ],
)
def test_bucket_reports_preserve_every_preregistered_bucket_and_population(experiment_id, buckets) -> None:
    rows = load_summary()["tables"][experiment_id]
    assert {row["bucket"] for row in rows} == {item[0] for item in buckets}
    assert {row["population"] for row in rows} == {"SOURCE", "ADMITTED", "SLOT_SKIPPED"}
    assert all({"sample_size", "mean_mfe_r", "mean_mae_r", "mean_realized_r", "target_rate_pct", "stop_rate_pct", "time_rate_pct"} <= set(row) for row in rows)


def test_score_regime_matrix_and_fixed_comparison_cohorts() -> None:
    rows = load_summary()["tables"]["EXP-REGIME-008"]
    matrix = [row for row in rows if row["section"] == "SCORE_X_REGIME_CONTEXT"]
    cohorts = [row for row in rows if row["section"] == "FIXED_DIAGNOSTIC_COHORT"]
    assert len(matrix) == 42
    assert {row["raw_strategy_score"] for row in matrix} == {80, 81, 82, 83, 84, 85}
    assert len(cohorts) == 4
    assert {row["cohort"] for row in cohorts} == {"HIGH_SCORE_WEAK_CONTEXT", "HIGH_SCORE_STRONGER_CONTEXT", "LOWER_SCORE_STRONG_CONTEXT", "LOWER_SCORE_BULLISH_LOW_CONTEXT"}


def test_setup_rr_candidate_and_gap_interactions_are_all_present() -> None:
    rows = load_summary()["tables"]["EXP-REGIME-009"]
    assert sum(row["section"] == "REGIME_X_SETUP" for row in rows) == 14
    assert sum(row["section"] == "REGIME_X_EFFECTIVE_RR" for row in rows) == 21
    assert sum(row["section"] == "REGIME_X_GAP" for row in rows) == 21
    assert sum(row["section"] == "REGIME_X_CANDIDATE_STAGE" for row in rows) == 6


def test_yearly_profiles_cover_requested_years_and_distributions() -> None:
    rows = load_summary()["tables"]["EXP-REGIME-010"]
    overviews = [row for row in rows if row["section"] == "YEAR_OVERVIEW"]
    assert [row["year"] for row in overviews] == [2022, 2023, 2024, 2025, 2026]
    assert all(row["period_status"] == ("PARTIAL" if row["year"] == 2026 else "COMPLETE") for row in rows)
    assert {row["section"] for row in rows} == {"YEAR_OVERVIEW", "YEAR_REGIME_STATE", "YEAR_BULLISH_STRENGTH", "YEAR_NEUTRAL_POSITION", "YEAR_TREND_BUCKET", "YEAR_BREADTH_BUCKET", "YEAR_SECTOR_BUCKET"}


def test_confidence_borderline_flip_and_persistence_are_diagnostic_only() -> None:
    auxiliary = load_summary()["auxiliary_analyses"]
    assert len(auxiliary["confidence_profiles"]) == 9
    assert len(auxiliary["borderline_profiles"]) == 4
    assert len(auxiliary["flip_proximity_profiles"]) == 3
    assert auxiliary["future_flip_used_as_diagnostic_label_only"] is True
    assert auxiliary["future_flip_used_for_admission"] is False
    assert len(auxiliary["persistence_profiles"]) == 16


def test_correlations_are_descriptive_and_classifications_are_allowed() -> None:
    summary = load_summary()
    correlations = summary["correlations"]
    assert all(row["descriptive_only"] and row["significance_tested"] is False for row in correlations)
    assert {row["measure"] for row in correlations} == {"TOTAL_REGIME_SCORE", "NIFTY_TREND", "BREADTH", "SECTOR_PARTICIPATION"}
    assert summary["classifications"]["NIFTY_TREND_RESULT"] in {"CLEAR_POSITIVE_DISCRIMINATION", "WEAK_POSITIVE_DISCRIMINATION", "NO_CLEAR_DISCRIMINATION", "MIXED", "INVERSE", "INCONCLUSIVE"}
    assert summary["classifications"]["TOTAL_REGIME_DISCRIMINATION_RESULT"] in {"CLEAR_POSITIVE_DISCRIMINATION", "WEAK_POSITIVE_DISCRIMINATION", "PARTIALLY_DISCRIMINATIVE", "MIXED", "NO_CLEAR_DISCRIMINATION", "INCONCLUSIVE"}


def test_no_regime_or_portfolio_rule_change_promotion_or_model() -> None:
    summary = load_summary()
    assert summary["promotion_allowed"] is False
    assert summary["experiments_promoted"] == 0
    assert summary["regime_threshold_changed"] is False
    assert summary["regime_weight_changed"] is False
    assert summary["neutral_exclusion_applied"] is False
    assert summary["hysteresis_or_smoothing_added"] is False
    assert summary["optimizer_or_ml_run"] is False
    assert summary["portfolio_variant_run"] is False
    assert summary["future_regime_used_for_admission"] is False


def test_sample_warning_boundaries() -> None:
    assert sample_size_flag(0) == "VERY_SMALL"
    assert sample_size_flag(29) == "VERY_SMALL"
    assert sample_size_flag(30) == "SMALL"
    assert sample_size_flag(99) == "SMALL"
    assert sample_size_flag(100) == "LIMITED"
    assert sample_size_flag(299) == "LIMITED"
    assert sample_size_flag(300) == "ADEQUATE_FOR_DESCRIPTION"


def test_pilot_uses_real_rows_and_validates_every_required_field() -> None:
    pilot = load_summary()["pilot"]
    assert pilot["case_count"] == 14
    assert pilot["real_case_count"] + pilot["not_available_count"] == 14
    assert pilot["passed"] is True
    assert all(row["passed"] for row in pilot["cases"])
    assert all(row["source_type"] in {"REAL_FROZEN_DATA", "NOT_AVAILABLE"} for row in pilot["cases"])


def test_full_summary_registry_reproducibility_and_readiness() -> None:
    summary = load_summary()
    assert summary["newly_registered_experiment_ids"] == list(REGIME_CONTEXT_EXPERIMENT_IDS)
    assert summary["newly_registered_experiment_count"] == 10
    assert summary["registry_preservation"] == {"previous_experiment_count": 39, "previous_parameter_and_preregistration_hashes_unchanged": True, "combined_registry_count": 49}
    assert summary["all_experiments_reproducible"] is True
    assert summary["baseline_mutation_violations"] == 0
    assert summary["failed_experiment_count"] == 0
    assert summary["classifications"]["FRAMEWORK_RESULT"] == "CLEAN"
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True


def test_registry_has_49_complete_records_and_frozen_hashes_remain_valid() -> None:
    registry = json.loads((DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json").read_text(encoding="utf-8"))
    command_rows = [row for row in registry["experiments"] if row["experiment_id"] in REGIME_CONTEXT_EXPERIMENT_IDS]
    assert len(registry["experiments"]) == 49
    assert len(command_rows) == 10
    assert all(row["status"] == "COMPLETE" and row["parameter_hash"] and row["pre_registration_hash"] for row in registry["experiments"])
    hashes = portfolio_backtest_regression_hashes(DATA_DIR)
    assert all(portfolio_backtest_regression_hash_checks(hashes).values())


def test_all_required_reports_and_isolated_runs_exist() -> None:
    filenames = (
        "strategy_diagnostic_v1_regime_context_summary.json",
        "strategy_diagnostic_v1_regime_context_profile.csv",
        "strategy_diagnostic_v1_regime_context_score_buckets.csv",
        "strategy_diagnostic_v1_regime_context_bullish.csv",
        "strategy_diagnostic_v1_regime_context_neutral.csv",
        "strategy_diagnostic_v1_regime_context_trend.csv",
        "strategy_diagnostic_v1_regime_context_breadth.csv",
        "strategy_diagnostic_v1_regime_context_sector.csv",
        "strategy_diagnostic_v1_regime_context_score_interaction.csv",
        "strategy_diagnostic_v1_regime_context_setup_rr.csv",
        "strategy_diagnostic_v1_regime_context_yearly.csv",
        "strategy_diagnostic_v1_regime_context_confidence.csv",
        "strategy_diagnostic_v1_regime_context_borderline.csv",
        "strategy_diagnostic_v1_regime_context_persistence.csv",
        "strategy_diagnostic_v1_regime_context_pilot.csv",
    )
    assert all((DATA_DIR / "reports" / filename).exists() for filename in filenames)
    root = DATA_DIR / "research/diagnostics/strategy/v1/regime_context_command_05"
    assert (root / "registry/regime_context_experiment_registry_v1_preregistered.json").exists()
    assert (root / "registry/regime_context_experiment_registry_v1.json").exists()
    assert all((root / "runs" / item / "result.json").exists() for item in REGIME_CONTEXT_EXPERIMENT_IDS)


def test_source_contains_no_predictive_model_or_threshold_search() -> None:
    source = (REPO_ROOT / "backend/app/diagnostics/regime_context_diagnostic.py").read_text(encoding="utf-8").lower()
    assert "sklearn" not in source
    assert "statsmodels" not in source
    assert "def optimize" not in source
    assert "logisticregression" not in source
    assert "randomforest" not in source
    assert "xgboost" not in source
    assert "isotonicregression" not in source
