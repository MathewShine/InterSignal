from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.models import DailyCandle, IntradayCandle
from app.services.data_quality import DataQualityConfig, HistoricalDataValidator


def test_ohlc_and_negative_volume_validation():
    record = DailyCandle(
        exchange="NSE",
        trading_symbol="ALPHA",
        trading_date=datetime(2026, 9, 1).date(),
        open=Decimal("100.0000"),
        high=Decimal("99.0000"),
        low=Decimal("101.0000"),
        close=Decimal("100.5000"),
        volume=-1,
        source="synthetic_fixture",
    )

    result = HistoricalDataValidator().validate_daily_candles([record])

    assert result.valid_count == 0
    assert "invalid_ohlc" in {error.code for error in result.errors}
    assert "negative_volume" in {error.code for error in result.errors}


def test_zero_volume_and_extreme_move_are_warnings_not_rejections():
    record = DailyCandle(
        exchange="NSE",
        trading_symbol="ALPHA",
        trading_date=datetime(2026, 9, 1).date(),
        open=Decimal("100.0000"),
        high=Decimal("130.0000"),
        low=Decimal("95.0000"),
        close=Decimal("105.0000"),
        volume=0,
        source="synthetic_fixture",
    )
    validator = HistoricalDataValidator(
        DataQualityConfig(extreme_move_warning_threshold=Decimal("0.10"))
    )

    result = validator.validate_daily_candles([record])

    assert result.valid_count == 1
    assert {warning.code for warning in result.warnings} == {
        "zero_volume",
        "extreme_candle_move",
    }


def test_unsupported_interval_is_rejected():
    record = IntradayCandle(
        exchange="NSE",
        trading_symbol="ALPHA",
        timestamp=datetime(2026, 9, 1, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")),
        interval="45m",
        open=Decimal("100.0000"),
        high=Decimal("101.0000"),
        low=Decimal("99.5000"),
        close=Decimal("100.7500"),
        volume=100,
        source="synthetic_fixture",
    )

    result = HistoricalDataValidator().validate_intraday_candles([record])

    assert result.valid_count == 0
    assert result.errors[0].code == "unsupported_interval"


def test_intraday_gap_warning():
    records = [
        intraday_record("2026-09-01T09:15:00+05:30"),
        intraday_record("2026-09-01T09:25:00+05:30"),
    ]

    result = HistoricalDataValidator().validate_intraday_candles(records)

    assert result.valid_count == 2
    assert any(warning.code == "intraday_gap" for warning in result.warnings)


def intraday_record(timestamp: str) -> IntradayCandle:
    return IntradayCandle(
        exchange="NSE",
        trading_symbol="ALPHA",
        timestamp=datetime.fromisoformat(timestamp),
        interval="5m",
        open=Decimal("100.0000"),
        high=Decimal("101.0000"),
        low=Decimal("99.5000"),
        close=Decimal("100.7500"),
        volume=100,
        source="synthetic_fixture",
    )
