from __future__ import annotations

import csv
import gzip
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.regime.breadth import BreadthAggregate, finalize_breadth_component, update_breadth_aggregate
from app.regime.market_regime import (
    MarketRegimeEngineConfig,
    classify_regime_state,
    transition_matrix_rows,
    build_historical_market_regimes,
    score_continuity_summary,
    streak_summary_rows,
    unavailable_component,
    write_historical_market_regime_markdown,
)
from app.regime.regime_config import (
    BreadthRules,
    MarketRegimeConfig,
    RegimeClassificationRules,
    SectorParticipationRules,
)
from app.regime.regime_confidence import calculate_regime_confidence, component_agreement
from app.regime.sector_participation import SectorIndexBar, build_sector_participation_components
from app.regime.trend import BenchmarkBar, build_nifty_trend_components
from app.regime.volatility import VixBar, build_india_vix_components, unavailable_india_vix_component


def test_score_normalization_missing_components_and_boundaries() -> None:
    config = MarketRegimeConfig()

    assert classify_regime_state(
        normalized_score=Decimal("30"),
        available_weight_pct=Decimal("60"),
        config=config,
    ) == ("CLASSIFIED", "BULLISH")
    assert classify_regime_state(
        normalized_score=Decimal("29"),
        available_weight_pct=Decimal("60"),
        config=config,
    ) == ("CLASSIFIED", "NEUTRAL")
    assert classify_regime_state(
        normalized_score=Decimal("-30"),
        available_weight_pct=Decimal("60"),
        config=config,
    ) == ("CLASSIFIED", "BEARISH")
    assert classify_regime_state(
        normalized_score=Decimal("80"),
        available_weight_pct=Decimal("59.99"),
        config=config,
    ) == ("INSUFFICIENT_COMPONENT_COVERAGE", "UNAVAILABLE")

    missing = unavailable_component("GLOBAL_GIFT", date(2024, 1, 1), Decimal("15"), "NO_SAFE_HISTORY")
    assert missing["component_status"] == "UNAVAILABLE"
    assert missing["signed_contribution"] is None
    assert missing["available_weight"] == 0


def test_nifty_trend_state_and_no_lookahead() -> None:
    start = date(2024, 1, 1)
    bars = [BenchmarkBar(start + timedelta(days=index), Decimal("100") + Decimal(index)) for index in range(230)]
    base = build_nifty_trend_components(bars, target_weight=Decimal("30"), rules=MarketRegimeConfig().trend)
    with_future = build_nifty_trend_components(
        [*bars, BenchmarkBar(start + timedelta(days=230), Decimal("50"))],
        target_weight=Decimal("30"),
        rules=MarketRegimeConfig().trend,
    )
    target_date = start + timedelta(days=220)

    assert base[target_date] == with_future[target_date]
    assert base[target_date]["component_state"] in {"BULLISH", "STRONGLY_BULLISH"}
    assert base[target_date]["signed_contribution"] > 0


def test_breadth_advancers_decliners_coverage_and_no_future_dependency() -> None:
    aggregate = BreadthAggregate()
    for feature in [
        feature_row("AAA", "0.02", "0.01", "0.02", "0.03", "0.04"),
        feature_row("BBB", "0.01", "0.02", "0.03", "0.02", "0.03"),
        feature_row("CCC", "-0.01", "-0.02", "0.01", "0.01", "0.02"),
        feature_row("DDD", "0", "0.01", "-0.01", "-0.01", "-0.02"),
    ]:
        update_breadth_aggregate(aggregate, feature)

    component = finalize_breadth_component(
        date(2024, 1, 5),
        aggregate,
        expected_members=4,
        membership_status="PARTIAL_HISTORY",
        target_weight=Decimal("20"),
        rules=replace(BreadthRules(), minimum_usable_members=1, minimum_breadth_coverage_pct=Decimal("50")),
    )

    assert component["component_status"] == "PARTIAL"
    assert component["evidence"]["advancers"] == 2
    assert component["evidence"]["decliners"] == 1
    assert component["evidence"]["unchanged"] == 1
    assert component["evidence"]["breadth_coverage_pct"] == Decimal("100")
    assert component["component_state"] in {"BULLISH", "STRONGLY_BULLISH"}


def test_sector_index_participation_partial_coverage() -> None:
    start = date(2024, 1, 1)
    bars = []
    for sector_index in range(10):
        for day_index in range(25):
            bars.append(
                SectorIndexBar(
                    trading_date=start + timedelta(days=day_index),
                    sector_index_id=f"SECTOR_{sector_index}",
                    close=Decimal("100") + Decimal(day_index) + Decimal(sector_index),
                )
            )
    components = build_sector_participation_components(
        bars,
        expected_sector_indexes=20,
        target_weight=Decimal("15"),
        rules=replace(
            SectorParticipationRules(),
            minimum_available_sector_indexes=5,
            minimum_sector_coverage_pct=Decimal("50"),
        ),
    )
    component = components[start + timedelta(days=24)]

    assert component["component_status"] == "PARTIAL"
    assert component["component_state"] in {"BULLISH", "STRONGLY_BULLISH"}
    assert component["evidence"]["sectors_available"] == 10
    assert component["evidence"]["sector_coverage_pct"] == Decimal("50")


def test_india_vix_available_and_unavailable_paths() -> None:
    start = date(2024, 1, 1)
    bars = [VixBar(start + timedelta(days=index), Decimal("20") - Decimal(index) / Decimal("2")) for index in range(25)]
    components = build_india_vix_components(bars, target_weight=Decimal("10"), rules=MarketRegimeConfig().india_vix)
    component = components[start + timedelta(days=24)]
    missing = unavailable_india_vix_component(start, target_weight=Decimal("10"))

    assert component["component_state"] in {"RISK_ON", "STRONGLY_RISK_ON"}
    assert component["signed_contribution"] > 0
    assert missing["component_status"] == "UNAVAILABLE"
    assert missing["signed_contribution"] is None


def test_confidence_uses_agreement_and_availability_not_score_magnitude_only() -> None:
    positive = component("NIFTY_TREND", Decimal("30"), Decimal("18"), "BULLISH")
    second_positive = component("NIFTY500_BREADTH", Decimal("20"), Decimal("12"), "BULLISH")
    negative = component("SECTOR_INDEX_PARTICIPATION", Decimal("15"), Decimal("-9"), "BEARISH")

    agreed = calculate_regime_confidence(
        [positive, second_positive],
        available_weight_pct=Decimal("50"),
        rules=MarketRegimeConfig().confidence,
    )
    mixed = calculate_regime_confidence(
        [positive, negative],
        available_weight_pct=Decimal("50"),
        rules=MarketRegimeConfig().confidence,
    )

    assert component_agreement([positive, second_positive])["dominant_direction"] == "POSITIVE"
    assert agreed["confidence_score"] > mixed["confidence_score"]


def test_regime_streaks_transitions_and_score_continuity() -> None:
    rows = [
        regime_row("2024-01-01", "BULLISH", "35"),
        regime_row("2024-01-02", "BULLISH", "40"),
        regime_row("2024-01-03", "NEUTRAL", "10"),
        regime_row("2024-01-04", "BEARISH", "-35"),
        regime_row("2024-01-05", "BEARISH", "-32"),
    ]
    _, streaks = streak_summary_rows(rows)
    transitions, transition_summary = transition_matrix_rows(rows)
    continuity = score_continuity_summary(rows)

    assert streaks["BULLISH"]["max"] == 2
    assert streaks["BEARISH"]["max"] == 2
    assert any(row["from_state"] == "BULLISH" and row["to_state"] == "NEUTRAL" and row["count"] == 1 for row in transitions)
    assert transition_summary["direct_bullish_bearish_flips"] == 0
    assert continuity["max"] == "45.0000"
    assert continuity["pathological_regime_flipping_detected"] is False


def test_report_generation_input_immutability_and_no_outcome_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_small_market_regime_fixture(data_dir)
    regime_config = replace(
        MarketRegimeConfig(),
        classification=replace(RegimeClassificationRules(), minimum_available_weight_pct=Decimal("30")),
        breadth=replace(BreadthRules(), minimum_usable_members=1, minimum_breadth_coverage_pct=Decimal("50")),
        sector=replace(SectorParticipationRules(), minimum_available_sector_indexes=2, minimum_sector_coverage_pct=Decimal("50")),
    )

    report = build_historical_market_regimes(
        config=MarketRegimeEngineConfig(
            data_dir=data_dir,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 25),
            regime_config=regime_config,
        )
    )
    markdown_path = tmp_path / "docs" / "historical-market-regime-engine.md"
    write_historical_market_regime_markdown(report, markdown_path)

    assert report["methodology"]["regime_version"] == "MARKET_REGIME_V1"
    assert report["generation"]["full_generation_completed"] is True
    assert report["generation"]["total_regime_rows"] == 25
    assert report["regression"]["feature_dataset_unchanged"] is True
    assert report["regression"]["candidate_dataset_unchanged"] is True
    assert report["regression"]["setup_dataset_unchanged"] is True
    assert report["safety"]["future_outcome_fields_used"] == 0
    assert report["safety"]["orders_placed"] == 0
    assert (data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz").exists()
    assert markdown_path.exists()


def feature_row(symbol: str, return_1d: str, sma20: str, sma50: str, return_5d: str, return_20d: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "return_1d": return_1d,
        "distance_from_sma_20_pct": sma20,
        "distance_from_sma_50_pct": sma50,
        "return_5d": return_5d,
        "return_20d": return_20d,
    }


def component(name: str, target_weight: Decimal, contribution: Decimal, state: str) -> dict[str, object]:
    return {
        "component_name": name,
        "component_status": "AVAILABLE",
        "component_state": state,
        "target_weight": target_weight,
        "available_weight": target_weight,
        "signed_contribution": contribution,
        "coverage_metadata": {"coverage_pct": Decimal("100")},
        "warnings": (),
    }


def regime_row(trading_date: str, state: str, score: str) -> dict[str, object]:
    return {
        "trading_date": trading_date,
        "regime_state": state,
        "regime_score_normalized": score,
        "confidence_state": "MEDIUM",
    }


def write_small_market_regime_fixture(data_dir: Path) -> None:
    calendar_path = data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"
    benchmark_path = data_dir / "reference" / "nse" / "indices" / "normalized" / "benchmark_daily.csv"
    sector_path = data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_daily.csv"
    inventory_path = data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_inventory.csv"
    membership_path = data_dir / "reference" / "nifty500" / "history" / "membership_periods.csv"
    coverage_path = data_dir / "reference" / "nifty500" / "history" / "membership_coverage.json"
    feature_path = data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"
    candidate_path = data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"
    setup_path = data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"

    dates = [date(2024, 1, 1) + timedelta(days=index) for index in range(25)]
    write_plain_csv(
        calendar_path,
        ["trading_date", "session_type", "source_reference", "source_available", "notes"],
        [{"trading_date": day, "session_type": "NORMAL", "source_reference": "fixture", "source_available": "True", "notes": ""} for day in dates],
    )
    write_plain_csv(
        benchmark_path,
        ["trading_date", "benchmark_id", "index_name", "open", "high", "low", "close"],
        [
            {
                "trading_date": day,
                "benchmark_id": "NIFTY_50",
                "index_name": "NIFTY 50",
                "open": "",
                "high": "",
                "low": "",
                "close": Decimal("100") + Decimal(index),
            }
            for index, day in enumerate(dates)
        ],
    )
    sector_rows = []
    for sector in ("SECTOR_A", "SECTOR_B"):
        for index, day in enumerate(dates):
            sector_rows.append(
                {
                    "trading_date": day,
                    "sector_index_id": sector,
                    "index_name": sector,
                    "close": Decimal("100") + Decimal(index),
                }
            )
    write_plain_csv(sector_path, ["trading_date", "sector_index_id", "index_name", "close"], sector_rows)
    write_plain_csv(
        inventory_path,
        ["sector_index_id", "index_name", "usable"],
        [
            {"sector_index_id": "SECTOR_A", "index_name": "SECTOR_A", "usable": "True"},
            {"sector_index_id": "SECTOR_B", "index_name": "SECTOR_B", "usable": "True"},
        ],
    )
    write_plain_csv(
        membership_path,
        ["index_name", "symbol", "isin", "valid_from", "valid_to", "reconstruction_method", "source_confidence", "provenance"],
        [
            {
                "index_name": "NIFTY 500",
                "symbol": symbol,
                "isin": "",
                "valid_from": "2024-01-01",
                "valid_to": "2024-01-25",
                "reconstruction_method": "FIXTURE",
                "source_confidence": "OFFICIAL_EVENTS_PARTIAL",
                "provenance": "fixture",
            }
            for symbol in ("AAA", "BBB", "CCC", "DDD")
        ],
    )
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text('{"membership_periods":{"coverage_start":"2024-01-01","coverage_end":"2024-01-25"}}', encoding="utf-8")
    feature_rows = []
    for day in dates:
        feature_rows.extend(
            [
                {"trading_date": day, **feature_row("AAA", "0.02", "0.01", "0.02", "0.03", "0.04")},
                {"trading_date": day, **feature_row("BBB", "0.01", "0.02", "0.03", "0.02", "0.03")},
                {"trading_date": day, **feature_row("CCC", "-0.01", "-0.02", "0.01", "0.01", "0.02")},
                {"trading_date": day, **feature_row("DDD", "0", "0.01", "-0.01", "-0.01", "-0.02")},
            ]
        )
    write_gzip_fixture_csv(
        feature_path,
        ["trading_date", "symbol", "return_1d", "distance_from_sma_20_pct", "distance_from_sma_50_pct", "return_5d", "return_20d"],
        feature_rows,
    )
    write_gzip_fixture_csv(candidate_path, ["trading_date"], [{"trading_date": "2024-01-01"}])
    write_gzip_fixture_csv(setup_path, ["trading_date"], [{"trading_date": "2024-01-01"}])


def write_plain_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip_fixture_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
