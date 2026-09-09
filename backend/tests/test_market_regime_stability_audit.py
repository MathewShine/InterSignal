from __future__ import annotations

import csv
import gzip
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.regime.regime_config import MarketRegimeConfig
from app.regime.stability_audit import (
    MarketRegimeStabilityAuditConfig,
    agreement_class_for_row,
    available_weight_analysis,
    boundary_zone_analysis,
    build_market_regime_stability_audit,
    classify_rows_by_threshold,
    component_transition_analysis,
    confidence_audit_rows,
    direct_flip_rows,
    flip_driver_analysis,
    normalization_audit,
    one_day_state_summary,
    scenario_analysis,
    score_change_analysis,
    simulate_hysteresis,
    simulate_minimum_persistence,
    simulate_score_smoothing,
    write_market_regime_stability_audit_markdown,
)
from app.strategy.momentum_candidates import file_sha256


def test_direct_flip_extraction_and_flip_driver_decomposition() -> None:
    rows = [
        regime_row("2024-01-01", "BULLISH", "48", "31.2", trend="BULLISH", trend_contribution="18", breadth="BULLISH", breadth_contribution="12", sector="NEUTRAL", sector_contribution="0"),
        regime_row("2024-01-02", "BEARISH", "-60", "-39", trend="BEARISH", trend_contribution="-18", breadth="STRONGLY_BEARISH", breadth_contribution="-20", sector="NEUTRAL", sector_contribution="0"),
        regime_row("2024-01-03", "NEUTRAL", "0", "0"),
    ]

    flips = direct_flip_rows(rows)
    drivers, summary = flip_driver_analysis(flips, MarketRegimeConfig())

    assert len(flips) == 1
    assert flips[0]["date_t"] == "2024-01-01"
    assert flips[0]["date_t1"] == "2024-01-02"
    assert drivers[0]["dominant_driver"] in {"MULTI_COMPONENT", "TREND_DOMINANT", "BREADTH_DOMINANT"}
    assert drivers[0]["structural_classification"] in {"STRONG_MULTI_COMPONENT_REVERSAL", "MODERATE_MULTI_COMPONENT_REVERSAL"}
    assert summary["structural_classification_distribution"]


def test_borderline_score_bands_and_score_change_distribution() -> None:
    rows = [
        regime_row("2024-01-01", "NEUTRAL", "28", "18.2"),
        regime_row("2024-01-02", "BULLISH", "32", "20.8"),
        regime_row("2024-01-03", "BEARISH", "-31", "-20.15"),
        regime_row("2024-01-04", "NEUTRAL", "-10", "-6.5"),
    ]

    boundary_summary, boundary_rows = boundary_zone_analysis(rows)
    changes, change_summary = score_change_analysis(rows)

    assert any(row["band"] == "PLUS_25_TO_35" and row["row_count"] == 2 for row in boundary_summary)
    assert any(row["band"] == "PLUS_25_TO_35" for row in boundary_rows)
    assert change_summary["distribution"]["usable_rows"] == 3
    assert change_summary["distribution"]["p99"]
    assert {row["change_band"] for row in changes} <= {"LOW_CHANGE", "MODERATE_CHANGE", "HIGH_CHANGE", "EXTREME_CHANGE"}
    assert any(row["direct_bullish_bearish_flip"] for row in changes)


def test_component_transition_matrices_and_contribution_volatility() -> None:
    rows = [
        regime_row("2024-01-01", "NEUTRAL", "0", "0", trend="NEUTRAL", trend_contribution="0", breadth="BULLISH", breadth_contribution="12", sector="NEUTRAL", sector_contribution="0"),
        regime_row("2024-01-02", "BULLISH", "46.1538", "30", trend="BULLISH", trend_contribution="18", breadth="BULLISH", breadth_contribution="12", sector="NEUTRAL", sector_contribution="0"),
        regime_row("2024-01-03", "BEARISH", "-46.1538", "-30", trend="BEARISH", trend_contribution="-18", breadth="BEARISH", breadth_contribution="-12", sector="NEUTRAL", sector_contribution="0"),
    ]

    transition_rows, summary, daily_changes = component_transition_analysis(rows, MarketRegimeConfig())

    assert any(row["component_name"] == "NIFTY_TREND" and row["from_state"] == "BULLISH" and row["to_state"] == "BEARISH" for row in transition_rows)
    assert summary["discretization"]["NIFTY_TREND"]["daily_bucket_changes"] >= 2
    assert summary["contribution_volatility"]["NIFTY_TREND"]["max"] == "36.0000"
    assert any(row["component_name"] == "NIFTY500_BREADTH" for row in daily_changes)


def test_normalization_multiplier_and_raw_normalized_equivalence() -> None:
    config = MarketRegimeConfig()
    rows = [
        regime_row("2024-01-01", "BULLISH", "30", "19.5"),
        regime_row("2024-01-02", "NEUTRAL", "29", "18.85"),
        regime_row("2024-01-03", "BEARISH", "-30", "-19.5"),
    ]
    flips = direct_flip_rows([rows[0], rows[2]])

    audit = normalization_audit(rows, flips, config)
    available = available_weight_analysis(rows, flips)

    assert audit["raw_vs_normalized_mismatch_count"] == 0
    assert audit["normalization_material_direct_flip_count"] == 0
    assert audit["classification_artifact_result"] == "NO_CLASSIFICATION_ARTIFACTS"
    assert audit["multiplier_distribution"]["median"] == "1.5385"
    assert available["bucket_counts"]["65"]["count"] == 3


def test_confidence_ceiling_and_agreement_classification() -> None:
    rows = [
        regime_row("2024-01-01", "BULLISH", "72", "46.8", confidence_score="70.5", confidence_state="MEDIUM", warnings="NIFTY500_MEMBERSHIP_PARTIAL_HISTORY"),
        regime_row("2024-01-02", "NEUTRAL", "5", "3.25", confidence_score="55", confidence_state="MEDIUM", trend="BULLISH", trend_contribution="18", breadth="BEARISH", breadth_contribution="-12", sector="NEUTRAL", sector_contribution="0"),
    ]

    confidence_rows, summary = confidence_audit_rows(rows, MarketRegimeConfig())

    assert confidence_rows
    assert summary["theoretical_ceiling"]["high_mathematically_unreachable"] is True
    assert "mathematically unreachable" in summary["high_confidence_absence_reason"]
    assert agreement_class_for_row(rows[0]) == "FULL_AVAILABLE_AGREEMENT"
    assert agreement_class_for_row(rows[1]) == "CONFLICTING"


def test_one_day_states_and_structural_scenarios() -> None:
    config = MarketRegimeConfig()
    rows = [
        regime_row("2024-01-01", "BULLISH", "45", "29.25"),
        regime_row("2024-01-02", "NEUTRAL", "0", "0"),
        regime_row("2024-01-03", "BULLISH", "36", "23.4"),
        regime_row("2024-01-04", "BEARISH", "-36", "-23.4"),
        regime_row("2024-01-05", "BEARISH", "-38", "-24.7"),
        regime_row("2024-01-06", "NEUTRAL", "0", "0"),
    ]

    deadband = classify_rows_by_threshold(rows, Decimal("40"), Decimal("-40"), config)
    hysteresis = simulate_hysteresis(rows, Decimal("30"), Decimal("-30"), Decimal("20"), Decimal("-20"), config)
    persistence, delays = simulate_minimum_persistence(rows, 2)
    smoothed = simulate_score_smoothing(rows, 2, config)
    scenario_rows, scenario_summary, state_rows = scenario_analysis(rows, config)
    one_day = one_day_state_summary(rows)

    assert deadband[2] == "NEUTRAL"
    assert hysteresis[0] == "BULLISH"
    assert persistence[3] == "NEUTRAL"
    assert persistence[4] == "BEARISH"
    assert delays == [Decimal("1")]
    assert smoothed[3] == "NEUTRAL"
    assert len(scenario_rows) == 9
    assert "PERSISTENCE_2" in scenario_summary
    assert len(state_rows) == len(rows) * 9
    assert one_day["BULLISH"]["isolated_one_day_count"] >= 1


def test_minimum_persistence_state_machine_has_no_lookahead() -> None:
    rows = [
        regime_row("2024-01-01", "BULLISH", "45", "29.25"),
        regime_row("2024-01-02", "BEARISH", "-45", "-29.25"),
        regime_row("2024-01-03", "BEARISH", "-46", "-29.9"),
        regime_row("2024-01-04", "BULLISH", "46", "29.9"),
        regime_row("2024-01-05", "BULLISH", "47", "30.55"),
    ]
    full, _full_delays = simulate_minimum_persistence(rows, 2)

    for index in range(1, len(rows) + 1):
        prefix, _prefix_delays = simulate_minimum_persistence(rows[:index], 2)
        assert prefix[-1] == full[index - 1]


def test_report_generation_preserves_baseline_hashes_and_has_no_outcome_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_small_regime_fixture(data_dir)
    config = MarketRegimeStabilityAuditConfig(data_dir=data_dir)
    hashes_before = {
        "regime": file_sha256(config.regime_dataset_path),
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
    }

    report = build_market_regime_stability_audit(config=config)
    markdown_path = tmp_path / "docs" / "market-regime-stability-audit.md"
    write_market_regime_stability_audit_markdown(report, markdown_path)

    assert report["audit"]["audit_version"] == "MARKET_REGIME_AUDIT_V1"
    assert report["regression"]["market_regime_dataset_unchanged"] is True
    assert report["regression"]["daily_features_v1_unchanged"] is True
    assert report["safety"]["future_outcome_fields_used"] == 0
    assert report["safety"]["orders_placed"] == 0
    assert report["safety"]["prohibited_outcome_fields_in_regime_input"] == []
    assert report["ready_for_review"] is True
    assert file_sha256(config.regime_dataset_path) == hashes_before["regime"]
    assert file_sha256(config.feature_dataset_path) == hashes_before["feature"]
    assert file_sha256(config.candidate_dataset_path) == hashes_before["candidate"]
    assert file_sha256(config.setup_dataset_path) == hashes_before["setup"]
    assert config.summary_path.exists()
    assert config.direct_flips_path.exists()
    assert config.scenario_state_series_path.exists()
    assert markdown_path.exists()


def regime_row(
    trading_date: str,
    regime_state: str,
    normalized_score: str,
    raw_score: str,
    *,
    available_weight: str = "65",
    confidence_score: str = "60",
    confidence_state: str = "MEDIUM",
    trend: str = "BULLISH",
    trend_contribution: str = "18",
    breadth: str = "BULLISH",
    breadth_contribution: str = "12",
    sector: str = "BULLISH",
    sector_contribution: str = "9",
    warnings: str = "NIFTY500_MEMBERSHIP_PARTIAL_HISTORY",
) -> dict[str, str]:
    return {
        "trading_date": trading_date,
        "regime_version": "MARKET_REGIME_V1",
        "config_hash": MarketRegimeConfig().config_hash(),
        "regime_state": regime_state,
        "regime_score_normalized": normalized_score,
        "regime_score_raw": raw_score,
        "available_weight_pct": available_weight,
        "confidence_score": confidence_score,
        "confidence_state": confidence_state,
        "component_agreement_pct": "100",
        "nifty_trend_status": "AVAILABLE",
        "nifty_trend_state": trend,
        "nifty_trend_contribution": trend_contribution,
        "nifty50_return_5d": "0.02",
        "nifty50_return_20d": "0.04",
        "nifty50_distance_sma20_pct": "0.02",
        "nifty50_distance_sma50_pct": "0.03",
        "nifty50_distance_sma200_pct": "0.05",
        "nifty50_sma20_slope_10d_pct": "0.01",
        "breadth_status": "PARTIAL",
        "breadth_state": breadth,
        "breadth_contribution": breadth_contribution,
        "breadth_coverage_pct": "95",
        "sector_status": "AVAILABLE",
        "sector_state": sector,
        "sector_contribution": sector_contribution,
        "sector_coverage_pct": "100",
        "vix_status": "UNAVAILABLE",
        "vix_state": "UNAVAILABLE",
        "vix_contribution": "",
        "global_gift_status": "UNAVAILABLE",
        "global_gift_state": "UNAVAILABLE",
        "global_gift_contribution": "",
        "intraday_status": "UNAVAILABLE",
        "intraday_state": "UNAVAILABLE",
        "intraday_contribution": "",
        "warnings": warnings,
    }


def write_small_regime_fixture(data_dir: Path) -> None:
    start = date(2024, 1, 1)
    rows = [
        regime_row(str(start), "BULLISH", "60", "39", trend="BULLISH", trend_contribution="18", breadth="BULLISH", breadth_contribution="12", sector="BULLISH", sector_contribution="9"),
        regime_row(str(start + timedelta(days=1)), "BEARISH", "-60", "-39", trend="BEARISH", trend_contribution="-18", breadth="BEARISH", breadth_contribution="-12", sector="BEARISH", sector_contribution="-9"),
        regime_row(str(start + timedelta(days=2)), "NEUTRAL", "0", "0", trend="NEUTRAL", trend_contribution="0", breadth="NEUTRAL", breadth_contribution="0", sector="NEUTRAL", sector_contribution="0"),
        regime_row(str(start + timedelta(days=3)), "BULLISH", "34", "22.1", trend="BULLISH", trend_contribution="18", breadth="NEUTRAL", breadth_contribution="0", sector="NEUTRAL", sector_contribution="0"),
    ]
    regime_path = data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz"
    write_gzip_csv(regime_path, rows, list(rows[0].keys()))
    write_gzip_csv(data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz", [{"trading_date": "2024-01-01"}], ["trading_date"])
    write_gzip_csv(data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz", [{"trading_date": "2024-01-01"}], ["trading_date"])
    write_gzip_csv(data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz", [{"trading_date": "2024-01-01"}], ["trading_date"])


def write_gzip_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
