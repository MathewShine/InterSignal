from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from io import StringIO
from typing import Any

from app.config.settings import get_settings
from app.models.ingestion import (
    ASIA_KOLKATA,
    DailyCandle,
    IngestionIssue,
    InstrumentRecord,
    IntradayCandle,
    ProviderReadResult,
)
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.providers.groww.exceptions import (
    GrowwHistoricalDataError,
    GrowwProviderNotConfiguredError,
)
from app.providers.historical.base import HistoricalDataProvider


INTERVAL_ALIASES = {
    "1m": "1m",
    "2m": "2m",
    "3m": "3m",
    "5m": "5m",
    "10m": "10m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "day": "1d",
    "daily": "1d",
    "1w": "1w",
    "week": "1w",
    "weekly": "1w",
    "1mo": "1mo",
    "month": "1mo",
    "monthly": "1mo",
}

INTERVAL_CONSTANTS = {
    "1m": ("CANDLE_INTERVAL_MIN_1", "1minute"),
    "2m": ("CANDLE_INTERVAL_MIN_2", "2minute"),
    "3m": ("CANDLE_INTERVAL_MIN_3", "3minute"),
    "5m": ("CANDLE_INTERVAL_MIN_5", "5minute"),
    "10m": ("CANDLE_INTERVAL_MIN_10", "10minute"),
    "15m": ("CANDLE_INTERVAL_MIN_15", "15minute"),
    "30m": ("CANDLE_INTERVAL_MIN_30", "30minute"),
    "1h": ("CANDLE_INTERVAL_HOUR_1", "1hour"),
    "4h": ("CANDLE_INTERVAL_HOUR_4", "4hour"),
    "1d": ("CANDLE_INTERVAL_DAY", "1day"),
    "1w": ("CANDLE_INTERVAL_WEEK", "1week"),
    "1mo": ("CANDLE_INTERVAL_MONTH", "1month"),
}

INTERVAL_LIMIT_DAYS = {
    "1m": 30,
    "2m": 30,
    "3m": 30,
    "5m": 30,
    "10m": 90,
    "15m": 90,
    "30m": 90,
    "1h": 180,
    "4h": 180,
    "1d": 180,
    "1w": 180,
    "1mo": 180,
}

INTRADAY_INTERVALS = {"1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"}


class _IncompleteGrowwCandle(ValueError):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class GrowwHistoricalProviderConfig:
    totp_token: str | None = field(default=None, repr=False)
    totp_secret: str | None = field(default=None, repr=False)
    exchange: str = "NSE"
    segment: str = "CASH"
    trading_symbol: str = "RELIANCE"
    groww_symbol: str | None = None
    company_name: str = "Reliance Industries"
    instrument_type: str = "EQ"
    source: str = "groww"
    timeout_seconds: int | None = 30

    @classmethod
    def from_settings(cls) -> "GrowwHistoricalProviderConfig":
        settings = get_settings()
        return cls(
            totp_token=settings.groww_totp_token,
            totp_secret=settings.groww_totp_secret,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.totp_token and self.totp_secret)

    @property
    def provider_symbol(self) -> str:
        return self.groww_symbol or f"{self.exchange}-{self.trading_symbol}"

    @property
    def credentials(self) -> GrowwCredentials | None:
        if not self.is_configured:
            return None
        return GrowwCredentials(
            totp_token=self.totp_token or "",
            totp_secret=self.totp_secret or "",
        )


class GrowwHistoricalProvider(HistoricalDataProvider):
    name = "groww"

    def __init__(
        self,
        config: GrowwHistoricalProviderConfig | None = None,
        *,
        auth_service: GrowwAuthService | None = None,
    ) -> None:
        self.config = config or GrowwHistoricalProviderConfig.from_settings()
        self.auth_service = auth_service or GrowwAuthService(
            credentials=self.config.credentials
        )

    async def list_instruments(self) -> ProviderReadResult[InstrumentRecord]:
        self._ensure_configured()
        client = self.auth_service.get_client()
        try:
            with redirect_stdout(StringIO()):
                payload = client.get_instrument_by_groww_symbol(
                    self.config.provider_symbol
                )
        except Exception as exc:
            raise GrowwHistoricalDataError() from exc

        record = self._normalize_instrument(payload)
        return ProviderReadResult(
            records=[record],
            rows_read=1,
            source_reference=f"groww:{self.config.provider_symbol}:instrument",
            metadata=self.get_provider_metadata(),
        )

    async def get_daily_candles(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> ProviderReadResult[DailyCandle]:
        self._ensure_configured()
        if start is None or end is None:
            raise ValueError("start and end dates are required for Groww daily candles")

        start_time = datetime.combine(start, time(9, 15), tzinfo=ASIA_KOLKATA)
        end_time = datetime.combine(end, time(15, 30), tzinfo=ASIA_KOLKATA)
        response = self._request_candles(
            interval="1d",
            start_time=start_time,
            end_time=end_time,
        )
        candles = self._extract_candles(response)
        records, errors, skipped_incomplete = self._normalize_daily_candles(candles)
        return ProviderReadResult(
            records=records,
            errors=errors,
            rows_read=len(candles),
            source_reference=self._source_reference("1d", start_time, end_time),
            metadata=self._read_metadata(
                "1d",
                records,
                start_time,
                end_time,
                skipped_incomplete_rows=skipped_incomplete,
            ),
        )

    async def get_raw_daily_candles(
        self,
        *,
        start: date,
        end: date,
    ) -> list[Any]:
        self._ensure_configured()
        start_time = datetime.combine(start, time(9, 15), tzinfo=ASIA_KOLKATA)
        end_time = datetime.combine(end, time(15, 30), tzinfo=ASIA_KOLKATA)
        response = self._request_candles(
            interval="1d",
            start_time=start_time,
            end_time=end_time,
        )
        return self._extract_candles(response)

    async def get_intraday_candles(
        self,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ProviderReadResult[IntradayCandle]:
        self._ensure_configured()
        canonical_interval = self._canonical_interval(interval)
        if canonical_interval not in INTRADAY_INTERVALS:
            raise ValueError(f"Unsupported Groww intraday interval: {interval}")
        if start is None or end is None:
            raise ValueError("start and end datetimes are required for Groww intraday candles")

        start_time = self._ensure_aware(start)
        end_time = self._ensure_aware(end)
        response = self._request_candles(
            interval=canonical_interval,
            start_time=start_time,
            end_time=end_time,
        )
        candles = self._extract_candles(response)
        records, errors, skipped_incomplete = self._normalize_intraday_candles(
            candles,
            canonical_interval,
        )
        return ProviderReadResult(
            records=records,
            errors=errors,
            rows_read=len(candles),
            source_reference=self._source_reference(canonical_interval, start_time, end_time),
            metadata=self._read_metadata(
                canonical_interval,
                records,
                start_time,
                end_time,
                skipped_incomplete_rows=skipped_incomplete,
            ),
        )

    def supports_interval(self, interval: str) -> bool:
        try:
            self._canonical_interval(interval)
        except ValueError:
            return False
        return True

    def get_provider_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "configured": self.auth_service.is_configured,
            "exchange": self.config.exchange,
            "segment": self.config.segment,
            "trading_symbol": self.config.trading_symbol,
            "groww_symbol": self.config.provider_symbol,
            "source": self.config.source,
            "official_sdk": "growwapi",
            "read_only": True,
            "orders_enabled": False,
            "supported_intervals": sorted(INTERVAL_CONSTANTS),
            "interval_limits_days": INTERVAL_LIMIT_DAYS,
            "history_available_from_year": 2020,
            "provider_symbol_mapping": "isolated_in_groww_adapter",
        }

    def _request_candles(
        self,
        *,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        self._validate_range(interval, start_time, end_time)
        client = self.auth_service.get_client()
        try:
            with redirect_stdout(StringIO()):
                return client.get_historical_candles(
                    exchange=self._sdk_value(client, "EXCHANGE_NSE", self.config.exchange),
                    segment=self._sdk_value(client, "SEGMENT_CASH", self.config.segment),
                    groww_symbol=self.config.provider_symbol,
                    start_time=self._format_api_datetime(start_time),
                    end_time=self._format_api_datetime(end_time),
                    candle_interval=self._interval_value(client, interval),
                    timeout=self.config.timeout_seconds,
                )
        except Exception as exc:
            raise GrowwHistoricalDataError() from exc

    def _extract_candles(self, response: dict[str, Any]) -> list[Any]:
        if not isinstance(response, dict):
            raise GrowwHistoricalDataError()

        candles = response.get("candles")
        if candles is None and isinstance(response.get("data"), dict):
            candles = response["data"].get("candles")

        if not isinstance(candles, list):
            raise GrowwHistoricalDataError()
        return candles

    def _normalize_daily_candles(
        self,
        candles: list[Any],
    ) -> tuple[list[DailyCandle], list[IngestionIssue], int]:
        records: list[DailyCandle] = []
        errors: list[IngestionIssue] = []
        skipped_incomplete = 0

        for index, row in enumerate(candles, start=1):
            try:
                timestamp, open_, high, low, close, volume = self._parse_candle_row(row)
                records.append(
                    DailyCandle(
                        exchange=self.config.exchange,
                        trading_symbol=self.config.trading_symbol,
                        trading_date=timestamp.date(),
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        adjusted_close=None,
                        traded_value=None,
                        source=self.config.source,
                    )
                )
            except _IncompleteGrowwCandle:
                skipped_incomplete += 1
            except Exception as exc:
                errors.append(self._parse_error(index, row, exc))

        return records, errors, skipped_incomplete

    def _normalize_intraday_candles(
        self,
        candles: list[Any],
        interval: str,
    ) -> tuple[list[IntradayCandle], list[IngestionIssue], int]:
        records: list[IntradayCandle] = []
        errors: list[IngestionIssue] = []
        skipped_incomplete = 0

        for index, row in enumerate(candles, start=1):
            try:
                timestamp, open_, high, low, close, volume = self._parse_candle_row(row)
                records.append(
                    IntradayCandle(
                        exchange=self.config.exchange,
                        trading_symbol=self.config.trading_symbol,
                        timestamp=timestamp,
                        interval=interval,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        traded_value=None,
                        vwap=None,
                        source=self.config.source,
                    )
                )
            except _IncompleteGrowwCandle:
                skipped_incomplete += 1
            except Exception as exc:
                errors.append(self._parse_error(index, row, exc))

        return records, errors, skipped_incomplete

    def _parse_candle_row(self, row: Any) -> tuple[datetime, Decimal, Decimal, Decimal, Decimal, int]:
        if isinstance(row, dict):
            timestamp = row.get("timestamp") or row.get("time") or row.get("date")
            open_ = row.get("open")
            high = row.get("high")
            low = row.get("low")
            close = row.get("close")
            volume = row.get("volume")
        else:
            timestamp, open_, high, low, close, volume = row[:6]

        if any(self._is_missing(value) for value in (timestamp, open_, high, low, close, volume)):
            raise _IncompleteGrowwCandle("incomplete Groww candle skipped")

        return (
            self._parse_timestamp(timestamp),
            self._parse_decimal(open_),
            self._parse_decimal(high),
            self._parse_decimal(low),
            self._parse_decimal(close),
            self._parse_int(volume),
        )

    def _normalize_instrument(self, payload: dict[str, Any]) -> InstrumentRecord:
        trading_symbol = str(payload.get("trading_symbol") or self.config.trading_symbol)
        return InstrumentRecord(
            exchange=str(payload.get("exchange") or self.config.exchange),
            trading_symbol=trading_symbol,
            company_name=str(payload.get("name") or self.config.company_name or trading_symbol),
            isin=payload.get("isin"),
            instrument_type=str(payload.get("instrument_type") or self.config.instrument_type),
            provider_symbol=payload.get("groww_symbol") or self.config.provider_symbol,
            provider=self.name,
        )

    def _canonical_interval(self, interval: str) -> str:
        canonical = INTERVAL_ALIASES.get(interval.strip().lower())
        if canonical is None:
            raise ValueError(f"Unsupported Groww interval: {interval}")
        return canonical

    def _interval_value(self, client: Any, interval: str) -> str:
        attr_name, fallback = INTERVAL_CONSTANTS[interval]
        return self._sdk_value(client, attr_name, fallback)

    def _sdk_value(self, client: Any, attr_name: str, fallback: str) -> str:
        return str(getattr(client, attr_name, fallback))

    def _validate_range(
        self,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        if start_time > end_time:
            raise ValueError("Groww historical start time must be before end time")

        max_days = INTERVAL_LIMIT_DAYS[interval]
        requested_days = (end_time.date() - start_time.date()).days + 1
        if requested_days > max_days:
            raise ValueError(
                f"Groww interval {interval} supports a maximum {max_days}-day request"
            )

    def _read_metadata(
        self,
        interval: str,
        records: list[DailyCandle] | list[IntradayCandle],
        start_time: datetime,
        end_time: datetime,
        *,
        skipped_incomplete_rows: int,
    ) -> dict[str, Any]:
        metadata = self.get_provider_metadata()
        metadata.update(
            {
                "requested_interval": interval,
                "requested_start": self._format_api_datetime(start_time),
                "requested_end": self._format_api_datetime(end_time),
                "normalized_records": len(records),
                "skipped_incomplete_rows": skipped_incomplete_rows,
                "first_candle": self._preview_candle(records[0]) if records else None,
                "last_candle": self._preview_candle(records[-1]) if records else None,
            }
        )
        return metadata

    def _preview_candle(self, candle: DailyCandle | IntradayCandle) -> dict[str, Any]:
        timestamp = (
            candle.trading_date.isoformat()
            if isinstance(candle, DailyCandle)
            else candle.timestamp.isoformat()
        )
        return {
            "timestamp": timestamp,
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": candle.volume,
        }

    def _source_reference(
        self,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        return (
            f"groww:{self.config.provider_symbol}:{interval}:"
            f"{self._format_api_datetime(start_time)}->{self._format_api_datetime(end_time)}"
        )

    def _format_api_datetime(self, value: datetime) -> str:
        return self._ensure_aware(value).strftime("%Y-%m-%d %H:%M:%S")

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return self._ensure_aware(value)
        if isinstance(value, date):
            return datetime.combine(value, time(), tzinfo=ASIA_KOLKATA)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(ASIA_KOLKATA)

        raw = str(value).strip()
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return self._ensure_aware(parsed)
        except ValueError:
            pass

        for timestamp_format in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(raw, timestamp_format)
                return self._ensure_aware(parsed)
            except ValueError:
                continue

        raise ValueError("invalid Groww candle timestamp")

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=ASIA_KOLKATA)
        return value.astimezone(ASIA_KOLKATA)

    def _parse_decimal(self, value: Any) -> Decimal:
        return Decimal(str(value).replace(",", "").strip())

    def _parse_int(self, value: Any) -> int:
        return int(self._parse_decimal(value))

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().lower() in {"", "none", "null", "nan"}
        return False

    def _parse_error(self, index: int, row: Any, exc: Exception) -> IngestionIssue:
        return IngestionIssue(
            severity="error",
            code="groww_parse_error",
            message=str(exc),
            row_reference=f"record:{index}",
            raw_record={"row": row} if isinstance(row, dict) else None,
        )

    def _ensure_configured(self) -> None:
        if not self.auth_service.is_configured:
            raise GrowwProviderNotConfiguredError()
