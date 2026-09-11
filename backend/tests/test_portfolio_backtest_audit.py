from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.portfolio_audit import (
    EXPECTED_BACKTEST_CONFIG_HASH,
    EXPECTED_DAILY_HASH,
    EXPECTED_SKIPPED_HASH,
    EXPECTED_TRADES_HASH,
    PORTFOLIO_BACKTEST_AUDIT_VERSION,
    PortfolioBacktestAuditConfig,
    audit_exit,
    audit_rank_rows,
    audit_sizing,
    baseline_hashes,
    calculate_cagr,
    independent_simulation,
    reconstruct_drawdown,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    SKIP_INSUFFICIENT_CASH,
    SKIP_MAX_POSITIONS,
    SKIP_PORTFOLIO_RISK_LIMIT,
    SKIP_SAME_SYMBOL_ALREADY_OPEN,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
)
from app.strategy.outcomes.outcome_baseline import STRATEGY_OUTCOME_V1_DATASET_HASH

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/portfolio_backtest_v1_audit_summary.json"


def audit_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_audit_identity_and_frozen_contract() -> None:
    config = PortfolioBacktestConfig()
    assert PORTFOLIO_BACKTEST_AUDIT_VERSION == "PORTFOLIO_BACKTEST_AUDIT_V1"
    assert config.config_hash() == EXPECTED_BACKTEST_CONFIG_HASH
    assert config.max_concurrent_positions == 4
    assert config.max_risk_per_trade_pct == Decimal("1.00")
    assert config.max_total_open_risk_pct == Decimal("4.00")


def test_baseline_dataset_immutability_hashes() -> None:
    hashes = baseline_hashes(PortfolioBacktestAuditConfig(DATA_DIR))
    assert hashes["portfolio_trades_v1"] == EXPECTED_TRADES_HASH
    assert hashes["portfolio_daily_v1"] == EXPECTED_DAILY_HASH
    assert hashes["portfolio_skipped_v1"] == EXPECTED_SKIPPED_HASH
    assert hashes["outcome_v1"] == STRATEGY_OUTCOME_V1_DATASET_HASH


def test_independent_ranking_reconstructs_all_tie_breaks() -> None:
    rows = [
        opportunity("ZZZ", score="84", rr="2", notional="1000"),
        opportunity("BBB", score="85", rr="2", notional="1000"),
        opportunity("AAA", score="85", rr="2", notional="1000"),
    ]
    assert [row["symbol"] for row in audit_rank_rows(rows)] == ["AAA", "BBB", "ZZZ"]
    assert [row["_audit_selection_rank"] for row in audit_rank_rows(rows)] == [1, 2, 3]
    assert [row["symbol"] for row in audit_rank_rows(rows, "REVERSE_FINAL_TIE_ONLY")][:2] == ["BBB", "AAA"]


def test_ranking_counterfactuals_are_fixed_and_deterministic() -> None:
    rows = [opportunity("A", score="84", rr="2"), opportunity("B", score="83", rr="4")]
    assert [row["symbol"] for row in audit_rank_rows(rows, "SCORE_ONLY")] == ["A", "B"]
    assert [row["symbol"] for row in audit_rank_rows(rows, "RR_FIRST")] == ["B", "A"]
    assert [row["symbol"] for row in audit_rank_rows(rows, "SETUP_FIRST")] == ["A", "B"]
    assert audit_rank_rows(rows) == audit_rank_rows(rows)


def test_future_mfe_mae_and_touch_labels_do_not_change_admission() -> None:
    rows = [opportunity(f"S{index}", score=str(85 - index)) for index in range(5)]
    baseline = independent_simulation(rows, session_dates(), PortfolioBacktestConfig())
    changed = copy.deepcopy(rows)
    changed[0].update(
        {
            "mfe_r_4": "999",
            "mae_r_4": "999",
            "first_touch_outcome": "TARGET_FIRST",
            "first_target_session": "1",
        }
    )
    mutated = independent_simulation(changed, session_dates(), PortfolioBacktestConfig())
    assert entered_keys(baseline) == entered_keys(mutated)
    assert skipped_keys(baseline) == skipped_keys(mutated)


def test_later_ohlc_mutation_only_changes_exit_and_subsequent_equity() -> None:
    row = opportunity("A")
    changed = copy.deepcopy(row)
    changed["high_2"] = "130"
    baseline = independent_simulation([row], session_dates(), PortfolioBacktestConfig())
    mutated = independent_simulation([changed], session_dates(), PortfolioBacktestConfig())
    assert entered_keys(baseline) == entered_keys(mutated)
    assert baseline["daily"][0] == mutated["daily"][0]
    assert baseline["trades"][0]["exit_reason"] == TIME_EXIT
    assert mutated["trades"][0]["exit_reason"] == TARGET_EXIT


def test_decision_date_score_mutation_may_change_admission() -> None:
    rows = [opportunity(f"S{index}", score=str(85 - index)) for index in range(5)]
    baseline = independent_simulation(rows, session_dates(), PortfolioBacktestConfig())
    changed = copy.deepcopy(rows)
    changed[-1]["raw_strategy_score"] = "99"
    mutated = independent_simulation(changed, session_dates(), PortfolioBacktestConfig())
    assert entered_keys(baseline) != entered_keys(mutated)


def test_skipped_future_outcome_mutation_does_not_change_earlier_decisions() -> None:
    rows = [opportunity(f"S{index}", score=str(85 - index)) for index in range(5)]
    baseline = independent_simulation(rows, session_dates(), PortfolioBacktestConfig())
    changed = copy.deepcopy(rows)
    skipped_symbol = next(row["symbol"] for row in rows if f"2024-01-01|{row['symbol']}" in skipped_keys(baseline))
    target = next(row for row in changed if row["symbol"] == skipped_symbol)
    target.update({"mfe_r_4": "999", "mae_r_4": "999", "close_return_pct_4": "999"})
    mutated = independent_simulation(changed, session_dates(), PortfolioBacktestConfig())
    assert entered_keys(baseline) == entered_keys(mutated)
    assert skipped_keys(baseline) == skipped_keys(mutated)


def test_chronology_prevents_same_day_exit_cash_reuse() -> None:
    first = opportunity(
        "A",
        entry="100",
        stop="99",
        target="101",
        highs=("100.5", "102", "102", "102"),
        lows=("99.5", "99.5", "99.5", "99.5"),
    )
    second = opportunity(
        "B",
        decision_date="2024-01-02",
        entry_date="2024-01-03",
        dates=("2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
        entry="1000",
        stop="999",
        target="1002",
    )
    result = independent_simulation(
        [first, second],
        ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"),
        PortfolioBacktestConfig(),
    )
    assert result["skipped"][0]["expected_skip_reason"] == SKIP_INSUFFICIENT_CASH
    exit_event = next(row for row in result["cash_events"] if row["event"] == "EXIT")
    assert exit_event["date"] == "2024-01-03"


def test_independent_sizing_uses_current_equity_and_cash() -> None:
    sizing = audit_sizing(
        opportunity("A", entry="100", stop="95"),
        equity=Decimal("120000"),
        cash=Decimal("10000"),
        config=PortfolioBacktestConfig(),
    )
    assert sizing["risk_budget"] == Decimal("1200")
    assert sizing["quantity_by_risk"] == 240
    assert sizing["quantity_by_cash"] == 100
    assert sizing["quantity"] == 100


def test_independent_constraint_ordering() -> None:
    same_symbol = opportunity("A", decision_date="2024-01-02", entry_date="2024-01-03", dates=("2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"))
    rows = [opportunity("A"), same_symbol]
    result = independent_simulation(rows, ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"), PortfolioBacktestConfig())
    assert result["skipped"][0]["expected_skip_reason"] == SKIP_SAME_SYMBOL_ALREADY_OPEN
    full = independent_simulation([opportunity(f"S{i}") for i in range(5)], session_dates(), PortfolioBacktestConfig())
    assert full["skipped"][0]["expected_skip_reason"] == SKIP_MAX_POSITIONS


def test_exit_reconstruction_and_ambiguity_policy() -> None:
    assert audit_exit(opportunity("T", highs=("121", "110", "110", "110")), "2024-01-02")["reason"] == TARGET_EXIT
    assert audit_exit(opportunity("S", lows=("89", "99", "99", "99")), "2024-01-02")["reason"] == STOP_EXIT
    assert audit_exit(opportunity("A", highs=("121", "110", "110", "110"), lows=("89", "99", "99", "99")), "2024-01-02")["reason"] == AMBIGUOUS_SAME_BAR_EXIT
    assert audit_exit(opportunity("X"), "2024-01-05")["reason"] == TIME_EXIT


def test_drawdown_exposure_and_cagr_reconstruction() -> None:
    daily = [
        {"date": "2024-01-01", "portfolio_equity": "100"},
        {"date": "2024-01-02", "portfolio_equity": "120"},
        {"date": "2024-01-03", "portfolio_equity": "90"},
        {"date": "2024-01-04", "portfolio_equity": "120"},
    ]
    drawdown = reconstruct_drawdown(daily)
    assert drawdown["maximum_drawdown_pct"] == Decimal("25")
    assert drawdown["peak_date"] == "2024-01-02"
    assert drawdown["trough_date"] == "2024-01-03"
    assert drawdown["recovery_date"] == "2024-01-04"
    cagr = calculate_cagr(Decimal("100"), Decimal("110"), "2023-01-01", "2024-01-01")
    assert Decimal("9.9") < cagr["cagr_pct"] < Decimal("10.1")


def test_generated_audit_reconciles_accounting_constraints_exits_and_ranking() -> None:
    report = audit_summary()
    assert report["ready_for_review"] is True
    assert report["accounting"]["cash"]["mismatch_count"] == 0
    assert report["accounting"]["equity"]["mismatch_count"] == 0
    assert report["accounting"]["pnl_mismatch_count"] == 0
    assert report["accounting"]["realized_r_mismatch_count"] == 0
    assert report["constraints"]["same_symbol"] == {"audited": 153, "incorrect": 0}
    assert report["constraints"]["max_positions"] == {"audited": 2398, "incorrect": 0}
    assert report["constraints"]["cash"] == {"audited": 15, "incorrect": 0}
    assert report["constraints"]["portfolio_risk_skips"] == {"audited": 2, "incorrect": 0}
    assert report["exits"]["all_exit_reconstruction_mismatches"] == 0
    assert report["ranking"]["reconstruction_mismatches"] == 0
    assert report["ranking"]["cutline_violations"] == 0


def test_generated_audit_is_reproducible_gross_only_and_not_optimized() -> None:
    report = audit_summary()
    assert report["reproducibility"]["deterministic_reruns_identical"] is True
    assert report["reproducibility"]["trade_count"] == 728
    assert report["reproducibility"]["skipped_count"] == 2568
    assert report["gross_only_status"]["costs"] == "NOT_MODELED"
    assert report["gross_only_status"]["slippage"] == "NOT_MODELED"
    assert report["safety"]["parameter_sweeps_run"] == 0
    assert report["safety"]["ranking_counterfactuals_adopted"] == 0
    assert all(row["diagnostic_only"] and not row["adopted"] for row in report["ranking"]["counterfactuals"])


def test_generated_risk_exposure_drawdown_cagr_and_yearly_continuity() -> None:
    report = audit_summary()
    risk = report["constraints"]["total_open_risk"]
    assert risk["entry_violations"] == 0
    assert Decimal(risk["maximum_entry_pct"]) <= Decimal("4")
    assert report["portfolio_shape"]["exposure_reconstruction"]["mismatch_count"] == 0
    assert report["portfolio_shape"]["open_positions"]["daily_count_mismatches"] == 0
    assert Decimal(report["portfolio_shape"]["drawdown"]["maximum_drawdown_pct"]) == Decimal(
        "25.76815326209741663605033331"
    )
    assert Decimal(report["portfolio_shape"]["cagr"]["cagr_pct"]) == Decimal("-3.182877736277989")
    assert report["portfolio_shape"]["yearly_continuity_mismatches"] == 0
    assert report["portfolio_shape"]["yearly_ending_equity_mismatches"] == 0


def test_generated_selection_distortion_and_skipped_outcomes_are_diagnostic_only() -> None:
    report = audit_summary()
    assert report["selection"]["distortion_classification"] in {"LOW", "MODERATE", "HIGH"}
    assert [row["count"] for row in report["selection"]["skipped_outcomes"]] == [153, 2398, 15, 2]
    assert all(row["descriptive_only"] for row in report["selection"]["skipped_outcomes"])
    assert report["selection"]["entered_outcomes"]["descriptive_only"] is True
    assert report["classifications"]["BASELINE_DECISION"] == "A FREEZE UNCHANGED"


def test_report_generation_paths_and_pilot() -> None:
    report = audit_summary()
    expected = (
        "accounting.csv",
        "chronology.csv",
        "constraints.csv",
        "ranking.csv",
        "ranking_sensitivity.csv",
        "exits.csv",
        "exposure.csv",
        "drawdown.csv",
        "monthly.csv",
        "attribution.csv",
        "selection_distortion.csv",
        "skipped_outcomes.csv",
        "pilot.csv",
    )
    assert all((DATA_DIR / "reports" / f"portfolio_backtest_v1_audit_{name}").exists() for name in expected)
    assert report["pilot"]["passed"] is True
    assert [row["pilot_case"] for row in report["pilot"]["rows"]] == list("ABCDEFGHIJKLMN")
    assert report["hash_integrity"]["all_frozen_inputs_and_ledgers_unchanged"] is True


def entered_keys(result: dict[str, object]) -> set[str]:
    return {str(row["source_key"]) for row in result["trades"]}


def skipped_keys(result: dict[str, object]) -> set[str]:
    return {str(row["source_key"]) for row in result["skipped"]}


def session_dates() -> tuple[str, ...]:
    return ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05")


def opportunity(
    symbol: str,
    *,
    decision_date: str = "2024-01-01",
    entry_date: str = "2024-01-02",
    dates: tuple[str, ...] = ("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"),
    entry: str = "100",
    stop: str = "90",
    target: str = "120",
    score: str = "85",
    rr: str = "2",
    notional: str = "10000",
    highs: tuple[str, ...] = ("110", "110", "110", "110"),
    lows: tuple[str, ...] = ("99", "99", "99", "99"),
    closes: tuple[str, ...] = ("100", "101", "102", "104"),
) -> dict[str, str]:
    row = {
        "decision_date": decision_date,
        "symbol": symbol,
        "next_session_date": entry_date,
        "hypothetical_entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "raw_strategy_score": score,
        "effective_reward_risk": rr,
        "setup_quality": "STRONG",
        "candidate_category": "BOTH_ELIGIBLE",
        "regime_state": "BULLISH",
        "momentum_points": "20",
        "rvol_points": "15",
        "relative_strength_points": "15",
        "position_notional": notional,
        "planned_rupee_risk": "1000",
        "mfe_r_4": "1",
        "mae_r_4": "0.5",
        "close_return_pct_4": "4",
        "first_touch_outcome": "NEITHER_WITHIN_HORIZON",
    }
    for index, trading_date in enumerate(dates, start=1):
        row[f"session_date_{index}"] = trading_date
        row[f"open_{index}"] = entry
        row[f"high_{index}"] = highs[index - 1]
        row[f"low_{index}"] = lows[index - 1]
        row[f"close_{index}"] = closes[index - 1]
    return row
