from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.strategy.outcomes.outcome_audit import (
    AUDIT_REPORT_NAMES,
    STRATEGY_OUTCOME_AUDIT_VERSION,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    StrategyOutcomeAuditConfig,
    audit_capital_demand,
    audit_forward_safety,
    audit_gap_and_rr,
    audit_mfe_mae,
    audit_overlap,
    audit_r_levels,
    audit_reconstruction,
    audit_target_distance,
    audit_terminology_and_separation,
    audit_yearly,
    favorable_before_stop_state,
    frozen_hashes,
    gap_size_bucket,
    reconstruct_path,
    safety_counterfactuals,
    target_distance_bucket,
    target_r_bucket,
    time_to_extreme,
    verify_frozen_hashes,
    write_audit_outputs,
)
from app.strategy.outcomes.outcome_engine import (
    AMBIGUOUS,
    ENTRY_INVALID_GAP,
    ENTRY_INVALID_STOP_RELATION,
    ENTRY_VALID,
    NEITHER_WITHIN_HORIZON,
    PRIMARY_COHORT,
    STOP_FIRST,
    TARGET_FIRST,
    OutcomeBar,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_audit_version_and_frozen_baselines_are_explicit_and_unchanged() -> None:
    config = StrategyOutcomeAuditConfig(data_dir=DATA_DIR)
    before = frozen_hashes(config)
    verify_frozen_hashes(before)
    after = frozen_hashes(config)
    assert STRATEGY_OUTCOME_AUDIT_VERSION == "STRATEGY_OUTCOME_AUDIT_V1"
    assert before == after
    assert before["outcome_v1"] == STRATEGY_OUTCOME_V1_DATASET_HASH


def test_frozen_hash_verification_rejects_an_outcome_change() -> None:
    hashes = frozen_hashes(StrategyOutcomeAuditConfig(data_dir=DATA_DIR))
    hashes["outcome_v1"] = "0" * 64
    with pytest.raises(ValueError, match="outcome dataset hash"):
        verify_frozen_hashes(hashes)


def test_unsafe_causes_and_entry_vs_later_sessions_are_decomposed() -> None:
    primary = [base_row(symbol="AAA"), base_row(symbol="BBB")]
    sessions = trading_sessions()
    bars = safe_bars(("AAA", "BBB"), sessions[1:])
    bars[(sessions[1].isoformat(), "AAA")] = bar(sessions[1], "AAA", status="UNSAFE")
    bars[(sessions[3].isoformat(), "BBB")] = bar(sessions[3], "BBB", status="CONTINUITY_BREAK")

    result = audit_forward_safety(primary, sessions, bars, {})

    assert result["unsafe_primary_rows"] == 2
    assert result["entry_session_unsafe_count"] == 1
    assert result["later_window_only_unsafe_count"] == 1
    assert {row["primary_cause"] for row in result["row_summaries"]} == {
        "UNSAFE_ADJUSTED_BAR_STATUS",
        "STRUCTURAL_CONTINUITY_BREAK",
    }


def test_strict_entry_only_and_censor_counterfactuals_remain_distinct() -> None:
    valid = base_row(symbol="VALID", forward_data_safe=True, entry_valid=True)
    later = base_row(symbol="LATER", entry_valid=False, entry_recheck_status=ENTRY_VALID)
    safety = [
        {
            "decision_date": later["decision_date"],
            "symbol": later["symbol"],
            "entry_session_unsafe": False,
            "later_window_only_unsafe": True,
        }
    ]

    result = safety_counterfactuals([valid, later], safety)

    policies = {row["policy"]: row for row in result["policies"]}
    assert policies["BASELINE_FORWARD_WINDOW_STRICT"]["valid_entry_count"] == 1
    assert policies["ENTRY_SESSION_MUST_BE_SAFE_ONLY"]["valid_entry_count"] == 2
    assert policies["CENSOR_AT_FIRST_UNSAFE_FORWARD_SESSION"]["partial_or_right_censored_count"] == 1


def test_gap_distribution_rr_delta_and_invalidation_decomposition() -> None:
    valid = complete_row(
        gap_pct="-1",
        planned_reward_risk="2",
        effective_reward_risk="2.2",
        delta_rr="0.2",
    )
    invalid = base_row(
        symbol="GAP",
        forward_data_safe=True,
        entry_valid=False,
        entry_recheck_status=ENTRY_INVALID_GAP,
        gap_pct="3",
        planned_reward_risk="2",
        effective_reward_risk="1.4",
        delta_rr="-0.6",
        target_price="107",
    )

    result = audit_gap_and_rr([valid, invalid])

    assert result["gap_quantiles"][0]["value"] == Decimal("-1")
    assert result["gap_invalidated_count"] == 1
    assert result["gap_invalidation_decomposition"][0]["reason"] == "RR_DROPPED_BELOW_1_5"
    assert result["safe_crossed_below_1_5_count"] == 1
    assert result["delta_rr_distribution"]["median"] == Decimal("-0.2")


def test_open_at_or_below_stop_reconstruction_is_correct() -> None:
    row = base_row(
        entry_valid=False,
        forward_data_safe=True,
        entry_recheck_status=ENTRY_INVALID_STOP_RELATION,
        hypothetical_entry_price="94",
        stop_price="95",
    )
    result = audit_gap_and_rr([row])
    assert result["open_stop_count"] == 1
    assert result["open_stop_correct_count"] == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1.8", "1.5-<2R"), ("2.2", "2-<2.5R"), ("2.5", ">=2.5R")],
)
def test_target_r_buckets(value: str, expected: str) -> None:
    assert target_r_bucket({"effective_reward_risk": value}) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2", "<=2%"), ("3", "2-4%"), ("5", "4-6%"), ("8", "6-10%"), ("11", ">10%")],
)
def test_target_distance_buckets(value: str, expected: str) -> None:
    assert target_distance_bucket({"effective_target_distance_pct": value}) == expected


def test_target_and_stop_distance_profiles_preserve_r_normalization() -> None:
    target = complete_row(highs=("111", "111", "111", "111"), target_price="110")
    stop = complete_row(symbol="STOP", lows=("94", "94", "94", "94"))
    result = audit_target_distance([target, stop])
    assert result["all_valid_target_distance_r"]["count"] == 2
    assert {row["first_touch_outcome"] for row in result["first_touch_profiles"]} == {TARGET_FIRST, STOP_FIRST}


def test_favorable_and_adverse_r_level_reach_by_horizon() -> None:
    row = complete_row(highs=("102.5", "105", "107.5", "110"), lows=("98", "97.5", "95", "94"))
    result = audit_r_levels([row])
    favorable = {(item["horizon"], item["r_level"]): item["reached_count"] for item in result["favorable_reach"]}
    adverse = {(item["horizon"], item["r_level"]): item["reached_count"] for item in result["adverse_reach"]}
    assert favorable[(1, Decimal("0.5"))] == 1
    assert favorable[(4, Decimal("2"))] == 1
    assert adverse[(2, Decimal("0.5"))] == 1
    assert adverse[(4, Decimal("1"))] == 1


def test_mfe_mae_time_to_extremes_and_session_increments() -> None:
    row = complete_row(highs=("102", "106", "105", "106"), lows=("99", "98", "94", "95"))
    result = audit_mfe_mae([row])
    assert result["horizons"][3]["median_mfe_r"] == Decimal("1.2")
    assert result["horizons"][3]["median_mae_r"] == Decimal("1.2")
    assert result["time_to_mfe"][0]["session"] == 2
    assert result["time_to_mae"][0]["session"] == 3
    assert len(result["session_specific"]) == 4
    assert len(result["incremental"]) == 4


def test_favorable_before_stop_uses_session_order_and_marks_same_session_ambiguous() -> None:
    earlier = complete_row(highs=("103", "104", "104", "104"), lows=("99", "94", "94", "94"))
    same = complete_row(symbol="SAME", highs=("103", "104", "104", "104"), lows=("94", "94", "94", "94"))
    assert favorable_before_stop_state(earlier, Decimal("0.5")) == "FAVORABLE_EARLIER_SESSION"
    assert favorable_before_stop_state(same, Decimal("0.5")) == "SAME_SESSION_SEQUENCE_AMBIGUOUS"


def test_first_touch_ambiguity_mfe_mae_and_close_reconstruct_cleanly() -> None:
    rows = [
        complete_row(symbol="TARGET", highs=("111", "111", "111", "111"), target_price="110"),
        complete_row(symbol="STOP", lows=("94", "94", "94", "94")),
        complete_row(symbol="AMB", highs=("111", "111", "111", "111"), lows=("94", "94", "94", "94"), target_price="110"),
        complete_row(symbol="NEITHER"),
    ]
    result = audit_reconstruction(rows)
    assert [row["first_touch_outcome"] for row in rows] == [TARGET_FIRST, STOP_FIRST, AMBIGUOUS, NEITHER_WITHIN_HORIZON]
    assert result["ambiguity_mismatches"] == 0
    assert result["first_touch_mismatches"] == 0
    assert result["mfe_r_mismatches"] == 0
    assert result["mae_r_mismatches"] == 0
    assert result["close_return_mismatches"] == 0


def test_right_censoring_is_reported_without_ordinary_neither_reconstruction() -> None:
    row = complete_row()
    row["right_censored"] = True
    row["horizon_available_4"] = False
    row["high_4"] = row["low_4"] = row["close_4"] = ""
    row["first_touch_outcome"] = "INSUFFICIENT_FORWARD_DATA"
    result = audit_reconstruction([row])
    assert result["right_censored_primary_count"] == 1


def test_unsafe_and_censored_semantics_cohorts_and_language_remain_separate() -> None:
    row = complete_row()
    row.update(
        {
            "source_scoring_disposition": "ENTRY_ELIGIBLE",
            "source_score_mode": "FULL_SCORE",
            "primary_evaluation_eligible": True,
            "transaction_cost_status": "NOT_MODELED",
            "slippage_status": "NOT_MODELED",
            "historical_execution_status": "NOT_EXECUTED",
            "trade_signal_status": "NOT_A_SIGNAL",
            "forward_data_status": "SAFE",
        }
    )
    result = audit_terminology_and_separation([row])
    assert result["canonical_profitability_language_violations"] == 0
    assert result["cohort_separation_violations"] == 0
    assert result["unsafe_censored_conflation_violations"] == 0
    assert result["execution_engine_components_introduced"] == 0
    assert result["signals_generated"] == result["orders_placed"] == 0


def test_canonical_profitability_language_is_rejected() -> None:
    row = complete_row()
    row["bad_label"] = "WIN"
    assert audit_terminology_and_separation([row])["canonical_profitability_language_violations"] == 1


def test_same_symbol_overlap_and_cross_position_concurrency() -> None:
    sessions = trading_sessions(8)
    first = complete_row(decision_date="2024-01-01", symbol="AAA")
    second = complete_row(decision_date="2024-01-02", symbol="AAA")
    other = complete_row(decision_date="2024-01-01", symbol="BBB")
    assign_session_dates(first, sessions[1:5])
    assign_session_dates(second, sessions[2:6])
    assign_session_dates(other, sessions[1:5])
    result = audit_overlap([first, second, other], [first, second, other], sessions)
    assert result["consecutive_same_symbol_opportunities"] == 1
    assert result["maximum_streak"] == 2
    assert result["valid_rows_overlapping_same_symbol_holding"] == 2
    assert result["active_opportunity_distribution"]["max"] == 3


def test_capital_and_planned_risk_demand_sum_overlapping_rows() -> None:
    sessions = trading_sessions(5)[1:5]
    first = complete_row(position_notional="60000", planned_rupee_risk="700")
    second = complete_row(symbol="BBB", position_notional="60000", planned_rupee_risk="700")
    assign_session_dates(first, sessions)
    assign_session_dates(second, sessions)
    result = audit_capital_demand([first, second])
    assert result["days_demanded_notional_above_100000"] == 4
    assert result["notional_distribution"]["median"] == Decimal("120000")
    assert result["planned_risk_distribution"]["median"] == Decimal("1400")
    assert result["days_above_risk_thresholds"]["1000"] == 4


def test_yearly_profiles_include_all_required_years() -> None:
    rows = [complete_row(decision_date=f"{year}-01-02", symbol=f"S{year}") for year in range(2021, 2027)]
    result = audit_yearly(rows)
    assert [row["year"] for row in result] == list(range(2021, 2027))
    assert all(row["source_count"] == 1 for row in result)


@pytest.mark.parametrize(
    ("gap", "expected"),
    [("-3", "<=-2%"), ("-1", "-2_TO_-0.5%"), ("0", "-0.5_TO_0%"), ("3", "2_TO_5%"), ("6", ">5%")],
)
def test_gap_size_outcome_buckets(gap: str, expected: str) -> None:
    assert gap_size_bucket({"gap_pct": gap}) == expected


def test_all_machine_reports_and_bulk_details_are_generated(tmp_path: Path) -> None:
    config = StrategyOutcomeAuditConfig(data_dir=tmp_path)
    tables = {name: [{"section": "TEST", "value": name}] for name in AUDIT_REPORT_NAMES}
    report = {"artifacts": {"storage_size_bytes": 0}}
    write_audit_outputs(config, report, tables, [{"symbol": "AAA"}], [{"symbol": "AAA"}])
    assert config.summary_path.exists()
    assert all(config.report_path(name).exists() for name in AUDIT_REPORT_NAMES)
    assert (config.bulk_dir / "forward_safety_detail.csv.gz").exists()
    assert (config.bulk_dir / "extended_horizon_detail.csv.gz").exists()
    assert report["artifacts"]["storage_size_bytes"] > 0


def base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "decision_date": "2024-01-01",
        "symbol": "AAA",
        "outcome_cohort": PRIMARY_COHORT,
        "entry_valid": False,
        "entry_recheck_status": "FORWARD_DATA_UNSAFE",
        "forward_data_safe": False,
        "forward_sessions_available": 4,
        "reference_entry_price": "100",
        "hypothetical_entry_price": "100",
        "stop_price": "95",
        "target_price": "110",
        "planned_reward_risk": "2",
        "effective_reward_risk": "2",
        "delta_rr": "0",
        "planned_stop_distance_pct": "5",
        "planned_target_distance_pct": "10",
        "effective_stop_distance_pct": "5",
        "effective_target_distance_pct": "10",
        "hypothetical_quantity": 10,
        "planned_quantity": 10,
        "position_notional": "1000",
        "planned_rupee_risk": "50",
        "gap_pct": "0",
        "gap_category": "FLAT",
        "target_type": "STRUCTURAL_TARGET",
        "target_basis": "STRUCTURAL_RESISTANCE",
        "score_raw": "80",
        "source_raw_strategy_score": "80",
        "regime_state": "BULLISH",
        "setup_quality": "STRONG",
        "candidate_category": "EMERGING_ONLY",
        "right_censored": False,
    }
    row.update(overrides)
    return row


def complete_row(
    *,
    highs: tuple[str, str, str, str] = ("102", "103", "104", "105"),
    lows: tuple[str, str, str, str] = ("99", "98", "97", "96"),
    closes: tuple[str, str, str, str] = ("101", "102", "103", "104"),
    **overrides: object,
) -> dict[str, object]:
    row = base_row(entry_valid=True, entry_recheck_status=ENTRY_VALID, forward_data_safe=True, **overrides)
    for horizon in range(1, 5):
        row[f"high_{horizon}"] = highs[horizon - 1]
        row[f"low_{horizon}"] = lows[horizon - 1]
        row[f"close_{horizon}"] = closes[horizon - 1]
        row[f"horizon_available_{horizon}"] = True
    rebuilt = reconstruct_path(row)
    row.update(rebuilt)
    row["first_stop_session"] = rebuilt["first_stop_session"]
    row["first_target_session"] = rebuilt["first_target_session"]
    row["same_bar_ambiguous"] = rebuilt["same_bar_ambiguous"]
    row["first_touch_outcome"] = rebuilt["first_touch_outcome"]
    return row


def trading_sessions(count: int = 5) -> list[date]:
    return [date(2024, 1, day) for day in range(1, count + 1)]


def bar(session: date, symbol: str, *, status: str = "ADJUSTED_READY") -> OutcomeBar:
    return OutcomeBar(
        trading_date=session,
        symbol=symbol,
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("101"),
        research_usability_status=status,
    )


def safe_bars(symbols: tuple[str, ...], sessions: list[date]) -> dict[tuple[str, str], OutcomeBar]:
    return {(session.isoformat(), symbol): bar(session, symbol) for symbol in symbols for session in sessions}


def assign_session_dates(row: dict[str, object], sessions: list[date]) -> None:
    row["next_session_date"] = sessions[0].isoformat()
    for horizon, session in enumerate(sessions, start=1):
        row[f"session_date_{horizon}"] = session.isoformat()
