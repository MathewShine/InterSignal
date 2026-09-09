from __future__ import annotations

import csv
import gzip
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.strategy.breakout_quality import (
    AdjustedDailyOhlc,
    classify_52w_context,
    classify_benchmark_rs_context,
    classify_breakout_state,
    classify_candle_quality,
    classify_consolidation,
    classify_extension_risk,
    classify_level_quality,
    classify_overhead_resistance,
    classify_volume_confirmation,
    daily_reclaim_context,
    false_breakout_flags,
)
from app.strategy.daily_setup_evaluator import (
    DailySetupEvaluationEngineConfig,
    SETUP_OUTPUT_FIELDS,
    build_daily_setup_evaluations,
    evaluate_setup_candidate,
    rank_setup_rows_by_date,
)
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig


def base_values() -> dict[str, object]:
    return {
        "prior_high_20d": Decimal("100"),
        "prior_high_52w": Decimal("105"),
        "distance_to_prior_20d_high_pct": Decimal("0.012"),
        "distance_to_prior_52w_high_pct": Decimal("-0.030"),
        "relative_volume_20d": Decimal("1.60"),
        "relative_volume_5d": Decimal("1.40"),
        "relative_return_5d_vs_nifty500": Decimal("0.025"),
        "relative_return_20d_vs_nifty500": Decimal("0.035"),
        "return_1d": Decimal("0.018"),
        "return_3d": Decimal("0.030"),
        "return_5d": Decimal("0.050"),
        "return_10d": Decimal("0.065"),
        "return_20d": Decimal("0.090"),
        "up_days_ratio_10": Decimal("0.700"),
        "up_days_ratio_20": Decimal("0.600"),
        "atr_percent_14": Decimal("0.030"),
        "close_location_value": Decimal("0.820"),
        "upper_wick_pct": Decimal("0.006"),
        "lower_wick_pct": Decimal("0.004"),
        "body_pct": Decimal("0.014"),
        "daily_range_pct": Decimal("0.025"),
        "range_width_5d_pct": Decimal("0.040"),
        "range_width_10d_pct": Decimal("0.070"),
        "range_width_20d_pct": Decimal("0.090"),
        "atr_contraction_ratio": Decimal("0.700"),
        "gap_open_pct": Decimal("0.004"),
        "distance_from_sma_20_pct": Decimal("0.050"),
        "above_prior_20d_high": True,
        "intraday_high_above_prior_20d_high": True,
        "above_prior_52w_high": False,
        "candidate_extension_status": "NORMAL",
        "open": Decimal("100.8"),
        "high": Decimal("103"),
        "low": Decimal("99.7"),
        "close": Decimal("101.2"),
    }


def base_candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "candidate_state": "EMERGING",
        "emerging_eligible": "True",
        "confirmed_eligible": "False",
        "both_eligible": "False",
        "emerging_rank": "3",
        "emerging_percentile": "88.5",
        "confirmed_rank": "",
        "confirmed_percentile": "",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "candidate_config_hash": "d111957c7a24da96",
        "benchmark_context_version": "BENCHMARK_CONTEXT_V1",
        "adjustment_methodology": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "exclusion_policy": "CORPORATE_ACTION_EXCLUSIONS_V1",
        "research_eligible": "True",
        "eligibility_status": "RESEARCH_ELIGIBLE",
        "mandatory_gates_passed": "True",
        "rejection_reasons": "",
        "extension_status": "NORMAL",
        "sector_context_status": "CURRENT_ONLY",
        "warning_flags": "",
    }
    row.update(overrides)
    return row


def base_feature(**overrides: object) -> dict[str, object]:
    values = base_values()
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "benchmark_context_version": "BENCHMARK_CONTEXT_V1",
        "adjustment_methodology": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "exclusion_policy": "CORPORATE_ACTION_EXCLUSIONS_V1",
        "feature_status": "READY",
        "feature_null_reasons": "",
        "sector_mapping_status": "CURRENT_ONLY",
    }
    row.update({key: str(value) for key, value in values.items() if key not in {"open", "high", "low", "close", "candidate_extension_status"}})
    row.update({"above_prior_20d_high": "True", "intraday_high_above_prior_20d_high": "True", "above_prior_52w_high": "False"})
    row.update(overrides)
    return row


def test_breakout_states_cover_approach_close_intraday_and_failed() -> None:
    config = DailySetupEvaluationConfig()
    values = base_values()
    assert classify_breakout_state(values, config) == "CLOSE_ACCEPTED"
    approaching = values | {"above_prior_20d_high": False, "intraday_high_above_prior_20d_high": False, "high": Decimal("99.5"), "close": Decimal("97"), "distance_to_prior_20d_high_pct": Decimal("-0.030")}
    assert classify_breakout_state(approaching, config) == "APPROACHING"
    intraday = values | {"above_prior_20d_high": False, "close": Decimal("99.8"), "high": Decimal("100.3"), "distance_to_prior_20d_high_pct": Decimal("-0.002"), "close_location_value": Decimal("0.520"), "upper_wick_pct": Decimal("0.010")}
    assert classify_breakout_state(intraday, config) == "INTRADAY_BREAK_ONLY"
    failed = intraday | {"close": Decimal("99.0"), "distance_to_prior_20d_high_pct": Decimal("-0.010"), "close_location_value": Decimal("0.250"), "upper_wick_pct": Decimal("0.040")}
    assert classify_breakout_state(failed, config) == "FAILED_BREAK"


def test_prior_level_quality_excludes_current_session() -> None:
    config = DailySetupEvaluationConfig()
    values = base_values()
    prior_bars = [
        AdjustedDailyOhlc("2026-01-07", "ABC", Decimal("98"), Decimal("99.0"), Decimal("96"), Decimal("98")),
        AdjustedDailyOhlc("2026-01-08", "ABC", Decimal("98"), Decimal("100.1"), Decimal("97"), Decimal("99")),
        AdjustedDailyOhlc("2026-01-09", "ABC", Decimal("99"), Decimal("100.3"), Decimal("98"), Decimal("99.5")),
    ]
    quality, metadata = classify_level_quality(values, prior_bars, config)
    assert quality == "GOOD"
    assert metadata["touches"] == 2


def test_consolidation_atr_volume_benchmark_candle_extension_components() -> None:
    config = DailySetupEvaluationConfig()
    values = base_values()
    state, quality, evidence = classify_consolidation(values, config)
    assert state == "TIGHT"
    assert quality == "STRONG"
    assert "LOWER_ATR_SHORT_TERM" in evidence
    assert classify_volume_confirmation(values, config) == "STRONG"
    assert classify_benchmark_rs_context(values, config) == "STRONG"
    assert classify_candle_quality(values, config) == "STRONG"
    assert classify_extension_risk(values, config) == "LOW"


def test_false_breakout_upper_wick_gap_fade_and_daily_reclaim() -> None:
    config = DailySetupEvaluationConfig()
    values = base_values() | {
        "above_prior_20d_high": False,
        "high": Decimal("101"),
        "low": Decimal("98"),
        "close": Decimal("99"),
        "distance_to_prior_20d_high_pct": Decimal("-0.010"),
        "close_location_value": Decimal("0.200"),
        "upper_wick_pct": Decimal("0.040"),
        "gap_open_pct": Decimal("0.030"),
        "relative_volume_20d": Decimal("0.80"),
        "relative_volume_5d": Decimal("0.90"),
    }
    breakout_state = classify_breakout_state(values, config)
    flags = false_breakout_flags(values, breakout_state, "WEAK", config)
    assert breakout_state == "FAILED_BREAK"
    assert {"INTRADAY_BREAK_FAILED", "UPPER_WICK_REJECTION", "LOW_VOLUME_BREAK", "GAP_FADE", "POSSIBLE_FALSE_BREAKOUT"} <= flags
    reclaim_values = base_values() | {"low": Decimal("99.5"), "close": Decimal("101")}
    reclaim, depth, status = daily_reclaim_context(reclaim_values, config)
    assert reclaim is True
    assert depth == Decimal("0.005")
    assert status == "SHALLOW"


def test_overhead_resistance_and_52w_context() -> None:
    config = DailySetupEvaluationConfig()
    values = base_values() | {"distance_to_prior_52w_high_pct": Decimal("-0.006"), "above_prior_52w_high": False}
    assert classify_overhead_resistance(values, config) == "HIGH"
    assert classify_52w_context(values, config) == "NEAR"
    unavailable = values | {"distance_to_prior_52w_high_pct": None}
    assert classify_overhead_resistance(unavailable, config) == "UNAVAILABLE"
    assert classify_52w_context(unavailable, config) == "UNAVAILABLE"


def test_evaluate_setup_candidate_emerging_and_confirmed_treatment() -> None:
    config = DailySetupEvaluationConfig()
    ohlc = AdjustedDailyOhlc("2026-01-10", "ABC", Decimal("100.8"), Decimal("103"), Decimal("99.7"), Decimal("101.2"))
    row = evaluate_setup_candidate(base_candidate(), feature_row=base_feature(), current_ohlc=ohlc, prior_bars=[], config=config)
    assert row["setup_version"] == DAILY_SETUP_EVALUATION_VERSION
    assert row["setup_eligible"] is True
    assert row["setup_quality"] in {"VALID", "STRONG"}
    assert "BREAKOUT_20D" in row["setup_type_flags"]
    confirmed = evaluate_setup_candidate(base_candidate(candidate_state="CONFIRMED", confirmed_eligible="True", emerging_eligible="True", confirmed_rank="1", confirmed_percentile="99"), feature_row=base_feature(), current_ohlc=ohlc, prior_bars=[], config=config)
    assert confirmed["candidate_rank"] == "1"
    assert confirmed["setup_eligible"] is True


def test_setup_rejection_reasons_and_no_clear_breakout() -> None:
    feature = base_feature(
        above_prior_20d_high="False",
        intraday_high_above_prior_20d_high="False",
        distance_to_prior_20d_high_pct="-0.150",
        distance_to_prior_52w_high_pct="-0.200",
        above_prior_52w_high="False",
        close_location_value="0.300",
    )
    ohlc = AdjustedDailyOhlc("2026-01-10", "ABC", Decimal("85"), Decimal("86"), Decimal("82"), Decimal("85"))
    row = evaluate_setup_candidate(base_candidate(), feature_row=feature, current_ohlc=ohlc, prior_bars=[])
    assert row["setup_eligible"] is False
    assert "NO_CLEAR_BREAKOUT_OR_CONTINUATION" in row["setup_rejection_reasons"]
    assert row["setup_quality"] == "POOR"


def test_same_date_rank_is_unaffected_by_next_session_rows() -> None:
    t_row = {"trading_date": "2026-01-10", "symbol": "ABC", "setup_eligible": True, "_rank_tuple": (3, 6, 3, 4, 4, Decimal("90")), "setup_rank": "", "setup_percentile": ""}
    weaker_t_row = {"trading_date": "2026-01-10", "symbol": "DEF", "setup_eligible": True, "_rank_tuple": (2, 4, 2, 3, 3, Decimal("80")), "setup_rank": "", "setup_percentile": ""}
    future_row = {"trading_date": "2026-01-11", "symbol": "XYZ", "setup_eligible": True, "_rank_tuple": (3, 9, 3, 5, 4, Decimal("99")), "setup_rank": "", "setup_percentile": ""}
    rows_by_date = {"2026-01-10": [t_row, weaker_t_row], "2026-01-11": [future_row]}
    rank_setup_rows_by_date(rows_by_date)
    assert t_row["setup_rank"] == 1
    assert weaker_t_row["setup_rank"] == 2
    assert future_row["setup_rank"] == 1


def test_dataset_fields_do_not_include_final_entry_or_outcome_fields() -> None:
    forbidden_fragments = ["entry_score", "target", "stop_loss", "position_size", "mfe", "mae", "winner", "loser"]
    lowered_fields = [field.lower() for field in SETUP_OUTPUT_FIELDS]
    assert not any(fragment in field for fragment in forbidden_fragments for field in lowered_fields)


def test_report_generation_no_outcomes_and_input_regression(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    candidate_path = data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"
    feature_path = data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"
    adjusted_path = data_dir / "research" / "adjusted" / "daily" / "nse" / "2026" / "01" / "nse_adjusted_daily_20260110.csv"
    write_gzip_rows(candidate_path, [base_candidate()])
    write_gzip_rows(feature_path, [base_feature()])
    write_plain_rows(
        adjusted_path,
        [
            {
                "trading_date": "2026-01-10",
                "symbol": "ABC",
                "isin": "INEABC",
                "series": "EQ",
                "adjusted_open": "100.8",
                "adjusted_high": "103",
                "adjusted_low": "99.7",
                "adjusted_close": "101.2",
            }
        ],
    )
    config = DailySetupEvaluationEngineConfig(
        data_dir=data_dir,
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 10),
        full_generation=False,
    )
    report = build_daily_setup_evaluations(config=config)
    assert report["setup_evaluator"]["setup_version"] == DAILY_SETUP_EVALUATION_VERSION
    assert report["generation"]["candidate_rows_evaluated"] == 1
    assert report["integrity"]["daily_features_v1_unchanged"] is True
    assert report["integrity"]["momentum_candidates_v1_unchanged"] is True
    assert report["safety"]["orders_placed"] == 0
    assert report["safety"]["remote_migrations_applied"] == 0
    assert report["safety"]["supabase_bulk_records_persisted"] == 0
    summary = json.loads((data_dir / "reports" / "daily_setup_summary.json").read_text(encoding="utf-8"))
    assert summary["safety"]["entry_scores_generated"] == 0


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_plain_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
