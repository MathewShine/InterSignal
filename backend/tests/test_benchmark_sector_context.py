from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal

from app.features.base import AdjustedDailyBar, DailyFeatureConfig
from app.features.relative_strength import LocalOfficialIndexContextProvider
from app.providers.indices.base import canonical_index_id
from app.providers.indices.nifty_indices import date_windows, parse_index_history_row
from app.services.daily_feature_engine import (
    FeatureRowBuilder,
    MembershipPeriod,
    ResearchEligibilityIndex,
    build_symbol_feature_cache,
)


def test_official_index_parser_normalizes_nse_payload():
    record = parse_index_history_row(
        {
            "EOD_INDEX_NAME": "NIFTY 500",
            "EOD_OPEN_INDEX_VAL": 1000.1,
            "EOD_HIGH_INDEX_VAL": 1005.2,
            "EOD_LOW_INDEX_VAL": 995.3,
            "EOD_CLOSE_INDEX_VAL": 1001.25,
            "EOD_TIMESTAMP": "07-SEP-2026",
            "HI_TIMESTAMP": "2026-09-06T18:30:00.000Z",
        },
        index_id="NIFTY_500",
        expected_index_name="NIFTY 500",
        source_reference="fixture",
    )

    assert record is not None
    assert record.trading_date == date(2026, 9, 7)
    assert record.index_id == "NIFTY_500"
    assert record.close == Decimal("1001.25")
    assert canonical_index_id("NIFTY OIL & GAS") == "NIFTY_OIL_AND_GAS"


def test_date_windows_keep_nse_requests_below_long_range_limit():
    windows = list(date_windows(date(2024, 1, 1), date(2024, 4, 15), 89))

    assert windows == [(date(2024, 1, 1), date(2024, 3, 30)), (date(2024, 3, 31), date(2024, 4, 15))]


def test_benchmark_return_requires_complete_trading_session_window(tmp_path):
    data_dir = tmp_path / "data"
    sessions = make_sessions(8)
    write_benchmark_context(data_dir, sessions, missing_nifty500_date=sessions[4])
    context = LocalOfficialIndexContextProvider(data_dir=data_dir, trading_sessions=sessions)

    assert context.benchmark_return_for("NIFTY_500", sessions[5], 1) is None
    assert context.benchmark_return_for("NIFTY_500", sessions[7], 2) == Decimal("1007") / Decimal("1005") - Decimal("1")
    assert context.benchmark_return_for("NIFTY_50", sessions[7], 5) == Decimal("2007") / Decimal("2002") - Decimal("1")


def test_stock_vs_benchmark_relative_return_and_corporate_action_blocking(tmp_path):
    data_dir = tmp_path / "data"
    sessions = make_sessions(30)
    bars = make_bars("RELIANCE", sessions)
    write_benchmark_context(data_dir, sessions)
    context = LocalOfficialIndexContextProvider(data_dir=data_dir, trading_sessions=sessions)

    row = build_row(bars, 25, sessions, context)
    expected_stock_return = bars[25].close / bars[20].close - Decimal("1")
    expected_benchmark_return = Decimal("1025") / Decimal("1020") - Decimal("1")

    assert row["benchmark_return_5d"] == expected_benchmark_return
    assert row["relative_return_5d_vs_nifty500"] == expected_stock_return - expected_benchmark_return

    blocked = build_row(
        bars,
        25,
        sessions,
        context,
        eligibility_rows=[
            {
                "symbol": "RELIANCE",
                "start_date": sessions[23].isoformat(),
                "end_date": sessions[23].isoformat(),
                "eligibility_status": "EXCLUDE_SECURITY_RANGE",
                "reason_code": "fixture_ca_block",
                "source_event_id": "fixture-event",
                "confidence": "HIGH",
            }
        ],
    )
    assert blocked["return_5d"] is None
    assert blocked["relative_return_5d_vs_nifty500"] is None
    assert "relative_return_5d_vs_nifty500:CORPORATE_ACTION_LOOKBACK_BLOCKED:fixture_ca_block" in blocked["feature_null_reasons"]


def test_sector_mapping_effective_dates_current_only_rejection_and_sector_relative_return(tmp_path):
    data_dir = tmp_path / "data"
    sessions = make_sessions(30)
    write_sector_context(data_dir, sessions)
    write_sector_mapping(
        data_dir,
        [
            ("RELIANCE", "NIFTY_IT", sessions[0].isoformat(), sessions[-1].isoformat(), "POINT_IN_TIME_VERIFIED"),
            ("TCS", "NIFTY_IT", "", "", "CURRENT_ONLY"),
            ("FUTURE", "NIFTY_IT", sessions[10].isoformat(), sessions[-1].isoformat(), "POINT_IN_TIME_VERIFIED"),
        ],
    )
    context = LocalOfficialIndexContextProvider(data_dir=data_dir, trading_sessions=sessions)

    bars = make_bars("RELIANCE", sessions)
    row = build_row(bars, 25, sessions, context)
    expected_sector_return = Decimal("3025") / Decimal("3020") - Decimal("1")
    expected_stock_return = bars[25].close / bars[20].close - Decimal("1")
    assert row["sector_return_5d"] == expected_sector_return
    assert row["relative_return_5d_vs_sector"] == expected_stock_return - expected_sector_return

    current_only = build_row(make_bars("TCS", sessions), 25, sessions, context)
    assert current_only["sector_mapping_status"] == "CURRENT_ONLY"
    assert current_only["relative_return_5d_vs_sector"] is None
    assert "sector_relative_features:CURRENT_ONLY_MAPPING_NOT_USED" in current_only["feature_null_reasons"]

    future = context.sector_mapping_for("FUTURE", sessions[5])
    assert future.mapping_status == "UNAVAILABLE"


def make_sessions(count: int) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=offset) for offset in range(count)]


def make_bars(symbol: str, sessions: list[date]) -> list[AdjustedDailyBar]:
    return [
        AdjustedDailyBar(
            trading_date=session,
            symbol=symbol,
            isin=f"INE{symbol}",
            open=Decimal(100 + index),
            high=Decimal(102 + index),
            low=Decimal(98 + index),
            close=Decimal(100 + index),
            volume=Decimal("1000"),
            source_file="fixture.csv",
            source="fixture",
            research_usability_status="ADJUSTED_READY",
            adjustment_methodology_version="PRICE_ADJUSTED_STRUCTURAL_V1",
            provenance="fixture",
        )
        for index, session in enumerate(sessions)
    ]


def build_row(
    bars: list[AdjustedDailyBar],
    index: int,
    sessions: list[date],
    context: LocalOfficialIndexContextProvider,
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
        sector="fixture",
        feature_cache=build_symbol_feature_cache(bars, DailyFeatureConfig()),
        eligibility_index=ResearchEligibilityIndex(eligibility_rows or [], sessions),
        trading_sessions=sessions,
        trading_session_index={session: offset for offset, session in enumerate(sessions)},
        feature_config=DailyFeatureConfig(),
        relative_strength_context=context,
    ).build()


def write_benchmark_context(data_dir, sessions, missing_nifty500_date=None):
    rows = []
    for index, session in enumerate(sessions):
        if session != missing_nifty500_date:
            rows.append(index_row(session, "benchmark_id", "NIFTY_500", "NIFTY 500", Decimal(1000 + index)))
        rows.append(index_row(session, "benchmark_id", "NIFTY_50", "NIFTY 50", Decimal(2000 + index)))
    write_csv(
        data_dir / "reference" / "nse" / "indices" / "normalized" / "benchmark_daily.csv",
        rows,
        ["trading_date", "benchmark_id", "index_name", "open", "high", "low", "close", "source", "source_reference", "source_date", "methodology", "benchmark_context_version"],
    )


def write_sector_context(data_dir, sessions):
    rows = [index_row(session, "sector_index_id", "NIFTY_IT", "NIFTY IT", Decimal(3000 + index)) for index, session in enumerate(sessions)]
    write_csv(
        data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_daily.csv",
        rows,
        ["trading_date", "sector_index_id", "index_name", "close", "source", "source_reference", "coverage_start", "coverage_end", "methodology", "sector_context_version"],
    )


def write_sector_mapping(data_dir, rows):
    write_csv(
        data_dir / "reference" / "nse" / "indices" / "normalized" / "stock_sector_mapping.csv",
        [
            {
                "symbol": symbol,
                "isin": f"INE{symbol}",
                "sector_name": "Information Technology",
                "sector_index_id": sector_id,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "mapping_source": "fixture",
                "mapping_status": status,
                "confidence": "HIGH" if status == "POINT_IN_TIME_VERIFIED" else "CURRENT_OFFICIAL_SNAPSHOT_ONLY",
                "notes": "fixture",
            }
            for symbol, sector_id, valid_from, valid_to, status in rows
        ],
        ["symbol", "isin", "sector_name", "sector_index_id", "valid_from", "valid_to", "mapping_source", "mapping_status", "confidence", "notes"],
    )


def index_row(session, id_field, index_id, index_name, close):
    return {
        "trading_date": session.isoformat(),
        id_field: index_id,
        "index_name": index_name,
        "open": str(close),
        "high": str(close),
        "low": str(close),
        "close": str(close),
        "source": "fixture",
        "source_reference": "fixture",
        "source_date": session.isoformat(),
        "methodology": "fixture",
        "benchmark_context_version": "BENCHMARK_CONTEXT_V1",
        "sector_context_version": "SECTOR_CONTEXT_V1",
        "coverage_start": "",
        "coverage_end": "",
    }


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
