import asyncio
from decimal import Decimal
from pathlib import Path

from app.models import ASIA_KOLKATA
from app.providers.historical import CSVColumnMapping, CsvHistoricalDataProvider

FIXTURES = Path(__file__).parent / "fixtures"


def test_csv_provider_uses_configurable_instrument_mapping():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "sample_instruments.csv",
        mapping=CSVColumnMapping(
            symbol="SYMBOL",
            exchange="EXCHANGE",
            company_name="COMPANY",
            isin="ISIN",
            sector="SECTOR",
            industry="INDUSTRY",
            instrument_type="TYPE",
            nifty500_member="NIFTY500",
            provider_symbol="PROVIDER_SYMBOL",
        ),
        source="synthetic_fixture",
    )

    result = asyncio.run(provider.list_instruments())

    assert result.rows_read == 2
    assert result.errors == []
    assert result.records[0].trading_symbol == "ALPHA"
    assert result.records[0].nifty500_member is True


def test_csv_provider_normalizes_daily_candles_with_decimal_values():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "sample_daily_candles.csv",
        mapping=daily_mapping(),
        source="synthetic_fixture",
    )

    result = asyncio.run(provider.get_daily_candles())

    assert result.rows_read == 2
    assert result.errors == []
    assert result.records[0].close == Decimal("104.5000")
    assert result.records[1].adjusted_close is None
    assert result.records[1].traded_value == Decimal("138912345.67")


def test_csv_provider_normalizes_intraday_timestamps_to_asia_kolkata():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "sample_intraday_5m.csv",
        mapping=CSVColumnMapping(
            symbol="SYMBOL",
            timestamp="TIMESTAMP",
            interval="INTERVAL",
            open="OPEN",
            high="HIGH",
            low="LOW",
            close="CLOSE",
            volume="VOLUME",
            traded_value="TRADED_VALUE",
            vwap="VWAP",
        ),
        source="synthetic_fixture",
        default_interval="5m",
    )

    result = asyncio.run(provider.get_intraday_candles(interval="5m"))

    assert result.errors == []
    assert result.records[0].timestamp.tzinfo == ASIA_KOLKATA
    assert result.records[0].interval == "5m"
    assert result.records[0].vwap == Decimal("100.4167")


def test_csv_provider_reports_malformed_rows_without_silently_discarding():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "malformed_daily_candles.csv",
        mapping=CSVColumnMapping(
            symbol="SYMBOL",
            date="DATE",
            open="OPEN",
            high="HIGH",
            low="LOW",
            close="CLOSE",
            volume="VOLUME",
            traded_value="TRADED_VALUE",
        ),
        source="synthetic_fixture",
    )

    result = asyncio.run(provider.get_daily_candles())

    assert result.rows_read == 3
    assert len(result.records) == 1
    assert len(result.errors) == 2
    assert {error.code for error in result.errors} == {"parse_error"}


def daily_mapping():
    return CSVColumnMapping(
        symbol="SYMBOL",
        date="DATE",
        open="OPEN",
        high="HIGH",
        low="LOW",
        close="CLOSE",
        adjusted_close="ADJ_CLOSE",
        volume="VOLUME",
        traded_value="TRADED_VALUE",
    )

