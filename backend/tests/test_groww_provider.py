import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.providers.groww import (
    GrowwAuthService,
    GrowwCredentials,
    GrowwHistoricalDataError,
    GrowwHistoricalProvider,
    GrowwHistoricalProviderConfig,
    GrowwProviderNotConfiguredError,
)


class FakeGrowwClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_DAY = "1day"
    CANDLE_INTERVAL_MIN_5 = "5minute"

    def __init__(self, response=None, exc: Exception | None = None):
        self.response = response or {
            "candles": [
                ["2025-01-02 00:00:00", "1200.10", "1220.00", "1190.00", "1210.50", 1000000, None]
            ]
        }
        self.exc = exc
        self.calls = []

    def get_historical_candles(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.response

    def get_instrument_by_groww_symbol(self, groww_symbol):
        return {
            "exchange": "NSE",
            "trading_symbol": "RELIANCE",
            "groww_symbol": groww_symbol,
            "name": "Reliance Industries",
            "instrument_type": "EQ",
            "isin": "INE002A01018",
        }


class FakeAuthService:
    is_configured = True

    def __init__(self, client: FakeGrowwClient):
        self.client = client

    def get_client(self):
        return self.client


def provider_with_client(client: FakeGrowwClient) -> GrowwHistoricalProvider:
    return GrowwHistoricalProvider(
        GrowwHistoricalProviderConfig(
            totp_token="fixture-token",
            totp_secret="fixture-totp-seed",
        ),
        auth_service=FakeAuthService(client),
    )


def test_groww_provider_reports_not_configured_without_credentials():
    provider = GrowwHistoricalProvider(GrowwHistoricalProviderConfig())

    assert provider.get_provider_metadata()["configured"] is False

    with pytest.raises(GrowwProviderNotConfiguredError) as exc_info:
        asyncio.run(provider.get_daily_candles(start=date(2025, 1, 1), end=date(2025, 1, 2)))

    assert exc_info.value.code == "GROWW_NOT_CONFIGURED"


def test_groww_daily_candles_are_normalized_from_sdk_payload():
    client = FakeGrowwClient()
    provider = provider_with_client(client)

    result = asyncio.run(
        provider.get_daily_candles(start=date(2025, 1, 1), end=date(2025, 1, 2))
    )

    assert result.rows_read == 1
    assert result.errors == []
    assert result.records[0].trading_symbol == "RELIANCE"
    assert result.records[0].trading_date == date(2025, 1, 2)
    assert result.records[0].source == "groww"
    assert client.calls[0]["groww_symbol"] == "NSE-RELIANCE"
    assert client.calls[0]["candle_interval"] == "1day"


def test_groww_intraday_candles_are_timezone_aware():
    client = FakeGrowwClient(
        {
            "candles": [
                ["2025-01-02 09:15:00", "1200", "1205", "1198", "1203", 1234, None]
            ]
        }
    )
    provider = provider_with_client(client)

    result = asyncio.run(
        provider.get_intraday_candles(
            interval="5m",
            start=datetime(2025, 1, 2, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")),
            end=datetime(2025, 1, 2, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
    )

    assert result.records[0].interval == "5m"
    assert result.records[0].timestamp.tzinfo is not None
    assert result.records[0].timestamp.utcoffset() is not None
    assert client.calls[0]["candle_interval"] == "5minute"


def test_groww_supported_intervals_match_documented_backtesting_intervals():
    provider = GrowwHistoricalProvider(GrowwHistoricalProviderConfig())

    for interval in ("1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"):
        assert provider.supports_interval(interval)

    assert not provider.supports_interval("45m")


def test_groww_parse_errors_are_reported_without_failing_entire_batch():
    client = FakeGrowwClient({"candles": [["bad-date", "1200", "1205", "1198", "1203", 1234, None]]})
    provider = provider_with_client(client)

    result = asyncio.run(
        provider.get_daily_candles(start=date(2025, 1, 1), end=date(2025, 1, 2))
    )

    assert result.records == []
    assert result.errors[0].code == "groww_parse_error"


def test_groww_incomplete_candles_are_skipped_without_parse_errors():
    client = FakeGrowwClient(
        {
            "candles": [
                ["2025-01-01 00:00:00", None, "1205", "1198", "1203", 1234, None],
                ["2025-01-02 00:00:00", "1200", "1205", "1198", "1203", 1234, None],
            ]
        }
    )
    provider = provider_with_client(client)

    result = asyncio.run(
        provider.get_daily_candles(start=date(2025, 1, 1), end=date(2025, 1, 2))
    )

    assert len(result.records) == 1
    assert result.errors == []
    assert result.metadata["skipped_incomplete_rows"] == 1


def test_groww_sdk_errors_are_sanitized():
    client = FakeGrowwClient(exc=RuntimeError("do not leak fixture-token"))
    provider = provider_with_client(client)

    with pytest.raises(GrowwHistoricalDataError) as exc_info:
        asyncio.run(provider.get_daily_candles(start=date(2025, 1, 1), end=date(2025, 1, 2)))

    assert "fixture-token" not in str(exc_info.value)
