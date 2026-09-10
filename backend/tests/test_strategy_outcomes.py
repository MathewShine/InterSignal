from __future__ import annotations

import copy
import gzip
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.risk.risk_config import CURRENT_RISK_STRUCTURE_CONFIG_HASH, CURRENT_RISK_STRUCTURE_VERSION
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_config import (
    STRATEGY_OUTCOME_VERSION,
    SWING_DAILY_OUTCOME_PROFILE,
    StrategyOutcomeConfig,
)
from app.strategy.outcomes.outcome_engine import (
    AMBIGUOUS,
    COUNTERFACTUAL_COHORT,
    ENTRY_INVALID_CAPITAL,
    ENTRY_INVALID_GAP,
    ENTRY_INVALID_RR,
    ENTRY_INVALID_STOP_RELATION,
    ENTRY_VALID,
    EXCEPTIONAL_COHORT,
    INSUFFICIENT_FORWARD_DATA,
    INVALID_ENTRY,
    NEITHER_WITHIN_HORIZON,
    NO_NEXT_SESSION_DATA,
    OTHER_INVALID,
    PREVIEW_COHORT,
    PRIMARY_COHORT,
    STOP_FIRST,
    TARGET_FIRST,
    ForwardExclusion,
    OutcomeBar,
    StrategyOutcomeEngineConfig,
    ambiguity_valid,
    build_outcome_row,
    build_report_tables,
    classify_gap,
    load_selected_score_rows,
    monotonic_horizons,
    outcome_cohort,
    resolve_next_sessions,
    run_pilot_validation,
    touch_temporal_valid,
    write_outcome_reports,
    write_outcome_rows,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
    baseline_hash_checks,
    baseline_input_hashes,
    resolve_current_strategy_score_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_outcome_version_profile_and_hash_are_explicit_and_reproducible() -> None:
    first = StrategyOutcomeConfig()
    second = StrategyOutcomeConfig()
    assert first.outcome_version == STRATEGY_OUTCOME_VERSION
    assert first.outcome_profile == SWING_DAILY_OUTCOME_PROFILE
    assert first.config_hash() == second.config_hash()
    assert len(first.config_hash()) == 16


def test_next_session_resolution_uses_trading_sessions_not_calendar_days() -> None:
    sessions = [date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)]
    assert resolve_next_sessions(date(2024, 1, 5), sessions) == [date(2024, 1, 8), date(2024, 1, 9)]


def test_next_session_open_is_entry_and_t_close_is_not_faked() -> None:
    row = evaluate(bars=market_bars(opens=(Decimal("103"),) * 4))
    assert row["next_session_date"] == "2024-01-03"
    assert row["hypothetical_entry_price"] == Decimal("103")
    assert row["hypothetical_entry_price"] != Decimal("100")
    assert row["entry_model"] == "NEXT_SESSION_OPEN"


@pytest.mark.parametrize(
    ("gap", "expected"),
    [
        (Decimal("-1"), "GAP_DOWN"),
        (Decimal("0.1"), "FLAT"),
        (Decimal("1"), "SMALL_GAP_UP"),
        (Decimal("3"), "MATERIAL_GAP_UP"),
        (Decimal("6"), "EXTREME_GAP_UP"),
    ],
)
def test_gap_classification_is_centralized(gap: Decimal, expected: str) -> None:
    assert classify_gap(gap, StrategyOutcomeConfig()) == expected


def test_open_at_or_below_stop_is_invalid() -> None:
    row = evaluate(
        bars=market_bars(opens=(Decimal("94"),) * 4),
        risk=base_risk(stop_price="95", selected_target_price="120"),
    )
    assert row["entry_recheck_status"] == ENTRY_INVALID_STOP_RELATION
    assert row["first_touch_outcome"] == INVALID_ENTRY


def test_gap_up_that_breaks_rr_is_invalid_gap() -> None:
    row = evaluate(
        bars=market_bars(opens=(Decimal("105"),) * 4),
        risk=base_risk(stop_price="95", selected_target_price="110"),
    )
    assert row["entry_recheck_status"] == ENTRY_INVALID_GAP
    assert row["effective_reward_risk"] == Decimal("0.5")


def test_non_gap_effective_rr_failure_is_invalid_rr() -> None:
    row = evaluate(
        bars=market_bars(opens=(Decimal("105"),) * 4),
        risk=base_risk(
            assumed_entry_price="110",
            entry_reference_price="110",
            stop_price="100",
            selected_target_price="110",
        ),
    )
    assert row["entry_recheck_status"] == ENTRY_INVALID_RR


def test_position_size_is_recalculated_with_whole_shares_and_no_leverage() -> None:
    row = evaluate(risk=base_risk(stop_price="95", selected_target_price="115"))
    assert row["entry_recheck_status"] == ENTRY_VALID
    assert row["quantity_by_risk"] == 200
    assert row["quantity_by_cash"] == 1000
    assert row["hypothetical_quantity"] == 200
    assert row["position_notional"] == Decimal("20000")
    assert row["planned_rupee_risk"] == Decimal("1000")
    assert row["no_leverage_status"] == "NO_LEVERAGE"


def test_unaffordable_next_open_is_invalid_capital() -> None:
    expensive_bars = market_bars(
        opens=(Decimal("110000"),) * 4,
        highs=(Decimal("120000"),) * 4,
        lows=(Decimal("109000"),) * 4,
        closes=(Decimal("115000"),) * 4,
    )
    row = evaluate(
        bars=expensive_bars,
        risk=base_risk(
            assumed_entry_price="110000",
            entry_reference_price="110000",
            stop_price="109000",
            selected_target_price="112000",
        ),
    )
    assert row["entry_recheck_status"] == ENTRY_INVALID_CAPITAL
    assert row["hypothetical_quantity"] == 0


def test_position_size_uses_central_outcome_capital_configuration() -> None:
    config = StrategyOutcomeConfig(
        research_capital_rupees=Decimal("50000"),
        max_risk_per_trade_pct=Decimal("0.50"),
    )
    row = build_outcome_row(
        score_row=base_score(),
        risk_row=base_risk(),
        sessions=trading_sessions(),
        bars=market_bars(),
        exclusions={},
        config=config,
    )
    assert row["risk_budget_rupees"] == Decimal("250")
    assert row["hypothetical_quantity"] == 50
    assert row["planned_risk_pct"] == Decimal("0.5")


def test_session_indexing_and_forward_close_returns() -> None:
    row = evaluate(bars=market_bars(closes=(Decimal("101"), Decimal("102"), Decimal("103"), Decimal("104"))))
    assert [row[f"session_date_{h}"] for h in range(1, 5)] == [
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
    ]
    assert row["close_return_pct_1"] == Decimal("1")
    assert row["close_return_pct_4"] == Decimal("4")
    assert row["close_return_r_4"] == Decimal("0.8")


def test_mfe_mae_are_cumulative_nonnegative_and_monotonic() -> None:
    bars = market_bars(
        highs=(Decimal("102"), Decimal("104"), Decimal("103"), Decimal("106")),
        lows=(Decimal("99"), Decimal("98"), Decimal("97"), Decimal("98")),
    )
    row = evaluate(bars=bars)
    assert row["mfe_pct_4"] == Decimal("6")
    assert row["mae_pct_4"] == Decimal("3")
    assert row["mfe_r_4"] == Decimal("1.2")
    assert row["mae_r_4"] == Decimal("0.6")
    assert monotonic_horizons(row, "mfe_pct")
    assert monotonic_horizons(row, "mae_pct")


def test_target_first_across_sessions_and_cumulative_touch_flags() -> None:
    bars = market_bars(highs=(Decimal("104"), Decimal("116"), Decimal("110"), Decimal("109")))
    row = evaluate(bars=bars, risk=base_risk(stop_price="90", selected_target_price="115"))
    assert row["first_target_session"] == 2
    assert row["first_touch_outcome"] == TARGET_FIRST
    assert row["target_touched_1"] is False
    assert row["target_touched_2"] is True
    assert touch_temporal_valid(row)


def test_stop_first_across_sessions() -> None:
    bars = market_bars(lows=(Decimal("98"), Decimal("89"), Decimal("97"), Decimal("98")))
    row = evaluate(bars=bars, risk=base_risk(stop_price="90", selected_target_price="120"))
    assert row["first_stop_session"] == 2
    assert row["first_touch_outcome"] == STOP_FIRST


def test_same_bar_stop_target_is_ambiguous() -> None:
    bars = market_bars(highs=(Decimal("121"),) * 4, lows=(Decimal("89"),) * 4)
    row = evaluate(bars=bars, risk=base_risk(stop_price="90", selected_target_price="120"))
    assert row["first_stop_session"] == row["first_target_session"] == 1
    assert row["same_bar_ambiguous"] is True
    assert row["first_touch_outcome"] == AMBIGUOUS
    assert ambiguity_valid(row)


def test_neither_within_complete_horizon() -> None:
    row = evaluate(risk=base_risk(stop_price="90", selected_target_price="120"))
    assert row["first_touch_outcome"] == NEITHER_WITHIN_HORIZON


def test_partial_forward_data_is_retained_and_right_censored() -> None:
    sessions = trading_sessions()[:2]
    bars = {key: value for key, value in market_bars().items() if key[0] <= "2024-01-04"}
    row = evaluate(sessions=sessions, bars=bars)
    assert row["forward_sessions_available"] == 2
    assert row["horizon_available_2"] is True
    assert row["horizon_available_3"] is False
    assert row["right_censored"] is True
    assert row["first_touch_outcome"] == INSUFFICIENT_FORWARD_DATA


def test_no_next_session_data_is_explicit() -> None:
    row = evaluate(sessions=[], bars={})
    assert row["entry_recheck_status"] == NO_NEXT_SESSION_DATA
    assert row["entry_valid"] is False


def test_missing_symbol_bar_is_not_skipped_to_a_later_session() -> None:
    bars = market_bars()
    bars.pop(("2024-01-03", "ABC"))
    row = evaluate(bars=bars)
    assert row["entry_recheck_status"] == NO_NEXT_SESSION_DATA


def test_corporate_action_interval_makes_forward_data_unsafe() -> None:
    exclusions = {"ABC": [ForwardExclusion(date(2024, 1, 4), date(2024, 1, 5), "test_exclusion", "event-1")]}
    row = evaluate(exclusions=exclusions)
    assert row["forward_data_safe"] is False
    assert row["forward_data_status"] == "FORWARD_DATA_UNSAFE"
    assert row["entry_recheck_status"] == OTHER_INVALID


@pytest.mark.parametrize(
    ("mode", "disposition", "expected"),
    [
        ("FULL_SCORE", "ENTRY_ELIGIBLE", PRIMARY_COHORT),
        ("FULL_SCORE", "NOT_ELIGIBLE", COUNTERFACTUAL_COHORT),
        ("EXCEPTIONAL_REVIEW_SCORE", "EXCEPTIONAL_REVIEW", EXCEPTIONAL_COHORT),
        ("PREVIEW_SCORE", "PREVIEW_ONLY", PREVIEW_COHORT),
    ],
)
def test_cohort_labels_preserve_source_semantics(mode: str, disposition: str, expected: str) -> None:
    assert outcome_cohort(base_score(score_mode=mode, scoring_disposition=disposition)) == expected


def test_comparison_cohorts_never_become_primary_evaluation_rows() -> None:
    row = evaluate(score=base_score(score_mode="FULL_SCORE", scoring_disposition="NOT_ELIGIBLE"))
    assert row["entry_valid"] is True
    assert row["outcome_cohort"] == COUNTERFACTUAL_COHORT
    assert row["primary_evaluation_eligible"] is False


def test_output_is_research_only_and_generates_no_signal_or_order() -> None:
    row = evaluate()
    assert row["trade_signal_status"] == "SOURCE_FROZEN_RESEARCH_ONLY"
    assert row["historical_execution_status"] == "NOT_EXECUTED"
    assert "order" not in row


def test_future_price_mutation_changes_only_outcome_not_frozen_inputs() -> None:
    score = base_score()
    risk = base_risk()
    frozen_score = copy.deepcopy(score)
    frozen_risk = copy.deepcopy(risk)
    first = evaluate(score=score, risk=risk)
    changed_bars = market_bars(highs=(Decimal("103"), Decimal("118"), Decimal("104"), Decimal("104")))
    second = evaluate(score=score, risk=risk, bars=changed_bars)
    assert first["mfe_pct_2"] != second["mfe_pct_2"]
    assert score == frozen_score
    assert risk == frozen_risk


def test_outcome_write_is_deterministic_and_reports_are_generated(tmp_path: Path) -> None:
    rows = [evaluate()]
    first = tmp_path / "one.csv.gz"
    second = tmp_path / "two.csv.gz"
    write_outcome_rows(first, rows)
    write_outcome_rows(second, rows)
    assert file_sha256(first) == file_sha256(second)
    with gzip.open(first, "rt", encoding="utf-8") as file:
        assert "STRATEGY_OUTCOME_V1" in file.read()
    engine = StrategyOutcomeEngineConfig(data_dir=tmp_path)
    pilot = run_pilot_validation(rows, engine.outcome_config)
    tables = build_report_tables(rows, pilot)
    write_outcome_reports(engine, {"ready_for_review": True}, tables)
    assert engine.report_path("summary.json").exists()
    assert all(engine.report_path(f"{name}.csv").exists() for name in tables)


def test_current_frozen_datasets_and_score_baseline_are_unchanged() -> None:
    hashes = baseline_input_hashes(DATA_DIR)
    assert all(baseline_hash_checks(hashes).values())
    assert file_sha256(resolve_current_strategy_score_dataset(DATA_DIR)) == STRATEGY_SCORE_V1_DATASET_HASH


def test_selected_real_cohorts_preserve_expected_population_counts() -> None:
    rows = load_selected_score_rows(resolve_current_strategy_score_dataset(DATA_DIR))
    counts: dict[str, int] = {}
    for row in rows:
        cohort = outcome_cohort(row)
        counts[cohort or ""] = counts.get(cohort or "", 0) + 1
    assert len(rows) == 14251
    assert counts == {
        PRIMARY_COHORT: 4268,
        COUNTERFACTUAL_COHORT: 6523,
        EXCEPTIONAL_COHORT: 324,
        PREVIEW_COHORT: 3136,
    }


def test_score_generation_does_not_import_outcome_layer() -> None:
    scorer = (REPO_ROOT / "backend" / "app" / "strategy" / "scoring" / "strategy_scorer.py").read_text(encoding="utf-8")
    baseline = (REPO_ROOT / "backend" / "app" / "strategy" / "scoring" / "score_baseline.py").read_text(encoding="utf-8")
    assert "strategy.outcomes" not in scorer
    assert "strategy.outcomes" not in baseline


def base_score(**overrides: str) -> dict[str, str]:
    row = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "isin": "INEABC",
        "score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
        "score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
        "score_mode": "FULL_SCORE",
        "scoring_disposition": "ENTRY_ELIGIBLE",
        "raw_strategy_score": "83",
        "score_band": "ENTRY_ELIGIBLE",
        "setup_quality": "STRONG",
        "candidate_state": "CONFIRMED",
        "candidate_category": "BOTH_ELIGIBLE",
        "regime_state": "BULLISH",
        "regime_confidence": "HIGH",
        "setup_points": "20",
        "momentum_points": "19",
        "rvol_points": "15",
        "relative_strength_points": "15",
        "regime_points": "10",
        "reward_risk_points": "4",
    }
    row.update(overrides)
    return row


def base_risk(**overrides: str) -> dict[str, str]:
    row = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "isin": "INEABC",
        "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "entry_reference_price": "100",
        "assumed_entry_price": "100",
        "stop_price": "95",
        "selected_target_price": "115",
        "selected_target_basis": "R_MULTIPLE_2R_RESEARCH_REFERENCE",
    }
    row.update(overrides)
    return row


def trading_sessions() -> list[date]:
    return [date(2024, 1, day) for day in (3, 4, 5, 8)]


def market_bars(
    *,
    opens: tuple[Decimal, ...] = (Decimal("100"),) * 4,
    highs: tuple[Decimal, ...] = (Decimal("103"),) * 4,
    lows: tuple[Decimal, ...] = (Decimal("98"),) * 4,
    closes: tuple[Decimal, ...] = (Decimal("101"),) * 4,
) -> dict[tuple[str, str], OutcomeBar]:
    return {
        (session.isoformat(), "ABC"): OutcomeBar(session, "ABC", opens[index], highs[index], lows[index], closes[index])
        for index, session in enumerate(trading_sessions())
    }


def evaluate(
    *,
    score: dict[str, str] | None = None,
    risk: dict[str, str] | None = None,
    sessions: list[date] | None = None,
    bars: dict[tuple[str, str], OutcomeBar] | None = None,
    exclusions: dict[str, list[ForwardExclusion]] | None = None,
) -> dict[str, object]:
    return build_outcome_row(
        score_row=score or base_score(),
        risk_row=risk or base_risk(),
        sessions=trading_sessions() if sessions is None else sessions,
        bars=market_bars() if bars is None else bars,
        exclusions=exclusions or {},
    )
