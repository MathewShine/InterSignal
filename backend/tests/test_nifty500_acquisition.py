import asyncio
from datetime import date
from decimal import Decimal

from app.models.ingestion import DailyCandle, ProviderReadResult
from app.services.nifty500_acquisition import (
    AcquisitionConfig,
    GrowwInstrumentMapping,
    Nifty500Constituent,
    build_report_payload,
    chunk_date_range,
    classify_price,
    count_large_daily_gaps,
    map_constituents_to_groww,
    merge_daily_records,
    normalize_nifty500_constituents,
    read_daily_csv,
    select_pilot_mappings,
    write_daily_csv,
    write_reports,
    acquire_symbol_daily_history,
)


RAW_NIFTY500 = """Company Name,Industry,Symbol,Series,ISIN Code
Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018
Tata Consultancy Services Ltd.,Information Technology,TCS,EQ,INE467B01029
"""


def test_nifty500_constituent_normalization():
    constituents = normalize_nifty500_constituents(
        RAW_NIFTY500,
        source_date="2026-09-07",
        source_url="https://example.test/nifty500.csv",
    )

    assert len(constituents) == 2
    assert constituents[0].trading_symbol == "RELIANCE"
    assert constituents[0].isin == "INE002A01018"
    assert constituents[0].active_current_member is True


def test_groww_mapping_uses_isin_before_symbol():
    constituents = [
        Nifty500Constituent(
            trading_symbol="RENAMED",
            company_name="Renamed Co",
            isin="INE002A01018",
            sector="",
            industry="Energy",
            index_name="NIFTY 500",
            source="test",
            source_date="2026-09-07",
        )
    ]
    instruments = [
        {
            "exchange": "NSE",
            "trading_symbol": "RELIANCE",
            "groww_symbol": "NSE-RELIANCE",
            "name": "Reliance Industries",
            "instrument_type": "EQ",
            "segment": "CASH",
            "series": "EQ",
            "isin": "INE002A01018",
            "buy_allowed": "1",
            "sell_allowed": "1",
        }
    ]

    mapping = map_constituents_to_groww(constituents, instruments)[0]

    assert mapping.mapping_status == "MATCHED"
    assert mapping.mapping_reason == "isin_exact; symbol differs but ISIN matched."
    assert mapping.groww_symbol == "NSE-RELIANCE"


def test_unresolved_symbol_is_not_dropped():
    constituents = normalize_nifty500_constituents(
        RAW_NIFTY500,
        source_date="2026-09-07",
    )

    mappings = map_constituents_to_groww(constituents, [])

    assert len(mappings) == 2
    assert {mapping.mapping_status for mapping in mappings} == {"NOT_FOUND"}


def test_chunked_daily_requests_respect_groww_daily_limit():
    chunks = chunk_date_range(date(2025, 1, 1), date(2026, 1, 10), max_days=180)

    assert chunks[0] == (date(2025, 1, 1), date(2025, 6, 29))
    assert chunks[-1][1] == date(2026, 1, 10)
    assert all((end - start).days + 1 <= 180 for start, end in chunks)


def test_duplicate_merge_keeps_one_candle_per_date():
    first = daily("2025-01-01", close="100")
    replacement = daily("2025-01-01", close="101")

    merged, duplicates = merge_daily_records([first, replacement])

    assert duplicates == 1
    assert len(merged) == 1
    assert merged[0].close == Decimal("101")


def test_price_eligibility_classification():
    assert classify_price(Decimal("99.99")) == "BELOW_PRICE_FLOOR"
    assert classify_price(Decimal("5000")) == "ELIGIBLE_PRICE"
    assert classify_price(Decimal("5000.01")) == "ABOVE_PREFERRED_RANGE"
    assert classify_price(Decimal("7000.01")) == "ABOVE_HARD_LIMIT"


def test_output_file_writing_and_resume_summary(tmp_path):
    mapping = matched_mapping()
    config = AcquisitionConfig(
        output_dir=tmp_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
        resume=True,
    )
    path = config.historical_dir / "RELIANCE.csv"
    write_daily_csv(
        path,
        [daily("2025-01-01"), daily("2025-01-02", close="101")],
        mapping=mapping,
        price_adjustment_status="UNKNOWN",
    )

    records = read_daily_csv(path, mapping=mapping)
    summary = asyncio.run(
        acquire_symbol_daily_history(
            mapping,
            config=config,
            auth_service=object(),
        )
    )

    assert len(records) == 2
    assert summary.fetch_status == "COMPLETE"
    assert summary.current_close == "101"
    assert summary.price_adjustment_status == "UNKNOWN"


def test_failed_symbol_isolation_with_mock_provider(tmp_path):
    mapping = matched_mapping()
    config = AcquisitionConfig(
        output_dir=tmp_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
        request_delay_seconds=0,
        max_retries=0,
    )

    class FailingProvider:
        async def get_daily_candles(self, *, start, end):
            raise RuntimeError("temporary provider issue")

    summary = asyncio.run(
        acquire_symbol_daily_history(
            mapping,
            config=config,
            auth_service=object(),
            provider_factory=lambda _: FailingProvider(),
        )
    )

    assert summary.fetch_status == "FAILED"
    assert "RuntimeError" in summary.error_message


def test_report_generation_outputs_csv_json_and_markdown(tmp_path):
    mapping = matched_mapping()
    summary = acquisition_summary(mapping)
    config = AcquisitionConfig(
        output_dir=tmp_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
    )

    report = write_reports(
        summaries=[summary],
        mappings=[mapping],
        constituents=[constituent()],
        config=config,
        source_metadata={"source_date": "2026-09-07", "source_url": "test", "source": "Official test"},
        full_acquisition_run=False,
        pilot_symbols=["RELIANCE"],
        markdown_path=tmp_path / "docs" / "report.md",
    )

    assert (tmp_path / "reports" / "nifty500_daily_acquisition_summary.csv").exists()
    assert (tmp_path / "reports" / "nifty500_daily_acquisition_summary.json").exists()
    assert (tmp_path / "docs" / "report.md").exists()
    assert report["corporate_actions"]["price_adjustment_status"] == "UNKNOWN"


def test_select_pilot_symbols_from_authoritative_mapping_order():
    mappings = [
        matched_mapping("INFY"),
        matched_mapping("RELIANCE"),
        matched_mapping("TCS"),
    ]

    selected = select_pilot_mappings(mappings, pilot_symbols=["RELIANCE", "INFY"])

    assert [mapping.nse_symbol for mapping in selected] == ["RELIANCE", "INFY"]


def test_large_gap_count_uses_chronological_daily_records():
    assert count_large_daily_gaps([daily("2025-01-01"), daily("2025-01-15")]) == 1


def test_large_gap_marks_symbol_partial(tmp_path):
    mapping = matched_mapping()
    config = AcquisitionConfig(
        output_dir=tmp_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 15),
    )
    from app.services.nifty500_acquisition import summarize_records

    summary = summarize_records(
        mapping,
        [daily("2025-01-01"), daily("2025-01-15")],
        config=config,
        output_path=tmp_path / "RELIANCE.csv",
    )

    assert summary.fetch_status == "PARTIAL"


def daily(value, *, close="100") -> DailyCandle:
    return DailyCandle(
        exchange="NSE",
        trading_symbol="RELIANCE",
        trading_date=date.fromisoformat(value),
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal(close),
        volume=1000,
        source="groww",
    )


def constituent() -> Nifty500Constituent:
    return Nifty500Constituent(
        trading_symbol="RELIANCE",
        company_name="Reliance Industries Ltd.",
        isin="INE002A01018",
        sector="",
        industry="Energy",
        index_name="NIFTY 500",
        source="test",
        source_date="2026-09-07",
    )


def matched_mapping(symbol="RELIANCE") -> GrowwInstrumentMapping:
    return GrowwInstrumentMapping(
        nse_symbol=symbol,
        company_name=f"{symbol} Ltd.",
        isin="INE002A01018",
        groww_symbol=f"NSE-{symbol}",
        exchange="NSE",
        segment="CASH",
        instrument_type="EQ",
        mapping_status="MATCHED",
        mapping_reason="isin_exact",
        groww_name=symbol,
        series="EQ",
    )


def acquisition_summary(mapping: GrowwInstrumentMapping):
    from app.services.nifty500_acquisition import SymbolAcquisitionSummary

    return SymbolAcquisitionSummary(
        nse_symbol=mapping.nse_symbol,
        company_name=mapping.company_name,
        isin=mapping.isin,
        groww_symbol=mapping.groww_symbol,
        mapping_status="MATCHED",
        mapping_reason="isin_exact",
        fetch_status="COMPLETE",
        candle_count=2,
        earliest_date="2025-01-01",
        latest_date="2025-01-02",
        current_close="101",
        price_eligibility_class="ELIGIBLE_PRICE",
    )
