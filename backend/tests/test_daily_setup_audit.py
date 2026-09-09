from __future__ import annotations

import csv
import gzip
import json
from datetime import date
from pathlib import Path

from app.strategy.daily_setup_audit import (
    DAILY_SETUP_AUDIT_VERSION,
    DailySetupAuditConfig,
    breakout_x_candle_summary,
    build_daily_setup_audit,
    candle_quality_audit_rows,
    candle_weaknesses,
    daily_churn_rows,
    false_breakout_summary,
    funnel_sanity_result,
    primary_rejection_driver,
    rejection_overlap_audit_rows,
    sensitivity_audit_rows,
    setup_streak_summary_rows,
    structural_stability_result,
    transition_matrix_rows,
)
from app.strategy.setup_config import DailySetupEvaluationConfig


def setup_row(**overrides: object) -> dict[str, object]:
    config = DailySetupEvaluationConfig()
    row: dict[str, object] = {
        "trading_date": "2026-01-02",
        "symbol": "ABC",
        "isin": "INEABC",
        "candidate_state": "EMERGING",
        "emerging_eligible": "True",
        "confirmed_eligible": "False",
        "both_eligible": "False",
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "candidate_config_hash": "d111957c7a24da96",
        "feature_version": "DAILY_FEATURES_V1",
        "setup_version": "DAILY_SETUP_EVALUATION_V1",
        "setup_config_hash": config.config_hash(),
        "setup_status": "READY",
        "research_status": "READY",
        "setup_eligible": "True",
        "setup_rejection_reasons": "",
        "setup_type_flags": "BREAKOUT_20D;MOMENTUM_CONTINUATION",
        "breakout_state": "CLOSE_ACCEPTED",
        "level_quality": "GOOD",
        "consolidation_state": "TIGHT",
        "consolidation_quality": "GOOD",
        "acceptance_state": "MODERATE",
        "candle_quality": "GOOD",
        "volume_confirmation": "STRONG",
        "benchmark_rs_context": "STRONG",
        "sector_context_status": "CURRENT_ONLY_NOT_USED",
        "extension_risk": "LOW",
        "overhead_resistance": "LOW",
        "high_52w_context": "NEAR",
        "daily_level_reclaim": "False",
        "reclaim_depth_status": "NONE",
        "false_breakout_flags": "",
        "prior_high_20d": "100",
        "prior_high_52w": "106",
        "distance_to_prior_20d_high_pct": "0.010",
        "distance_to_prior_52w_high_pct": "-0.040",
        "relative_volume_20d": "1.60",
        "relative_volume_5d": "1.30",
        "relative_return_5d_vs_nifty500": "0.020",
        "relative_return_20d_vs_nifty500": "0.030",
        "return_1d": "0.015",
        "return_5d": "0.050",
        "return_10d": "0.070",
        "atr_percent_14": "0.030",
        "close_location_value": "0.700",
        "upper_wick_pct": "0.010",
        "lower_wick_pct": "0.005",
        "body_pct": "0.012",
        "daily_range_pct": "0.030",
        "range_width_5d_pct": "0.050",
        "range_width_10d_pct": "0.080",
        "range_width_20d_pct": "0.110",
        "atr_contraction_ratio": "0.800",
        "gap_open_pct": "0.005",
        "distance_from_sma_20_pct": "0.050",
        "price": "101",
        "adjusted_open": "100",
        "adjusted_high": "103",
        "adjusted_low": "99",
        "adjusted_close": "101",
        "setup_quality": "VALID",
        "setup_rank": "1",
        "setup_percentile": "100",
        "supporting_evidence": "VOLUME_STRONG;BENCHMARK_RS_STRONG",
        "warning_flags": "",
    }
    row.update(overrides)
    return row


def sample_rows() -> list[dict[str, object]]:
    return [
        setup_row(trading_date="2026-01-02", symbol="ABC", setup_quality="STRONG", setup_eligible="True"),
        setup_row(trading_date="2026-01-05", symbol="ABC", setup_quality="VALID", setup_eligible="True"),
        setup_row(
            trading_date="2026-01-06",
            symbol="ABC",
            setup_quality="POOR",
            setup_eligible="False",
            candle_quality="POOR",
            close_location_value="0.250",
            upper_wick_pct="0.040",
            body_pct="0.001",
            false_breakout_flags="GAP_FADE;POSSIBLE_FALSE_BREAKOUT;UPPER_WICK_REJECTION",
            setup_rejection_reasons="POOR_CANDLE_QUALITY;POSSIBLE_FALSE_BREAKOUT",
            breakout_state="FAILED_BREAK",
        ),
        setup_row(
            trading_date="2026-01-02",
            symbol="XYZ",
            candidate_state="CONFIRMED",
            both_eligible="True",
            setup_quality="WATCH",
            setup_eligible="False",
            candle_quality="FAIR",
            breakout_state="APPROACHING",
            acceptance_state="NONE",
            setup_rejection_reasons="INSUFFICIENT_SETUP_CONFIRMATION",
        ),
    ]


def test_candle_weakness_decomposition_and_poor_combinations() -> None:
    config = DailySetupEvaluationConfig()
    poor = sample_rows()[2]
    weaknesses = candle_weaknesses(poor, config)
    assert {"WEAK_CLOSE_LOCATION", "SMALL_BODY", "LARGE_UPPER_WICK", "GAP_FADE", "MULTIPLE_CANDLE_WEAKNESSES"} <= set(weaknesses)
    rows, summary = candle_quality_audit_rows(sample_rows(), config)
    assert summary["poor_count"] == 1
    assert any(row["section"] == "POOR_CANDLE_COMBINATION" for row in rows)


def test_breakout_x_candle_and_emerging_confirmed_comparison_inputs() -> None:
    summary = breakout_x_candle_summary(sample_rows())
    assert summary["FAILED_BREAK"]["POOR"]["count"] == 1
    assert summary["APPROACHING"]["FAIR"]["count"] == 1


def test_rejection_overlap_and_primary_rejection_driver() -> None:
    rows, summary = rejection_overlap_audit_rows(sample_rows())
    assert summary["reason_count_distribution"]["exactly_2"] == 1
    assert primary_rejection_driver(sample_rows()[2]) == "CANDLE_FAILURE"
    assert any(row["section"] == "REJECTION_PAIR" for row in rows)


def test_false_breakout_reclaim_streak_transition_and_churn() -> None:
    rows = sample_rows()
    sessions = ["2026-01-02", "2026-01-05", "2026-01-06"]
    false_summary = false_breakout_summary(rows)
    assert false_summary["rows_with_any_flag"] == 1
    streak_rows, streak_summary = setup_streak_summary_rows(rows, sessions)
    assert streak_summary["ANY_SETUP_ELIGIBLE"]["max"] == 2
    assert any(row["streak_type"] == "WATCH_SETUP" for row in streak_rows)
    transition_rows, transition_summary = transition_matrix_rows(rows, sessions)
    assert transition_summary["setup_eligible_next_session"]["EMERGING"]["REMAINS_SETUP_ELIGIBLE"]["count"] == 1
    assert any(row["section"] == "SETUP_STATE_TRANSITION" for row in transition_rows)
    churn_rows, churn_summary = daily_churn_rows(rows, sessions)
    assert churn_rows[1]["continued_setup_eligible"] == 1
    assert "churn_rate_pct_distribution" in churn_summary


def test_sensitivity_jaccard_structural_stability_and_funnel_sanity() -> None:
    rows = sample_rows()
    sessions = ["2026-01-02", "2026-01-05", "2026-01-06"]
    sensitivity_rows, sensitivity_summary = sensitivity_audit_rows(rows, DailySetupEvaluationConfig(), sessions)
    assert "BASELINE" in sensitivity_summary["scenarios"]
    assert sensitivity_summary["scenarios"]["BASELINE"]["jaccard_similarity"] == "1.0000"
    stability = structural_stability_result(sensitivity_rows)
    assert stability["status"] in {"STABLE", "MODERATELY_SENSITIVE", "HIGHLY_SENSITIVE"}
    funnel = {
        "overall_pass_rate_pct": "20.0000",
    }
    candle = {"poor_pct": "65.0000"}
    sanity = funnel_sanity_result(funnel, candle, sensitivity_summary)
    assert sanity["status"] in {"HEALTHY", "HEALTHY_BUT_CANDLE_STRICT"}


def test_report_generation_no_outcomes_and_baseline_immutability(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    setup_path = data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"
    candidate_path = data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"
    feature_path = data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"
    calendar_path = data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"
    write_gzip_rows(setup_path, sample_rows())
    write_gzip_rows(candidate_path, [{"trading_date": "2026-01-02", "symbol": "ABC"}])
    write_gzip_rows(feature_path, [{"trading_date": "2026-01-02", "symbol": "ABC"}])
    write_plain_rows(
        calendar_path,
        [
            {"trading_date": "2026-01-02", "session_type": "NORMAL", "source_available": "True"},
            {"trading_date": "2026-01-05", "session_type": "NORMAL", "source_available": "True"},
            {"trading_date": "2026-01-06", "session_type": "NORMAL", "source_available": "True"},
        ],
    )
    report = build_daily_setup_audit(
        config=DailySetupAuditConfig(
            data_dir=data_dir,
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 6),
        )
    )
    assert report["audit"]["audit_version"] == DAILY_SETUP_AUDIT_VERSION
    assert report["regression"]["setup_dataset_unchanged"] is True
    assert report["regression"]["candidate_dataset_unchanged"] is True
    assert report["regression"]["feature_dataset_unchanged"] is True
    assert report["safety"]["future_outcome_fields_used"] == 0
    assert report["safety"]["entry_scores_generated"] == 0
    persisted = json.loads((data_dir / "reports" / "daily_setup_audit_summary.json").read_text(encoding="utf-8"))
    assert persisted["outputs"]["sensitivity_csv"].endswith("daily_setup_sensitivity.csv")


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
