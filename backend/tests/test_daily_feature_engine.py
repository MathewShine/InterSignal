from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from decimal import Decimal

from app.features import breakout_context, daily, liquidity, volatility
from app.features.base import DAILY_FEATURES_VERSION, AdjustedDailyBar, DailyFeatureConfig
from app.services.daily_feature_engine import (
    DailyFeatureEngineConfig,
    FeatureRowBuilder,
    MembershipPeriod,
    Nifty500MembershipIndex,
    ResearchEligibilityIndex,
    build_daily_feature_engine,
    build_symbol_feature_cache,
    load_adjusted_nifty500_bars,
    write_daily_feature_engine_markdown,
)


def test_core_daily_feature_formulas_are_deterministic():
    sessions = make_sessions(260)
    bars = make_bars("RELIANCE", sessions)
    target_index = 220
    bars[target_index] = replace_bar(bars[target_index], high=Decimal("999"))

    row = build_row(bars, target_index, sessions)

    assert row["feature_version"] == DAILY_FEATURES_VERSION
    assert row["availability_time"] == "EOD"
    assert row["decision_input_time"] == "NEXT_SESSION_DECISION_INPUT"
    assert row["return_1d"] == daily.trailing_return(bars, target_index, 1)
    assert row["return_5d"] == daily.trailing_return(bars, target_index, 5)
    assert row["return_20d"] == daily.trailing_return(bars, target_index, 20)
    assert row["momentum_20d"] == row["return_20d"]
    assert row["positive_days_5"] == 5
    assert row["up_days_ratio_5"] == Decimal("1")
    assert row["daily_traded_value"] == liquidity.daily_traded_value(bars[target_index])
    assert row["median_traded_value_20d"] == liquidity.rolling_median_traded_value(bars, target_index, 20)
    assert row["avg_volume_20d"] == liquidity.rolling_average_volume(bars, target_index, 20)
    assert row["relative_volume_20d"] == liquidity.relative_volume_vs_prior_median(bars, target_index, 20)
    assert row["true_range"] == volatility.true_range(bars, target_index)
    assert row["atr_14"] == volatility.simple_atr(bars, target_index, 14)
    assert row["return_volatility_20d"] == volatility.rolling_return_volatility(bars, target_index, 20)
    assert row["prior_high_20d"] == max(bar.high for bar in bars[target_index - 20 : target_index])
    assert row["prior_high_20d"] != bars[target_index].high
    assert row["sma_20"] == daily.simple_moving_average(bars, target_index, 20)
    assert row["distance_from_sma_20_pct"] == breakout_context.distance_to_level(bars[target_index].close, row["sma_20"])
    assert row["daily_range_pct"] == (bars[target_index].high - bars[target_index].low) / bars[target_index].close
    assert row["gap_open_pct"] == breakout_context.gap_open_pct(bars, target_index)
    assert row["range_width_20d_pct"] == breakout_context.range_width_pct(bars, target_index, 20)
    assert row["atr_contraction_ratio"] == row["atr_5"] / row["atr_20"]
    assert row["intraday_high_above_prior_20d_high"] is True
    assert row["benchmark_status"] == "BENCHMARK_UNAVAILABLE"


def test_relative_volume_denominator_excludes_current_date():
    sessions = make_sessions(30)
    bars = make_bars("RELIANCE", sessions)
    target_index = 25
    bars[target_index] = replace_bar(bars[target_index], volume=Decimal("1000000"))

    row = build_row(bars, target_index, sessions)
    prior_median = liquidity.rolling_average_volume(bars, target_index - 1, 1)
    assert prior_median != bars[target_index].volume
    assert row["relative_volume_20d"] == liquidity.relative_volume_vs_prior_median(bars, target_index, 20)


def test_insufficient_history_and_missing_trading_sessions_are_explicit():
    sessions = make_sessions(8)
    bars = make_bars("RELIANCE", [sessions[0], sessions[1], sessions[2], sessions[4], sessions[5], sessions[6]])

    early = build_row(bars, 2, sessions)
    assert early["return_5d"] is None
    assert "return_5d:INSUFFICIENT_HISTORY" in early["feature_null_reasons"]

    missing = build_row(bars, 5, sessions)
    assert missing["return_3d"] is None
    assert "return_3d:MISSING_INPUT_DATA:missing_trading_session_in_window" in missing["feature_null_reasons"]


def test_corporate_action_lookback_blocking_uses_eligibility_metadata():
    sessions = make_sessions(12)
    bars = make_bars("INFIBEAM", sessions)
    exclusion = {
        "symbol": "INFIBEAM",
        "start_date": sessions[4].isoformat(),
        "end_date": sessions[4].isoformat(),
        "eligibility_status": "EXCLUDE_SECURITY_RANGE",
        "reason_code": "unresolved_discontinuity_exclusion_v1",
        "source_event_id": "",
        "confidence": "MEDIUM",
    }
    row = build_row(bars, 8, sessions, eligibility_rows=[exclusion])

    assert row["return_5d"] is None
    assert row["feature_status"] == "CORPORATE_ACTION_LOOKBACK_BLOCKED"
    assert row["eligibility_reason_codes"] == "unresolved_discontinuity_exclusion_v1"


def test_membership_intersection_prevents_future_membership_leakage(tmp_path):
    data_dir = tmp_path / "data"
    sessions = make_sessions(4)
    write_calendar(data_dir, sessions)
    write_membership(data_dir, [("FUTURE", sessions[2], sessions[3])])
    write_eligibility(data_dir, [("FUTURE", sessions[2], sessions[3], "RESEARCH_READY", "default")])
    for session in sessions:
        write_adjusted_file(data_dir, session, [bar_row("FUTURE", session, 100)])

    membership_index = Nifty500MembershipIndex([
        MembershipPeriod("FUTURE", "INEFUTURE", sessions[2], sessions[3], "fixture", "OFFICIAL_EVENTS_PARTIAL", "fixture")
    ])
    loaded, summary = load_adjusted_nifty500_bars(
        adjusted_daily_dir=data_dir / "research" / "adjusted" / "daily" / "nse",
        membership_index=membership_index,
        start_date=sessions[0],
        end_date=sessions[-1],
        trading_sessions=sessions,
    )

    assert summary["loaded_bars"] == 2
    assert [bar.trading_date for bar in loaded["FUTURE"]] == [sessions[2], sessions[3]]
    assert membership_index.period_for("FUTURE", sessions[1]) is None


def test_future_price_mutation_does_not_change_feature_date_output():
    sessions = make_sessions(35)
    bars = make_bars("RELIANCE", sessions)
    original = build_row(bars, 25, sessions)
    mutated = list(bars)
    mutated[26] = replace_bar(mutated[26], close=Decimal("999999"), high=Decimal("999999"), low=Decimal("999999"))
    after_mutation = build_row(mutated, 25, sessions)

    checked_fields = ["return_5d", "prior_high_20d", "relative_volume_20d", "sma_20", "gap_open_pct"]
    assert {field: original[field] for field in checked_fields} == {field: after_mutation[field] for field in checked_fields}


def test_zero_range_candle_is_null_explained_not_zero_filled():
    sessions = make_sessions(3)
    bars = make_bars("RELIANCE", sessions)
    bars[2] = replace_bar(bars[2], open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"))

    row = build_row(bars, 2, sessions)

    assert row["close_location_value"] is None
    assert "close_location_value:ZERO_RANGE_CANDLE" in row["feature_null_reasons"]


def test_report_generation_writes_local_outputs_without_mutating_adjusted_dataset(tmp_path):
    data_dir = tmp_path / "data"
    sessions = make_sessions(30)
    write_calendar(data_dir, sessions)
    write_membership(data_dir, [("RELIANCE", sessions[0], sessions[-1])])
    write_eligibility(data_dir, [("RELIANCE", sessions[0], sessions[-1], "RESEARCH_READY", "default")])
    write_membership_coverage(data_dir)
    write_current_constituents(data_dir)
    for index, session in enumerate(sessions):
        write_adjusted_file(data_dir, session, [bar_row("RELIANCE", session, 100 + index)])
    before = list((data_dir / "research" / "adjusted" / "daily" / "nse").glob("*/*/*.csv"))[0].read_text(encoding="utf-8")

    report = build_daily_feature_engine(
        config=DailyFeatureEngineConfig(data_dir=data_dir, start_date=sessions[0], end_date=sessions[-1])
    )
    write_daily_feature_engine_markdown(report, tmp_path / "docs" / "daily-feature-engine.md")

    assert report["ready_for_review"] is True
    assert report["generation"]["full_generation_completed"] is True
    assert report["generation"]["generated_feature_rows"] == 30
    assert report["benchmark"]["status"] == "UNAVAILABLE"
    assert report["integrity"]["raw_nse_unchanged"] is True
    assert list((data_dir / "research" / "adjusted" / "daily" / "nse").glob("*/*/*.csv"))[0].read_text(encoding="utf-8") == before
    assert json.loads(report["outputs"]["summary_json"] and (data_dir / "reports" / "daily_feature_engine_summary.json").read_text(encoding="utf-8"))["safety"]["orders_placed"] == 0


def build_row(
    bars: list[AdjustedDailyBar],
    index: int,
    sessions: list[date],
    eligibility_rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    membership = MembershipPeriod(
        symbol=bars[index].symbol,
        isin=bars[index].isin,
        valid_from=sessions[0],
        valid_to=sessions[-1],
        reconstruction_method="fixture",
        source_confidence="OFFICIAL_EVENTS_PARTIAL",
        provenance="fixture",
    )
    return FeatureRowBuilder(
        bars=bars,
        index=index,
        membership=membership,
        membership_status="PARTIAL_HISTORY",
        universe_version="fixture",
        sector="",
        feature_cache=build_symbol_feature_cache(bars, DailyFeatureConfig()),
        eligibility_index=ResearchEligibilityIndex(eligibility_rows or [], sessions),
        trading_sessions=sessions,
        trading_session_index={session: offset for offset, session in enumerate(sessions)},
        feature_config=DailyFeatureConfig(),
        benchmark_available=False,
    ).build()


def make_sessions(count: int) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=offset) for offset in range(count)]


def make_bars(symbol: str, sessions: list[date]) -> list[AdjustedDailyBar]:
    bars: list[AdjustedDailyBar] = []
    for index, session in enumerate(sessions):
        close = Decimal(100 + index)
        bars.append(
            AdjustedDailyBar(
                trading_date=session,
                symbol=symbol,
                isin=f"INE{symbol}",
                open=close - Decimal("1"),
                high=close + Decimal("2"),
                low=close - Decimal("2"),
                close=close,
                volume=Decimal(1000 + index),
                source_file="fixture.csv",
                source="fixture",
                research_usability_status="ADJUSTED_READY",
                adjustment_methodology_version="PRICE_ADJUSTED_STRUCTURAL_V1",
                provenance="fixture",
            )
        )
    return bars


def replace_bar(bar: AdjustedDailyBar, **kwargs) -> AdjustedDailyBar:
    values = {
        "trading_date": bar.trading_date,
        "symbol": bar.symbol,
        "isin": bar.isin,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "source_file": bar.source_file,
        "source": bar.source,
        "research_usability_status": bar.research_usability_status,
        "adjustment_methodology_version": bar.adjustment_methodology_version,
        "provenance": bar.provenance,
    }
    values.update(kwargs)
    return AdjustedDailyBar(**values)


def write_calendar(data_dir, sessions):
    write_csv(
        data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv",
        [{"trading_date": session.isoformat(), "session_type": "NORMAL", "source_reference": "fixture", "source_available": "True", "notes": ""} for session in sessions],
        ["trading_date", "session_type", "source_reference", "source_available", "notes"],
    )


def write_membership(data_dir, rows):
    write_csv(
        data_dir / "reference" / "nifty500" / "history" / "membership_periods.csv",
        [
            {
                "index_name": "NIFTY 500",
                "symbol": symbol,
                "isin": f"INE{symbol}",
                "valid_from": start.isoformat(),
                "valid_to": end.isoformat(),
                "reconstruction_method": "fixture",
                "source_confidence": "OFFICIAL_EVENTS_PARTIAL",
                "provenance": "fixture",
            }
            for symbol, start, end in rows
        ],
        ["index_name", "symbol", "isin", "valid_from", "valid_to", "reconstruction_method", "source_confidence", "provenance"],
    )


def write_eligibility(data_dir, rows):
    write_csv(
        data_dir / "reference" / "nse" / "corporate_actions" / "research_eligibility.csv",
        [
            {
                "symbol": symbol,
                "isin": f"INE{symbol}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "eligibility_status": status,
                "reason_code": reason,
                "source_event_id": "",
                "confidence": "HIGH",
                "policy_version": "CORPORATE_ACTION_EXCLUSIONS_V1",
                "lookback_contamination_supported": "True",
                "notes": "fixture",
            }
            for symbol, start, end, status, reason in rows
        ],
        ["symbol", "isin", "start_date", "end_date", "eligibility_status", "reason_code", "source_event_id", "confidence", "policy_version", "lookback_contamination_supported", "notes"],
    )


def write_membership_coverage(data_dir):
    path = data_dir / "reference" / "nifty500" / "history" / "membership_coverage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"phase": "fixture", "survivorship_bias_status": "PARTIAL_HISTORY"}), encoding="utf-8")


def write_current_constituents(data_dir):
    write_csv(
        data_dir / "reference" / "nifty500" / "current" / "nifty500_constituents_normalized.csv",
        [{"symbol": "RELIANCE", "company_name": "Reliance", "isin": "INERELIANCE", "industry": "Energy", "sector": "", "membership_start": "", "source": "fixture", "source_date": "2024-01-01"}],
        ["symbol", "company_name", "isin", "industry", "sector", "membership_start", "source", "source_date"],
    )


def write_adjusted_file(data_dir, session, rows):
    path = data_dir / "research" / "adjusted" / "daily" / "nse" / f"{session:%Y}" / f"{session:%m}" / f"nse_adjusted_daily_{session:%Y%m%d}.csv"
    write_csv(
        path,
        rows,
        [
            "trading_date",
            "symbol",
            "isin",
            "series",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "adjusted_open",
            "adjusted_high",
            "adjusted_low",
            "adjusted_close",
            "raw_volume",
            "adjusted_volume",
            "cumulative_adjustment_factor",
            "adjustment_applied",
            "adjustment_event_count",
            "adjustment_methodology_version",
            "research_usability_status",
            "source",
            "provenance",
        ],
    )


def bar_row(symbol, session, close):
    return {
        "trading_date": session.isoformat(),
        "symbol": symbol,
        "isin": f"INE{symbol}",
        "series": "EQ",
        "raw_open": str(close - 1),
        "raw_high": str(close + 2),
        "raw_low": str(close - 2),
        "raw_close": str(close),
        "adjusted_open": str(close - 1),
        "adjusted_high": str(close + 2),
        "adjusted_low": str(close - 2),
        "adjusted_close": str(close),
        "raw_volume": "1000",
        "adjusted_volume": "1000",
        "cumulative_adjustment_factor": "1",
        "adjustment_applied": "False",
        "adjustment_event_count": "0",
        "adjustment_methodology_version": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "research_usability_status": "ADJUSTED_READY",
        "source": "fixture",
        "provenance": "fixture",
    }


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
