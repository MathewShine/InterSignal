from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.portfolio_baseline import (
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
    CURRENT_PORTFOLIO_BACKTEST_PROFILE,
    CURRENT_PORTFOLIO_BACKTEST_VERSION,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.diagnostics.strategy_diagnostic import (
    AUTHORIZED_EXPERIMENT_IDS,
    EXPERIMENT_FAMILIES,
    PROMOTION_ALLOWED,
    RESEARCH_HYPOTHESES,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
    ExperimentDefinition,
    ExperimentExecution,
    ExperimentRegistry,
    baseline_reproduction_check,
    build_experiment_definitions,
    gap_group,
    pairwise_jaccard,
    rank_diagnostic_opportunities,
    robustness_summary,
    simulate_diagnostic_portfolio,
    source_key,
    yearly_summary,
)
from app.backtesting.portfolio_engine import load_frozen_opportunities
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_summary.json"


def test_framework_identity_and_exact_finite_registry() -> None:
    definitions = build_experiment_definitions("2026-01-01T00:00:00+00:00")
    assert STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION == "STRATEGY_DIAGNOSTIC_FRAMEWORK_V1"
    assert STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE == "SWING_STRATEGY_DIAGNOSTICS_V1"
    assert tuple(item.experiment_id for item in definitions) == AUTHORIZED_EXPERIMENT_IDS
    assert len(definitions) == 12
    assert tuple(RESEARCH_HYPOTHESES) == tuple(f"H{index}" for index in range(1, 10))
    assert {item.family for item in definitions} <= set(EXPERIMENT_FAMILIES)
    assert all(item.pre_registered and item.parameters_locked_before_run for item in definitions)
    assert all(item.diagnostic_only and not item.eligible_for_promotion for item in definitions)
    assert PROMOTION_ALLOWED is False


def test_pre_registration_hash_covers_parameters_and_baseline_hashes() -> None:
    definition = build_experiment_definitions("2026-01-01T00:00:00+00:00")[0]
    baseline = {"portfolio_trades_v1": "abc"}
    changed_parameters = replace(
        definition,
        parameters=(("ranking", "BASELINE_RANK"), ("max_hold_sessions", 6)),
    )
    assert definition.pre_registration_hash(baseline) != changed_parameters.pre_registration_hash(baseline)
    assert definition.pre_registration_hash(baseline) != definition.pre_registration_hash(
        {"portfolio_trades_v1": "changed"}
    )


def test_completed_experiment_is_immutable_and_failure_is_not_complete() -> None:
    definition = build_experiment_definitions("2026-01-01T00:00:00+00:00")[0]
    registry = ExperimentRegistry({"frozen": "hash"})
    registry.register(definition)
    registry.mark_ready(definition.experiment_id)
    execution = registry.run(
        definition.experiment_id,
        lambda _: ExperimentExecution(result={"experiment_id": definition.experiment_id}),
        hash_reader=lambda: {"frozen": "hash"},
    )
    assert execution is not None
    assert registry.state(definition.experiment_id).status == "COMPLETE"
    with pytest.raises(ValueError, match="immutable"):
        registry.register(replace(definition, parameters=(("ranking", "SCORE_ONLY"),)))

    failed = build_experiment_definitions("2026-01-01T00:00:00+00:00")[1]
    failure_registry = ExperimentRegistry({"frozen": "hash"})
    failure_registry.register(failed)
    failure_registry.mark_ready(failed.experiment_id)
    result = failure_registry.run(
        failed.experiment_id,
        lambda _: (_ for _ in ()).throw(RuntimeError("controlled failure")),
        hash_reader=lambda: {"frozen": "hash"},
    )
    assert result is None
    assert failure_registry.state(failed.experiment_id).status == "FAILED"
    assert "controlled failure" in str(failure_registry.state(failed.experiment_id).failure_reason)


def test_unauthorized_experiment_cannot_enter_command_01_registry() -> None:
    definition = replace(
        build_experiment_definitions("2026-01-01T00:00:00+00:00")[0],
        experiment_id="EXP-UNAUTHORIZED-001",
    )
    with pytest.raises(ValueError, match="Unauthorized"):
        ExperimentRegistry({"frozen": "hash"}).register(definition)


def test_ranking_adapters_are_exact_and_neutral() -> None:
    rows = [
        opportunity("ZZZ", score="85", rr="2", setup="VALID"),
        opportunity("BBB", score="84", rr="3", setup="STRONG"),
        opportunity("AAA", score="85", rr="2", setup="VALID"),
    ]
    assert [row["symbol"] for row in rank_diagnostic_opportunities(rows, "BASELINE_RANK")] == [
        "AAA", "ZZZ", "BBB"
    ]
    assert [row["symbol"] for row in rank_diagnostic_opportunities(rows, "SCORE_ONLY")] == [
        "AAA", "ZZZ", "BBB"
    ]
    assert [row["symbol"] for row in rank_diagnostic_opportunities(rows, "RR_FIRST")] == [
        "BBB", "AAA", "ZZZ"
    ]
    assert [row["symbol"] for row in rank_diagnostic_opportunities(rows, "SETUP_FIRST")] == [
        "BBB", "AAA", "ZZZ"
    ]


def test_extended_horizon_runs_chronologically_and_changes_later_admission() -> None:
    dates = [
        "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15",
    ]
    rows = [diagnostic_opportunity(f"S{index}", dates[0], dates[:6]) for index in range(4)]
    rows.append(diagnostic_opportunity("LATER", dates[4], dates[4:10], decision_date="2024-01-05"))
    four = simulate_diagnostic_portfolio(
        opportunities=rows,
        trading_dates=dates,
        ranking="BASELINE_RANK",
        horizon=4,
    )
    six = simulate_diagnostic_portfolio(
        opportunities=rows,
        trading_dates=dates,
        ranking="BASELINE_RANK",
        horizon=6,
    )
    assert "2024-01-05|LATER" in {row["source_key"] for row in four["trades"]}
    assert "2024-01-05|LATER" not in {row["source_key"] for row in six["trades"]}
    assert any(row["skip_reason"] == "SKIP_MAX_POSITIONS" for row in six["skipped"])


def test_gap_cohort_segmentation_has_exact_boundaries_and_frozen_counts() -> None:
    assert gap_group({"gap_from_t_close_pct": "-0.01"}) == "GAP_LE_ZERO"
    assert gap_group({"gap_from_t_close_pct": "0"}) == "GAP_LE_ZERO"
    assert gap_group({"gap_from_t_close_pct": "0.5"}) == "GAP_GT_ZERO_LE_0_5"
    assert gap_group({"gap_from_t_close_pct": "0.5001"}) == "GAP_GT_0_5"
    rows, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(DATA_DIR))
    counts: dict[str, int] = {}
    for row in rows:
        counts[gap_group(row)] = counts.get(gap_group(row), 0) + 1
    assert counts == {"GAP_LE_ZERO": 995, "GAP_GT_ZERO_LE_0_5": 1119, "GAP_GT_0_5": 1182}


def test_pairwise_jaccard_and_yearly_robustness_are_deterministic() -> None:
    executions = {
        "A": ExperimentExecution(result={}, trades=[{"source_key": "1"}, {"source_key": "2"}]),
        "B": ExperimentExecution(result={}, trades=[{"source_key": "2"}, {"source_key": "3"}]),
    }
    matrix = pairwise_jaccard(executions)
    assert matrix["A"]["A"] == Decimal("1")
    assert matrix["A"]["B"] == Decimal("1") / Decimal("3")
    daily = [
        {"date": "2022-01-03", "opening_portfolio_equity": "100", "portfolio_equity": "100"},
        {"date": "2022-12-30", "opening_portfolio_equity": "100", "portfolio_equity": "110"},
        {"date": "2023-01-02", "opening_portfolio_equity": "110", "portfolio_equity": "105"},
        {"date": "2023-12-29", "opening_portfolio_equity": "105", "portfolio_equity": "90"},
    ]
    yearly = yearly_summary(daily)
    robust = robustness_summary(yearly)
    assert [row["year"] for row in yearly] == [2022, 2023]
    assert robust["positive_years"] == 1
    assert robust["negative_years"] == 1
    assert robust["best_year"] == 2022
    assert robust["worst_year"] == 2023


def test_frozen_baseline_hashes_are_unchanged_and_reproduction_is_exact() -> None:
    before = portfolio_backtest_regression_hashes(DATA_DIR)
    baseline = verify_current_portfolio_backtest_baseline(DATA_DIR)
    after = portfolio_backtest_regression_hashes(DATA_DIR)
    assert baseline.version == CURRENT_PORTFOLIO_BACKTEST_VERSION
    assert baseline.profile == CURRENT_PORTFOLIO_BACKTEST_PROFILE
    assert baseline.config_hash == CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH
    assert before == after
    assert all(portfolio_backtest_regression_hash_checks(after).values())
    report = diagnostic_summary()
    assert baseline_reproduction_check(report["results"][0])["passed"] is True
    assert report["baseline_mutation_violations"] == 0
    assert all(row["baseline_hashes_unchanged"] is True for row in report["results"])


def test_generated_suite_is_reproducible_non_promotable_and_complete() -> None:
    report = diagnostic_summary()
    assert report["registered_experiment_ids"] == list(AUTHORIZED_EXPERIMENT_IDS)
    assert report["registered_experiment_count"] == 12
    assert report["pilot"]["passed"] is True
    assert report["reproducibility"]["same_registered_experiment_canonical_outputs_match"] is True
    assert report["failed_experiment_count"] == 0
    assert report["promotion_allowed"] is False
    assert report["experiments_promoted"] == 0
    assert report["winner_selected"] is False
    assert report["optimizer_or_parameter_search_run"] is False
    assert report["tests_passed"] is True
    assert report["frontend_build_passed"] is True
    assert report["classifications"]["FRAMEWORK_RESULT"] == "CLEAN"
    assert report["ready_for_review"] is True


def test_machine_reports_registry_and_isolated_runs_exist() -> None:
    expected_reports = (
        "strategy_diagnostic_v1_summary.json",
        "strategy_diagnostic_v1_registry.csv",
        "strategy_diagnostic_v1_ranking.csv",
        "strategy_diagnostic_v1_hold_horizon.csv",
        "strategy_diagnostic_v1_gap_cohorts.csv",
        "strategy_diagnostic_v1_baseline_reproduction.csv",
    )
    assert all((DATA_DIR / "reports" / name).exists() for name in expected_reports)
    root = DATA_DIR / "research/diagnostics/strategy/v1"
    assert (root / "registry/experiment_registry_v1_preregistered.json").exists()
    assert (root / "registry/experiment_registry_v1.json").exists()
    assert (root / "summaries/experiment_results_v1.csv").exists()
    assert all((root / f"runs/{experiment_id}/result.json").exists() for experiment_id in AUTHORIZED_EXPERIMENT_IDS)


def test_no_winner_selector_or_optimizer_is_implemented() -> None:
    source = (REPO_ROOT / "backend/app/diagnostics/strategy_diagnostic.py").read_text(encoding="utf-8")
    assert "def select_best" not in source
    assert "def choose_winner" not in source
    assert "def optimize" not in source
    assert "for threshold in" not in source
    assert "for max_positions in" not in source
    assert "for risk in" not in source


def diagnostic_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def opportunity(symbol: str, *, score: str, rr: str, setup: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "raw_strategy_score": score,
        "effective_reward_risk": rr,
        "setup_quality": setup,
        "momentum_points": "10",
        "rvol_points": "10",
        "relative_strength_points": "10",
        "position_notional": "10000",
    }


def diagnostic_opportunity(
    symbol: str,
    entry_date: str,
    dates: list[str],
    *,
    decision_date: str = "2024-01-01",
) -> dict[str, object]:
    return {
        "decision_date": decision_date,
        "next_session_date": entry_date,
        "symbol": symbol,
        "hypothetical_entry_price": "100",
        "stop_price": "90",
        "target_price": "200",
        "raw_strategy_score": "85",
        "effective_reward_risk": "10",
        "setup_quality": "STRONG",
        "momentum_points": "20",
        "rvol_points": "15",
        "relative_strength_points": "15",
        "position_notional": "10000",
        "_diagnostic_bars": {
            trading_date: {
                "index": index,
                "date": trading_date,
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
            }
            for index, trading_date in enumerate(dates, start=1)
        },
    }
