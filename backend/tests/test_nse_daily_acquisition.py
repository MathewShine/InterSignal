from __future__ import annotations

import csv
import urllib.error
from datetime import date
from decimal import Decimal

from app.providers.nse.daily_reference import NSEDailyRecord
from app.services import nse_daily_acquisition as service
from app.services.nse_daily_acquisition import (
    NSEDailyAcquisitionConfig,
    acquire_nse_daily_dataset,
    build_pilot_calendar_dates,
    classify_series,
    normalize_session_records,
    nse_archive_candidates,
)


LEGACY = """SYMBOL,SERIES,DATE1,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,TTL_TRD_QNTY,TURNOVER_LACS
RELIANCE,EQ,07-Sep-2026,101,105,99,104,12345,120.50
TCS,BE,07-Sep-2026,99,100,95,96,10,1.25
"""


def test_nse_archive_url_generation():
    candidates = nse_archive_candidates(date(2026, 9, 7))

    assert candidates[0].filename == "sec_bhavdata_full_07092026.csv"
    assert "07092026" in candidates[0].url
    assert candidates[1].filename == "BhavCopy_NSE_CM_0_0_0_20260907_F_0000.csv.zip"
    assert "20260907" in candidates[1].url


def test_cache_import_preserves_raw_payload_and_normalizes_special_series(tmp_path):
    source_cache = tmp_path / "legacy-cache"
    source_cache.mkdir()
    (source_cache / "sec_bhavdata_full_07092026.csv").write_text(LEGACY, encoding="utf-8")
    config = NSEDailyAcquisitionConfig(
        output_dir=tmp_path / "data",
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 7),
        request_delay_seconds=0,
        source_cache_dir=source_cache,
    )

    report = acquire_nse_daily_dataset(config=config)

    raw_path = tmp_path / "data" / "raw" / "nse" / "daily" / "2026" / "09" / "sec_bhavdata_full_07092026.csv"
    normalized_path = tmp_path / "data" / "historical" / "daily" / "nse" / "2026" / "09" / "nse_daily_20260907.csv"
    assert raw_path.read_text(encoding="utf-8") == LEGACY
    rows = list(csv.DictReader(normalized_path.open("r", encoding="utf-8")))
    assert report["records"]["eq_records"] == 1
    assert report["records"]["special_series_records"] == 1
    assert {row["series_classification"] for row in rows} == {"NORMAL_EQUITY", "SPECIAL_SERIES"}


def test_missing_marker_treated_as_non_session(tmp_path):
    source_cache = tmp_path / "legacy-cache"
    source_cache.mkdir()
    (source_cache / "2026-09-08.missing").write_text("missing", encoding="utf-8")
    config = NSEDailyAcquisitionConfig(
        output_dir=tmp_path / "data",
        start_date=date(2026, 9, 8),
        end_date=date(2026, 9, 8),
        request_delay_seconds=0,
        source_cache_dir=source_cache,
    )

    report = acquire_nse_daily_dataset(config=config)

    assert report["sessions"]["downloaded"] == 0
    assert report["calendar"]["non_session_dates"] == 1
    calendar_rows = list(csv.DictReader(config.calendar_path.open("r", encoding="utf-8")))
    assert calendar_rows[0]["source_available"] == "False"
    assert calendar_rows[0]["session_type"] == "UNKNOWN"


def test_network_failure_is_reported(monkeypatch, tmp_path):
    def fail_download(self, url):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(service.NSEDailyArchiveClient, "_download", fail_download)
    config = NSEDailyAcquisitionConfig(
        output_dir=tmp_path / "data",
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 7),
        request_delay_seconds=0,
        max_retries=0,
    )

    report = acquire_nse_daily_dataset(config=config)

    assert report["sessions"]["failed"] == 1
    assert report["records"]["total_normalized"] == 0


def test_validation_handles_duplicates_invalid_ohlc_and_zero_volume(tmp_path):
    previous = {}
    records = [
        record("RELIANCE", close=Decimal("100")),
        record("RELIANCE", close=Decimal("100")),
        record("BAD", high=Decimal("90"), low=Decimal("95")),
        record("ZERO", volume=0),
    ]

    normalized, summary = normalize_session_records(
        records,
        trading_date=date(2026, 9, 7),
        source_path=tmp_path / "fixture.csv",
        source_format="legacy_sec_bhavdata_full",
        previous_closes=previous,
    )

    assert len(normalized) == 2
    assert summary.duplicate_records == 1
    assert summary.invalid_records == 1
    assert summary.zero_volume_records == 1


def test_weekend_source_available_calendar_is_special(tmp_path):
    source_cache = tmp_path / "legacy-cache"
    source_cache.mkdir()
    source_cache.joinpath("sec_bhavdata_full_01022025.csv").write_text(
        LEGACY.replace("07-Sep-2026", "01-Feb-2025"),
        encoding="utf-8",
    )
    config = NSEDailyAcquisitionConfig(
        output_dir=tmp_path / "data",
        start_date=date(2025, 2, 1),
        end_date=date(2025, 2, 1),
        request_delay_seconds=0,
        source_cache_dir=source_cache,
    )

    acquire_nse_daily_dataset(config=config)

    calendar_rows = list(csv.DictReader(config.calendar_path.open("r", encoding="utf-8")))
    assert date(2025, 2, 1).weekday() == 5
    assert calendar_rows[0]["session_type"] == "SPECIAL"
    assert calendar_rows[0]["source_available"] == "True"


def test_corporate_action_suspect_flag_requires_nearby_session(tmp_path):
    previous = {}
    normalize_session_records(
        [record("RELIANCE", close=Decimal("100"), trading_date=date(2026, 9, 7))],
        trading_date=date(2026, 9, 7),
        source_path=tmp_path / "day1.csv",
        source_format="legacy_sec_bhavdata_full",
        previous_closes=previous,
    )

    normalized, summary = normalize_session_records(
        [record("RELIANCE", low=Decimal("45"), close=Decimal("50"), trading_date=date(2026, 9, 8))],
        trading_date=date(2026, 9, 8),
        source_path=tmp_path / "day2.csv",
        source_format="legacy_sec_bhavdata_full",
        previous_closes=previous,
    )

    assert summary.corporate_action_suspects == 1
    assert normalized[0].quality_flags == "CORPORATE_ACTION_SUSPECT"


def test_pilot_calendar_dates_are_evenly_spaced():
    dates = build_pilot_calendar_dates(
        date(2021, 9, 7),
        date(2026, 9, 7),
        target_dates=6,
    )

    assert dates[0] == date(2021, 9, 7)
    assert dates[-1] == date(2026, 9, 7)
    assert len(dates) == 6


def test_classify_series_keeps_special_series_visible():
    assert classify_series("EQ") == "NORMAL_EQUITY"
    assert classify_series("BE") == "SPECIAL_SERIES"


def record(
    symbol: str,
    *,
    trading_date: date = date(2026, 9, 7),
    high: Decimal = Decimal("105"),
    low: Decimal = Decimal("95"),
    close: Decimal = Decimal("100"),
    volume: int = 1000,
) -> NSEDailyRecord:
    return NSEDailyRecord(
        trading_date=trading_date,
        symbol=symbol,
        series="EQ",
        isin="INE002A01018",
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=volume,
        traded_value=Decimal("1000"),
        source_file="fixture.csv",
        source_format="legacy_sec_bhavdata_full",
    )
