import asyncio
from pathlib import Path

from app.models import ImportStatus
from app.providers.historical import CSVColumnMapping, CsvHistoricalDataProvider
from app.services.historical_ingestion import HistoricalIngestionService

FIXTURES = Path(__file__).parent / "fixtures"


def test_daily_dry_run_summary():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "sample_daily_candles.csv",
        mapping=daily_mapping(),
        source="synthetic_fixture",
    )

    summary = asyncio.run(
        HistoricalIngestionService().ingest_daily_candles(provider, dry_run=True)
    )

    assert summary.status == ImportStatus.DRY_RUN
    assert summary.rows_read == 2
    assert summary.rows_valid == 2
    assert summary.rows_inserted == 0
    assert summary.errors_count == 0


def test_duplicate_rows_are_skipped_and_reported():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "duplicate_daily_candles.csv",
        mapping=daily_mapping(),
        source="synthetic_fixture",
    )

    summary = asyncio.run(
        HistoricalIngestionService().ingest_daily_candles(provider, dry_run=True)
    )

    assert summary.rows_read == 2
    assert summary.rows_valid == 1
    assert summary.rows_skipped == 1
    assert any(warning.code == "duplicate_row" for warning in summary.warnings)


def test_malformed_rows_are_rejected_in_dry_run_summary():
    provider = CsvHistoricalDataProvider(
        file_path=FIXTURES / "malformed_daily_candles.csv",
        mapping=daily_mapping(),
        source="synthetic_fixture",
    )

    summary = asyncio.run(
        HistoricalIngestionService().ingest_daily_candles(provider, dry_run=True)
    )

    assert summary.status == ImportStatus.DRY_RUN
    assert summary.rows_read == 3
    assert summary.rows_valid == 1
    assert summary.rows_rejected == 2
    assert summary.errors_count == 2


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

