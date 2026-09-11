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
from app.diagnostics.entry_quality_diagnostic import (
    ATR_EXTENSION_BUCKETS,
    BREAKOUT_DISTANCE_BUCKETS,
    ENTRY_QUALITY_COMMAND_VERSION,
    ENTRY_QUALITY_EXPERIMENT_IDS,
    GAP_BUCKETS,
    MATURITY_CLASSES,
    MOMENTUM_BUCKETS,
    PRIOR_MOVE_BUCKETS,
    EntryQualityRegistry,
    atr_extension_bucket,
    breakout_distance_bucket,
    build_entry_quality_definitions,
    calculate_entry_quality_pre_registration_hash,
    calculate_extension,
    gap_bucket,
    maturity_class,
    momentum_bucket,
    prior_move_bucket,
    select_structural_reference,
)
from app.diagnostics.exit_stop_path_diagnostic import EXIT_EXPERIMENT_IDS
from app.diagnostics.strategy_diagnostic import AUTHORIZED_EXPERIMENT_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_entry_quality_summary.json"


def test_exact_command_03_allowlist_and_preregistration_policy() -> None:
    definitions = build_entry_quality_definitions("2026-01-01T00:00:00+00:00")
    assert ENTRY_QUALITY_COMMAND_VERSION == "STRATEGY_DIAGNOSTIC_ENTRY_QUALITY_V1"
    assert tuple(row.experiment_id for row in definitions) == ENTRY_QUALITY_EXPERIMENT_IDS
    assert len(definitions) == 10
    assert {row.family for row in definitions} == {"ENTRY_QUALITY_DIAGNOSTIC"}
    assert all(row.pre_registered and row.parameters_locked_before_run for row in definitions)
    assert all(row.diagnostic_only and not row.eligible_for_promotion for row in definitions)


def test_entry_quality_registry_rejects_any_extra_experiment() -> None:
    definition = build_entry_quality_definitions("2026-01-01T00:00:00+00:00")[0]
    with pytest.raises(ValueError, match="Unauthorized"):
        EntryQualityRegistry({"frozen": "hash"}).register(
            replace(definition, experiment_id="EXP-ENTRYQ-011")
        )


def test_preregistration_hash_covers_parameters_and_frozen_hashes() -> None:
    definition = build_entry_quality_definitions("2026-01-01T00:00:00+00:00")[1]
    changed = replace(definition, parameters=definition.parameters + (("changed", True),))
    baseline = {"feature": "abc"}
    assert calculate_entry_quality_pre_registration_hash(definition, baseline)
    assert calculate_entry_quality_pre_registration_hash(definition, baseline) != calculate_entry_quality_pre_registration_hash(changed, baseline)
    assert calculate_entry_quality_pre_registration_hash(definition, baseline) != calculate_entry_quality_pre_registration_hash(definition, {"feature": "changed"})


def test_structural_reference_hierarchy_uses_causal_priority() -> None:
    setup = {"prior_high_20d": "100"}
    risk = {"technical_invalidation_level": "90", "entry_reference_price": "105"}
    assert select_structural_reference(setup, risk) == (
        Decimal("100"),
        "SETUP_PRIOR_HIGH_20D_BREAKOUT_OR_RECLAIM_REFERENCE",
    )
    assert select_structural_reference({}, risk) == (
        Decimal("90"),
        "RISK_V1_1_TECHNICAL_INVALIDATION_ANCHOR",
    )
    assert select_structural_reference({}, {"entry_reference_price": "105"}) == (
        Decimal("105"),
        "RISK_V1_1_ENTRY_REFERENCE_PRICE",
    )
    assert select_structural_reference({}, {}) == (None, "UNAVAILABLE")


def test_extension_percent_and_atr_math_and_unavailable_handling() -> None:
    pct, atr = calculate_extension(Decimal("110"), Decimal("100"), Decimal("5"))
    assert pct == Decimal("10")
    assert atr == Decimal("2")
    assert calculate_extension(Decimal("110"), None, Decimal("5")) == (None, None)
    assert calculate_extension(Decimal("110"), Decimal("100"), None) == (Decimal("10"), None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "UNAVAILABLE"),
        (Decimal("0.4999"), "LT_0_5_ATR"),
        (Decimal("0.5"), "0_5_TO_LT_1_ATR"),
        (Decimal("1"), "1_TO_LT_1_5_ATR"),
        (Decimal("1.5"), "1_5_TO_LT_2_ATR"),
        (Decimal("2"), "2_TO_3_ATR"),
        (Decimal("3"), "2_TO_3_ATR"),
        (Decimal("3.0001"), "GT_3_ATR"),
    ],
)
def test_atr_bucket_boundaries(value: Decimal | None, expected: str) -> None:
    assert atr_extension_bucket(value) == expected
    assert expected in ATR_EXTENSION_BUCKETS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "UNAVAILABLE"),
        (Decimal("1"), "LE_1_PCT"),
        (Decimal("2"), "GT_1_TO_2_PCT"),
        (Decimal("3"), "GT_2_TO_3_PCT"),
        (Decimal("5"), "GT_3_TO_5_PCT"),
        (Decimal("8"), "GT_5_TO_8_PCT"),
        (Decimal("8.01"), "GT_8_PCT"),
    ],
)
def test_breakout_distance_boundaries(value: Decimal | None, expected: str) -> None:
    assert breakout_distance_bucket(value) == expected
    assert expected in BREAKOUT_DISTANCE_BUCKETS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "UNAVAILABLE"),
        (Decimal("0"), "LE_0_PCT"),
        (Decimal("2"), "GT_0_TO_2_PCT"),
        (Decimal("4"), "GT_2_TO_4_PCT"),
        (Decimal("6"), "GT_4_TO_6_PCT"),
        (Decimal("8"), "GT_6_TO_8_PCT"),
        (Decimal("8.01"), "GT_8_PCT"),
    ],
)
def test_prior_day_move_boundaries(value: Decimal | None, expected: str) -> None:
    assert prior_move_bucket(value) == expected
    assert expected in PRIOR_MOVE_BUCKETS


def test_momentum_bucket_boundaries_are_fixed_for_all_horizons() -> None:
    assert momentum_bucket("return_5d_pct", Decimal("3")) == "3_TO_LT_6_PCT"
    assert momentum_bucket("return_5d_pct", Decimal("15")) == "10_TO_15_PCT"
    assert momentum_bucket("return_5d_pct", Decimal("15.01")) == "GT_15_PCT"
    assert momentum_bucket("return_10d_pct", Decimal("25")) == "15_TO_25_PCT"
    assert momentum_bucket("return_20d_pct", Decimal("50")) == "30_TO_50_PCT"
    assert set(MOMENTUM_BUCKETS) == {"return_5d_pct", "return_10d_pct", "return_20d_pct"}


def test_maturity_mapping_is_outcome_independent_and_exact() -> None:
    assert maturity_class(Decimal("1"), Decimal("2"), Decimal("3")) == "EARLY"
    assert maturity_class(Decimal("5"), Decimal("8"), Decimal("12")) == "DEVELOPING"
    assert maturity_class(Decimal("10"), Decimal("8"), Decimal("12")) == "MATURE"
    assert maturity_class(Decimal("16"), Decimal("8"), Decimal("12")) == "EXTENDED"
    assert maturity_class(None, Decimal("8"), Decimal("12")) == "UNAVAILABLE"
    assert set(MATURITY_CLASSES) == {"EARLY", "DEVELOPING", "MATURE", "EXTENDED", "UNAVAILABLE"}


def test_gap_boundaries_are_fixed() -> None:
    assert gap_bucket(None) == "UNAVAILABLE"
    assert gap_bucket(Decimal("0")) == "LE_0_PCT"
    assert gap_bucket(Decimal("0.5")) == "GT_0_TO_0_5_PCT"
    assert gap_bucket(Decimal("1")) == "GT_0_5_TO_1_PCT"
    assert gap_bucket(Decimal("2")) == "GT_1_TO_2_PCT"
    assert gap_bucket(Decimal("2.01")) == "GT_2_PCT"
    assert set(GAP_BUCKETS) == {"LE_0_PCT", "GT_0_TO_0_5_PCT", "GT_0_5_TO_1_PCT", "GT_1_TO_2_PCT", "GT_2_PCT", "UNAVAILABLE"}


def test_full_summary_has_no_filter_admission_or_baseline_change() -> None:
    summary = load_summary()
    integrity = summary["population_integrity"]
    assert integrity["source_opportunities"] == 3296
    assert integrity["admitted_trades"] == 728
    assert integrity["skipped_opportunities"] == 2568
    assert integrity["unchanged"] is True
    assert integrity["ranking_changed"] is False
    assert integrity["filter_applied"] is False
    assert integrity["portfolio_equity_curve_generated"] is False
    assert summary["entry_filter_applied"] is False


def test_baseline_and_exit_profiles_include_all_available_entry_quality_fields() -> None:
    summary = load_summary()
    source = next(row for row in summary["baseline_profile"] if row["population"] == "SOURCE")
    required_metrics = {
        "median_gap_pct",
        "median_stop_distance_pct",
        "median_stop_distance_atr",
        "median_breakout_distance_pct",
        "median_return_3d_pct",
        "up_days_ratio_5_available_count",
        "median_up_days_ratio_5",
        "up_days_ratio_10_available_count",
        "median_up_days_ratio_10",
        "up_days_ratio_20_available_count",
        "median_up_days_ratio_20",
        "median_relative_volume_20d",
        "median_rs_relative_return_5d_pct",
        "median_rs_relative_return_20d_pct",
        "median_raw_strategy_score",
        "rvol_state_counts",
        "rs_state_counts",
        "setup_quality_counts",
        "candidate_category_counts",
    }
    assert required_metrics <= set(source)
    unavailable_up_day_ratios = {
        "median_up_days_ratio_5",
        "median_up_days_ratio_10",
        "median_up_days_ratio_20",
    }
    assert all(
        source[key] is not None
        for key in required_metrics - unavailable_up_day_ratios
        if not key.endswith("_counts")
    )
    assert all(source[key] is None for key in unavailable_up_day_ratios)
    assert source["up_days_ratio_5_available_count"] == 0
    assert source["up_days_ratio_10_available_count"] == 0
    assert source["up_days_ratio_20_available_count"] == 0
    assert sum(source["rvol_state_counts"].values()) == 3296
    assert sum(source["rs_state_counts"].values()) == 3296
    assert sum(source["setup_quality_counts"].values()) == 3296
    assert sum(source["candidate_category_counts"].values()) == 3296
    for profile in summary["auxiliary_analyses"]["exit_profiles"]:
        assert profile["median_gap_pct"] is not None
        assert profile["median_relative_volume_20d"] is not None
        assert sum(profile["rvol_state_counts"].values()) == profile["source_opportunities"]
        assert sum(profile["rs_state_counts"].values()) == profile["source_opportunities"]


def test_full_summary_registry_reports_and_reproducibility() -> None:
    summary = load_summary()
    assert summary["newly_registered_experiment_ids"] == list(ENTRY_QUALITY_EXPERIMENT_IDS)
    assert summary["newly_registered_experiment_count"] == 10
    assert summary["registry_preservation"]["previous_experiment_count"] == 19
    assert summary["registry_preservation"]["previous_parameter_and_preregistration_hashes_unchanged"] is True
    assert summary["registry_preservation"]["combined_registry_count"] == 29
    assert summary["all_experiments_reproducible"] is True
    assert summary["failed_experiment_count"] == 0
    assert summary["promotion_allowed"] is False
    assert summary["experiments_promoted"] == 0
    assert summary["automatic_selection_performed"] is False
    assert summary["optimizer_or_parameter_search_run"] is False
    assert summary["pilot"]["passed"] is True
    assert summary["pilot"]["real_case_count"] == 14
    assert summary["classifications"]["FRAMEWORK_RESULT"] == "CLEAN"
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True


def test_required_reports_and_isolated_runs_exist() -> None:
    filenames = (
        "strategy_diagnostic_v1_entry_quality_summary.json",
        "strategy_diagnostic_v1_entry_quality_atr.csv",
        "strategy_diagnostic_v1_entry_quality_breakout_distance.csv",
        "strategy_diagnostic_v1_entry_quality_prior_move.csv",
        "strategy_diagnostic_v1_entry_quality_maturity.csv",
        "strategy_diagnostic_v1_entry_quality_gap_prior.csv",
        "strategy_diagnostic_v1_entry_quality_rvol_extension.csv",
        "strategy_diagnostic_v1_entry_quality_rs_extension.csv",
        "strategy_diagnostic_v1_entry_quality_score_extension.csv",
        "strategy_diagnostic_v1_entry_quality_candidate_stage.csv",
        "strategy_diagnostic_v1_entry_quality_correlations.csv",
        "strategy_diagnostic_v1_entry_quality_pilot.csv",
    )
    assert all((DATA_DIR / "reports" / filename).exists() for filename in filenames)
    root = DATA_DIR / "research/diagnostics/strategy/v1/entry_quality_command_03"
    assert (root / "registry/entry_quality_experiment_registry_v1_preregistered.json").exists()
    assert (root / "registry/entry_quality_experiment_registry_v1.json").exists()
    assert all((root / "runs" / item / "result.json").exists() for item in ENTRY_QUALITY_EXPERIMENT_IDS)


def test_previous_19_registry_hashes_and_frozen_data_are_unchanged() -> None:
    registry = json.loads((DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json").read_text(encoding="utf-8"))
    previous_ids = set(AUTHORIZED_EXPERIMENT_IDS) | set(EXIT_EXPERIMENT_IDS)
    previous = [row for row in registry["experiments"] if row["experiment_id"] in previous_ids]
    assert len(previous) == 19
    assert len(registry["experiments"]) >= 29
    assert all(row["status"] == "COMPLETE" for row in previous)
    assert all(row["parameter_hash"] and row["pre_registration_hash"] for row in previous)
    before = portfolio_backtest_regression_hashes(DATA_DIR)
    after = portfolio_backtest_regression_hashes(DATA_DIR)
    assert before == after
    assert all(portfolio_backtest_regression_hash_checks(after).values())
    assert load_summary()["baseline_mutation_violations"] == 0


def test_no_predictive_model_filter_selector_or_optimizer() -> None:
    source = (REPO_ROOT / "backend/app/diagnostics/entry_quality_diagnostic.py").read_text(encoding="utf-8")
    assert "def optimize" not in source
    assert "def select_best" not in source
    assert "def choose_winner" not in source
    assert "sklearn" not in source
    assert "statsmodels" not in source


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
