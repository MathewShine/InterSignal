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
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
)
from app.diagnostics.exit_stop_path_diagnostic import (
    EXIT_COMMAND_VERSION,
    EXIT_EXPERIMENT_IDS,
    FIXED_TARGET_EXPERIMENT_IDS,
    PROTECTED_STOP_EXIT,
    PROTECTED_STOP_GAP_EXIT,
    PROTECTION_EXPERIMENT_IDS,
    ExitExperimentRegistry,
    ExitRule,
    baseline_exit_reproduction_check,
    build_exit_experiment_definitions,
    calculate_exit_pre_registration_hash,
    distribution,
    percentile,
    resolve_exit_for_bar,
    simulate_exit_portfolio,
)
from app.diagnostics.strategy_diagnostic import AUTHORIZED_EXPERIMENT_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/strategy_diagnostic_v1_exit_summary.json"


def test_command_02_has_exact_preregistered_allowlist_and_policy() -> None:
    definitions = build_exit_experiment_definitions("2026-01-01T00:00:00+00:00")
    assert EXIT_COMMAND_VERSION == "STRATEGY_DIAGNOSTIC_EXIT_STOP_PATH_V1"
    assert tuple(row.experiment_id for row in definitions) == EXIT_EXPERIMENT_IDS
    assert len(definitions) == 7
    assert {row.family for row in definitions} == {"EXIT_DIAGNOSTIC"}
    assert all(row.pre_registered and row.parameters_locked_before_run for row in definitions)
    assert all(row.diagnostic_only and not row.eligible_for_promotion for row in definitions)


def test_exit_registry_rejects_unregistered_and_combined_experiments() -> None:
    definition = build_exit_experiment_definitions("2026-01-01T00:00:00+00:00")[0]
    registry = ExitExperimentRegistry({"frozen": "hash"})
    with pytest.raises(ValueError, match="Unauthorized"):
        registry.register(replace(definition, experiment_id="EXP-EXIT-999"))
    with pytest.raises(ValueError, match="cannot be combined"):
        ExitRule("PROTECTION", Decimal("0.5"), Decimal("1")).validate()
    with pytest.raises(ValueError, match="cannot be combined"):
        ExitRule("FIXED_TARGET", Decimal("0.5"), Decimal("1")).validate()


def test_exit_preregistration_hash_covers_parameters_baseline_and_thresholds() -> None:
    definition = build_exit_experiment_definitions("2026-01-01T00:00:00+00:00")[1]
    base = {"portfolio_trades_v1": "abc"}
    changed = replace(definition, parameters=definition.parameters + (("extra", "changed"),))
    assert calculate_exit_pre_registration_hash(definition, base)
    assert calculate_exit_pre_registration_hash(definition, base) != calculate_exit_pre_registration_hash(changed, base)
    assert calculate_exit_pre_registration_hash(definition, base) != calculate_exit_pre_registration_hash(definition, {"portfolio_trades_v1": "changed"})


def test_exit_resolution_is_stop_first_and_protected_gap_is_explicit() -> None:
    ambiguous = resolve_exit_for_bar(
        bar=bar("100", "112", "89", "105"),
        entry_price=Decimal("100"),
        original_stop=Decimal("90"),
        target_price=Decimal("110"),
        protection_active=False,
        sessions_seen=1,
    )
    assert ambiguous == (AMBIGUOUS_SAME_BAR_EXIT, Decimal("90"), True)
    protected = resolve_exit_for_bar(
        bar=bar("101", "105", "99", "102"),
        entry_price=Decimal("100"),
        original_stop=Decimal("90"),
        target_price=Decimal("120"),
        protection_active=True,
        sessions_seen=2,
    )
    assert protected == (PROTECTED_STOP_EXIT, Decimal("100"), False)
    gap = resolve_exit_for_bar(
        bar=bar("98", "103", "97", "101"),
        entry_price=Decimal("100"),
        original_stop=Decimal("90"),
        target_price=Decimal("120"),
        protection_active=True,
        sessions_seen=2,
    )
    assert gap == (PROTECTED_STOP_GAP_EXIT, Decimal("98"), False)


@pytest.mark.parametrize("threshold", [Decimal("0.5"), Decimal("1")])
def test_protection_activates_only_after_completed_prior_session(threshold: Decimal) -> None:
    rows = [
        opportunity(
            "PROTECT",
            highs=(str(100 + threshold * 10), "105", "105", "105"),
            lows=("95", "99", "99", "99"),
            closes=("104", "101", "101", "101"),
            target="130",
        )
    ]
    simulation = simulate_exit_portfolio(
        opportunities=rows,
        trading_dates=DATES,
        rule=ExitRule("PROTECTION", protection_threshold_r=threshold),
    )
    trade = simulation["trades"][0]
    assert trade["protection_activation_date"] == DATES[0]
    assert trade["protection_effective_session"] == 2
    assert trade["exit_date"] == DATES[1]
    assert trade["exit_reason"] == PROTECTED_STOP_EXIT
    assert trade["exit_price"] == Decimal("100")
    assert trade["realized_r_multiple"] == 0


def test_same_session_threshold_and_original_stop_does_not_protect() -> None:
    rows = [
        opportunity(
            "NO-SAME-DAY",
            highs=("106", "105", "105", "105"),
            lows=("89", "95", "95", "95"),
            closes=("100", "100", "100", "100"),
            target="130",
        )
    ]
    simulation = simulate_exit_portfolio(
        opportunities=rows,
        trading_dates=DATES,
        rule=ExitRule("PROTECTION", protection_threshold_r=Decimal("0.5")),
    )
    trade = simulation["trades"][0]
    assert trade["exit_reason"] == STOP_EXIT
    assert trade["exit_price"] == Decimal("90")
    assert trade["protection_activated"] is False


def test_protection_can_activate_then_reach_frozen_target() -> None:
    rows = [
        opportunity(
            "PROTECT-TARGET",
            highs=("106", "121", "121", "121"),
            lows=("95", "101", "101", "101"),
            closes=("104", "120", "120", "120"),
            target="120",
        )
    ]
    trade = simulate_exit_portfolio(
        opportunities=rows,
        trading_dates=DATES,
        rule=ExitRule("PROTECTION", protection_threshold_r=Decimal("0.5")),
    )["trades"][0]
    assert trade["protection_activated"] is True
    assert trade["exit_reason"] == TARGET_EXIT


@pytest.mark.parametrize(
    ("target_r", "target_price"),
    [(Decimal("1"), Decimal("110")), (Decimal("1.5"), Decimal("115")), (Decimal("2"), Decimal("120"))],
)
def test_fixed_targets_use_exact_r_multiple(target_r: Decimal, target_price: Decimal) -> None:
    rows = [
        opportunity(
            f"FIXED-{target_r}",
            highs=(str(target_price), "100", "100", "100"),
            lows=("95", "95", "95", "95"),
            closes=("100", "100", "100", "100"),
            target="150",
        )
    ]
    trade = simulate_exit_portfolio(
        opportunities=rows,
        trading_dates=DATES,
        rule=ExitRule("FIXED_TARGET", fixed_target_r=target_r),
    )["trades"][0]
    assert trade["target_price"] == target_price
    assert trade["exit_price"] == target_price
    assert trade["realized_r_multiple"] == target_r


def test_fixed_target_same_bar_ambiguity_uses_original_stop() -> None:
    rows = [
        opportunity(
            "FIXED-AMBIG",
            highs=("111", "100", "100", "100"),
            lows=("89", "95", "95", "95"),
            closes=("100", "100", "100", "100"),
            target="150",
        )
    ]
    trade = simulate_exit_portfolio(
        opportunities=rows,
        trading_dates=DATES,
        rule=ExitRule("FIXED_TARGET", fixed_target_r=Decimal("1")),
    )["trades"][0]
    assert trade["exit_reason"] == AMBIGUOUS_SAME_BAR_EXIT
    assert trade["exit_price"] == Decimal("90")


def test_chronological_earlier_exit_changes_later_admission() -> None:
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    rows = [
        opportunity(f"S{index}", highs=("111", "100", "100", "100"), lows=("95",) * 4, closes=("100",) * 4, entry_date=dates[0], target="150")
        for index in range(4)
    ]
    rows.append(opportunity("LATER", highs=("100", "111", "100", "100"), lows=("95",) * 4, closes=("100",) * 4, entry_date=dates[1], decision_date="2024-01-02", target="150"))
    baseline = simulate_exit_portfolio(opportunities=rows, trading_dates=dates, rule=ExitRule("BASELINE"))
    fixed = simulate_exit_portfolio(opportunities=rows, trading_dates=dates, rule=ExitRule("FIXED_TARGET", fixed_target_r=Decimal("1")))
    assert "2024-01-02|LATER" not in {row["source_key"] for row in baseline["trades"]}
    assert "2024-01-02|LATER" in {row["source_key"] for row in fixed["trades"]}
    assert any(row["skip_reason"] == "SKIP_MAX_POSITIONS" for row in baseline["skipped"])


def test_giveback_percentiles_are_deterministic() -> None:
    values = [Decimal("0"), Decimal("1"), Decimal("2"), Decimal("3")]
    assert percentile(values, Decimal("0.75")) == Decimal("2.25")
    report = distribution(values)
    assert report["mean"] == Decimal("1.5")
    assert report["median"] == Decimal("1.5")
    assert report["p90"] == Decimal("2.7")


def test_full_exit_report_reproduces_baseline_and_path_counts() -> None:
    summary = load_summary()
    assert baseline_exit_reproduction_check(summary["results"][0])["passed"] is True
    assert summary["path_diagnostic"]["baseline_stop_exit_count"] == 159
    assert summary["path_diagnostic"]["baseline_time_exit_count"] == 542
    assert summary["path_diagnostic"]["same_session_favorable_excursion_counted_for_stops"] is False
    assert summary["baseline_mutation_violations"] == 0


def test_full_exit_report_is_reproducible_non_promotable_and_complete() -> None:
    summary = load_summary()
    assert summary["newly_registered_experiment_ids"] == list(EXIT_EXPERIMENT_IDS)
    assert summary["newly_registered_experiment_count"] == 7
    assert set(PROTECTION_EXPERIMENT_IDS) == {"EXP-EXIT-002", "EXP-EXIT-003"}
    assert set(FIXED_TARGET_EXPERIMENT_IDS) == {"EXP-EXIT-004", "EXP-EXIT-005", "EXP-EXIT-006"}
    assert summary["pre_registration"]["written_before_any_simulation"] is True
    assert summary["all_experiments_reproducible"] is True
    assert summary["failed_experiment_count"] == 0
    assert summary["promotion_allowed"] is False
    assert summary["experiments_promoted"] == 0
    assert summary["automatic_selection_performed"] is False
    assert summary["optimizer_or_parameter_search_run"] is False
    assert summary["pilot"]["passed"] is True
    assert summary["classifications"]["FRAMEWORK_RESULT"] == "CLEAN"
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True


def test_yearly_jaccard_occupancy_and_required_reports_exist() -> None:
    summary = load_summary()
    portfolio_results = summary["results"][:6]
    assert all([row["year"] for row in result["yearly_results"]] == [2022, 2023, 2024, 2025, 2026] for result in portfolio_results)
    assert all(result["comparison_to_baseline"]["trade_set_jaccard"] is not None for result in portfolio_results)
    assert all("days_at_max_capacity" in result for result in portfolio_results)
    required = (
        "strategy_diagnostic_v1_exit_summary.json",
        "strategy_diagnostic_v1_exit_experiments.csv",
        "strategy_diagnostic_v1_exit_yearly.csv",
        "strategy_diagnostic_v1_exit_path.csv",
        "strategy_diagnostic_v1_exit_giveback.csv",
        "strategy_diagnostic_v1_exit_occupancy.csv",
        "strategy_diagnostic_v1_exit_jaccard.csv",
        "strategy_diagnostic_v1_exit_pilot.csv",
    )
    assert all((DATA_DIR / "reports" / name).exists() for name in required)
    root = DATA_DIR / "research/diagnostics/strategy/v1/exit_command_02"
    assert (root / "registry/exit_experiment_registry_v1_preregistered.json").exists()
    assert (root / "registry/exit_experiment_registry_v1.json").exists()
    assert all((root / "runs" / item / "result.json").exists() for item in EXIT_EXPERIMENT_IDS)


def test_command_01_registry_records_and_run_folders_were_not_overwritten() -> None:
    registry = json.loads((DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json").read_text(encoding="utf-8"))
    command_01 = [row for row in registry["experiments"] if row["experiment_id"] in AUTHORIZED_EXPERIMENT_IDS]
    assert len(command_01) == 12
    assert all(row["status"] == "COMPLETE" for row in command_01)
    assert all(row["parameter_hash"] and row["pre_registration_hash"] for row in command_01)
    assert all((DATA_DIR / "research/diagnostics/strategy/v1/runs" / row["experiment_id"] / "result.json").exists() for row in command_01)


def test_frozen_hash_guards_security_and_no_side_effects() -> None:
    before = portfolio_backtest_regression_hashes(DATA_DIR)
    summary = load_summary()
    after = portfolio_backtest_regression_hashes(DATA_DIR)
    assert before == after
    assert all(portfolio_backtest_regression_hash_checks(after).values())
    assert all(result["baseline_hashes_unchanged"] for result in summary["results"])
    assert summary["safety"] == {
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    source = (REPO_ROOT / "backend/app/diagnostics/exit_stop_path_diagnostic.py").read_text(encoding="utf-8")
    assert "def optimize" not in source
    assert "def select_best" not in source
    assert "def choose_winner" not in source


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


DATES = ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05")


def bar(open_price: str, high: str, low: str, close: str) -> dict[str, Decimal]:
    return {
        "open": Decimal(open_price),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
    }


def opportunity(
    symbol: str,
    *,
    highs: tuple[str, str, str, str],
    lows: tuple[str, str, str, str],
    closes: tuple[str, str, str, str],
    target: str,
    entry_date: str = DATES[0],
    decision_date: str = "2024-01-01",
) -> dict[str, object]:
    bars = {
        day: {
            "index": index,
            "date": day,
            "open": Decimal("100"),
            "high": Decimal(highs[index - 1]),
            "low": Decimal(lows[index - 1]),
            "close": Decimal(closes[index - 1]),
        }
        for index, day in enumerate(DATES, start=1)
        if day >= entry_date
    }
    return {
        "symbol": symbol,
        "decision_date": decision_date,
        "next_session_date": entry_date,
        "hypothetical_entry_price": "100",
        "stop_price": "90",
        "target_price": target,
        "raw_strategy_score": "80",
        "effective_reward_risk": "2",
        "setup_quality": "STRONG",
        "momentum_points": "15",
        "rvol_points": "15",
        "relative_strength_points": "15",
        "position_notional": "25000",
        "_diagnostic_bars": bars,
        "_diagnostic_horizon": 4,
    }
