from __future__ import annotations

import csv
import gzip
import json
from datetime import date, timedelta
from decimal import Decimal

from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig
from app.strategy.momentum_candidates import (
    CANDIDATE_OUTPUT_FIELDS,
    MomentumCandidateEngineConfig,
    build_momentum_candidate_engine,
    daily_count_rows,
    evaluate_candidate_row,
    rank_candidate_rows_by_date,
    write_momentum_candidate_markdown,
)


def test_config_version_and_hash_are_stable():
    config = MomentumCandidateConfig()

    assert config.candidate_version == MOMENTUM_CANDIDATES_VERSION
    assert config.config_hash() == MomentumCandidateConfig().config_hash()
    assert config.liquidity.median_traded_value_20d_min == Decimal("100000000")


def test_price_liquidity_series_and_research_gates():
    config = MomentumCandidateConfig()

    assert "PRICE_BELOW_MINIMUM" in evaluate_candidate_row(base_feature_row(), config=config, price=Decimal("99"))["rejection_reasons"]
    assert "PRICE_ABOVE_HARD_LIMIT" in evaluate_candidate_row(base_feature_row(), config=config, price=Decimal("7000.01"))["rejection_reasons"]

    preferred = evaluate_candidate_row(base_feature_row(), config=config, price=Decimal("6000"))
    assert preferred["price_range_status"] == "ABOVE_PREFERRED_PRICE_RANGE"
    assert "ABOVE_PREFERRED_PRICE_RANGE" in preferred["warning_flags"]

    low_liquidity = base_feature_row(median_traded_value_20d="99999999")
    assert "LOW_LIQUIDITY" in evaluate_candidate_row(low_liquidity, config=config, price=Decimal("250"))["rejection_reasons"]

    non_standard = base_feature_row(series="BE")
    assert "NON_STANDARD_SERIES" in evaluate_candidate_row(non_standard, config=config, price=Decimal("250"))["rejection_reasons"]

    blocked = base_feature_row(feature_null_reasons="return_5d:CORPORATE_ACTION_LOOKBACK_BLOCKED:fixture")
    assert evaluate_candidate_row(blocked, config=config, price=Decimal("250"))["candidate_state"] == "UNAVAILABLE"


def test_emerging_confirmed_both_and_rejected_classifications():
    config = MomentumCandidateConfig()

    emerging = evaluate_candidate_row(
        base_feature_row(
            return_3d="0.012",
            return_5d="0.018",
            return_10d="0.005",
            return_20d="0.015",
            relative_volume_20d="1.25",
            up_days_ratio_10="0.6",
            distance_to_prior_20d_high_pct="-0.005",
            relative_return_5d_vs_nifty500="0.01",
        ),
        config=config,
        price=Decimal("250"),
    )
    assert emerging["candidate_state"] == "EMERGING"
    assert emerging["emerging_eligible"] is True
    assert emerging["confirmed_eligible"] is False

    confirmed = evaluate_candidate_row(
        base_feature_row(
            return_1d="0.012",
            return_3d="0.02",
            return_5d="0.04",
            return_10d="0.06",
            return_20d="0.09",
            relative_volume_20d="1.7",
            up_days_ratio_10="0.7",
            up_days_ratio_20="0.65",
            above_prior_20d_high="True",
            relative_return_20d_vs_nifty500="0.03",
        ),
        config=config,
        price=Decimal("250"),
    )
    assert confirmed["candidate_state"] == "CONFIRMED"
    assert confirmed["both_eligible"] is True

    rejected = evaluate_candidate_row(
        base_feature_row(return_3d="-0.02", return_5d="-0.03", return_10d="-0.04", return_20d="-0.05", relative_volume_20d="0.8"),
        config=config,
        price=Decimal("250"),
    )
    assert rejected["candidate_state"] == "REJECTED"
    assert "LOW_MULTI_DAY_MOMENTUM" in rejected["rejection_reasons"]
    assert "LOW_RELATIVE_VOLUME" in rejected["rejection_reasons"]


def test_benchmark_missing_sector_current_only_breakout_extension_and_volatility_metadata():
    row = evaluate_candidate_row(
        base_feature_row(
            relative_return_5d_vs_nifty500="",
            relative_return_20d_vs_nifty500="",
            sector_mapping_status="CURRENT_ONLY",
            return_1d="0.08",
            return_5d="0.12",
            atr_percent_14="0.01",
            distance_from_sma_20_pct="0.20",
            distance_to_prior_20d_high_pct="-0.002",
        ),
        config=MomentumCandidateConfig(),
        price=Decimal("250"),
    )

    assert "BENCHMARK_CONTEXT_UNAVAILABLE" in row["warning_flags"]
    assert row["sector_context_status"] == "CURRENT_ONLY"
    assert row["breakout_context"] == "TESTING_20D_HIGH"
    assert row["extension_status"] == "EXTREME"
    assert row["volatility_context"] == "NORMAL"


def test_cross_sectional_ranks_use_only_same_date_rows():
    config = MomentumCandidateConfig()
    date_one = [
        evaluate_candidate_row(base_feature_row(symbol="AAA", return_5d="0.03", relative_volume_20d="1.5"), config=config, price=Decimal("250")),
        evaluate_candidate_row(base_feature_row(symbol="BBB", return_5d="0.08", relative_volume_20d="2.5"), config=config, price=Decimal("250")),
    ]
    rows_by_date = {"2024-01-31": date_one}
    rank_candidate_rows_by_date(rows_by_date)
    rank_before = {row["symbol"]: row["emerging_rank"] for row in rows_by_date["2024-01-31"]}

    rows_by_date["2024-02-01"] = [
        evaluate_candidate_row(base_feature_row(symbol="ZZZ", trading_date="2024-02-01", return_5d="0.50", relative_volume_20d="5.0"), config=config, price=Decimal("250"))
    ]
    rank_candidate_rows_by_date(rows_by_date)

    assert {row["symbol"]: row["emerging_rank"] for row in rows_by_date["2024-01-31"]} == rank_before


def test_daily_summary_counts_and_rejected_row_retention():
    config = MomentumCandidateConfig()
    rows = [
        evaluate_candidate_row(base_feature_row(symbol="AAA"), config=config, price=Decimal("250")),
        evaluate_candidate_row(base_feature_row(symbol="BBB", return_3d="-0.01", return_5d="-0.02", relative_volume_20d="0.7"), config=config, price=Decimal("250")),
        evaluate_candidate_row(base_feature_row(symbol="CCC", feature_null_reasons="return_5d:CORPORATE_ACTION_LOOKBACK_BLOCKED:fixture"), config=config, price=Decimal("250")),
    ]
    counts = daily_count_rows({"2024-01-31": rows})[0]

    assert counts["universe_count"] == 3
    assert counts["rejected_count"] >= 1
    assert counts["unavailable_count"] >= 1
    assert any(row["candidate_state"] == "REJECTED" for row in rows)


def test_full_report_generation_and_no_future_outcome_fields(tmp_path):
    data_dir = tmp_path / "data"
    sessions = [date(2024, 1, 29), date(2024, 1, 30), date(2024, 1, 31)]
    feature_rows = [
        base_feature_row(symbol="AAA", trading_date=session.isoformat(), source_file=f"nse_adjusted_daily_{session:%Y%m%d}.csv")
        for session in sessions
    ]
    feature_rows.append(
        base_feature_row(
            symbol="BBB",
            trading_date=sessions[-1].isoformat(),
            source_file=f"nse_adjusted_daily_{sessions[-1]:%Y%m%d}.csv",
            return_3d="-0.02",
            return_5d="-0.03",
            relative_volume_20d="0.6",
        )
    )
    feature_rows.append(
        base_feature_row(
            symbol="CCC",
            trading_date=sessions[-1].isoformat(),
            source_file=f"nse_adjusted_daily_{sessions[-1]:%Y%m%d}.csv",
            feature_null_reasons="return_5d:CORPORATE_ACTION_LOOKBACK_BLOCKED:fixture",
        )
    )
    feature_rows.append(
        base_feature_row(
            symbol="DDD",
            trading_date=sessions[-1].isoformat(),
            source_file=f"nse_adjusted_daily_{sessions[-1]:%Y%m%d}.csv",
            return_1d="0.015",
            return_5d="0.05",
            return_10d="0.07",
            return_20d="0.09",
            relative_volume_20d="1.8",
            above_prior_20d_high="True",
        )
    )
    write_feature_dataset(data_dir, feature_rows)
    for session in sessions:
        write_adjusted_file(data_dir, session, [("AAA", "250"), ("BBB", "250"), ("CCC", "250"), ("DDD", "250")])

    report = build_momentum_candidate_engine(
        config=MomentumCandidateEngineConfig(data_dir=data_dir, start_date=sessions[0], end_date=sessions[-1])
    )
    write_momentum_candidate_markdown(report, tmp_path / "docs" / "momentum-candidate-engine.md")

    assert report["ready_for_review"] is True
    assert report["generation"]["total_evaluated_rows"] == 6
    assert report["generation"]["rejected_count"] >= 1
    assert report["integrity"]["daily_features_v1_unchanged"] is True
    assert not any(field.startswith("future_") for field in CANDIDATE_OUTPUT_FIELDS)
    assert "winner" not in ";".join(CANDIDATE_OUTPUT_FIELDS).lower()
    assert report["safety"]["orders_placed"] == 0
    assert (data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz").exists()
    assert json.loads((data_dir / "reports" / "momentum_candidate_summary.json").read_text(encoding="utf-8"))["ready_for_review"] is True


def base_feature_row(**overrides):
    row = {
        "trading_date": "2024-01-31",
        "symbol": "RELIANCE",
        "isin": "INERELIANCE",
        "universe_name": "NIFTY_500",
        "universe_membership_status": "PARTIAL_HISTORY",
        "universe_membership_confidence": "OFFICIAL_EVENTS_PARTIAL",
        "universe_version": "fixture",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": "",
        "benchmark_context_version": "BENCHMARK_CONTEXT_V1",
        "sector_context_version": "SECTOR_CONTEXT_V1",
        "adjustment_methodology": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "exclusion_policy": "CORPORATE_ACTION_EXCLUSIONS_V1",
        "availability_time": "EOD",
        "decision_input_time": "NEXT_SESSION_DECISION_INPUT",
        "timeframe": "DAILY_EOD",
        "source_file": "nse_adjusted_daily_20240131.csv",
        "series": "EQ",
        "feature_status": "READY",
        "feature_null_reasons": "",
        "return_1d": "0.01",
        "return_3d": "0.02",
        "return_5d": "0.03",
        "return_10d": "0.04",
        "return_20d": "0.05",
        "relative_volume_5d": "1.30",
        "relative_volume_20d": "1.35",
        "up_days_ratio_10": "0.60",
        "up_days_ratio_20": "0.55",
        "median_traded_value_20d": "150000000",
        "atr_percent_14": "0.02",
        "relative_return_5d_vs_nifty500": "0.01",
        "relative_return_20d_vs_nifty500": "0.02",
        "prior_high_20d": "250",
        "distance_to_prior_20d_high_pct": "-0.005",
        "distance_from_sma_20_pct": "0.04",
        "above_prior_20d_high": "False",
        "above_prior_52w_high": "",
        "intraday_high_above_prior_20d_high": "True",
        "sector_mapping_status": "UNAVAILABLE",
    }
    row.update(overrides)
    return row


def write_feature_dataset(data_dir, rows):
    path = data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_adjusted_file(data_dir, session, rows):
    path = data_dir / "research" / "adjusted" / "daily" / "nse" / f"{session:%Y}" / f"{session:%m}" / f"nse_adjusted_daily_{session:%Y%m%d}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["trading_date", "symbol", "series", "adjusted_close"])
        writer.writeheader()
        for symbol, close in rows:
            writer.writerow({"trading_date": session.isoformat(), "symbol": symbol, "series": "EQ", "adjusted_close": close})
