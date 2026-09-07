from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models.ingestion import (
    ASIA_KOLKATA,
    DailyCandle,
    IngestionIssue,
    InstrumentRecord,
    IntradayCandle,
    ProviderReadResult,
)
from app.providers.historical.base import HistoricalDataProvider


@dataclass(frozen=True, slots=True)
class CSVColumnMapping:
    symbol: str | None = None
    exchange: str | None = None
    company_name: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    instrument_type: str | None = None
    nifty500_member: str | None = None
    provider_symbol: str | None = None
    provider: str | None = None
    date: str | None = None
    timestamp: str | None = None
    interval: str | None = None
    open: str | None = None
    high: str | None = None
    low: str | None = None
    close: str | None = None
    adjusted_close: str | None = None
    volume: str | None = None
    traded_value: str | None = None
    vwap: str | None = None


class CsvHistoricalDataProvider(HistoricalDataProvider):
    name = "csv"

    def __init__(
        self,
        *,
        file_path: str | Path,
        mapping: CSVColumnMapping | dict[str, str | None],
        source: str,
        provider: str = "csv",
        delimiter: str = ",",
        encoding: str = "utf-8",
        default_exchange: str = "NSE",
        default_interval: str | None = None,
        date_formats: list[str] | None = None,
        timestamp_formats: list[str] | None = None,
        supported_intervals: set[str] | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.mapping = (
            mapping
            if isinstance(mapping, CSVColumnMapping)
            else CSVColumnMapping(**mapping)
        )
        self.source = source
        self.provider = provider
        self.delimiter = delimiter
        self.encoding = encoding
        self.default_exchange = default_exchange
        self.default_interval = default_interval
        self.date_formats = date_formats or ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"]
        self.timestamp_formats = timestamp_formats or [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ]
        self.supported_intervals = supported_intervals or {"1m", "5m", "15m", "1d", "day", "daily"}

    async def list_instruments(self) -> ProviderReadResult[InstrumentRecord]:
        rows, file_error = self._read_rows()
        if file_error:
            return ProviderReadResult(records=[], errors=[file_error], rows_read=0)

        records: list[InstrumentRecord] = []
        errors: list[IngestionIssue] = []

        for index, row in enumerate(rows, start=2):
            try:
                symbol = self._required_value(row, "symbol")
                records.append(
                    InstrumentRecord(
                        exchange=self._optional_value(row, "exchange") or self.default_exchange,
                        trading_symbol=symbol,
                        company_name=self._optional_value(row, "company_name") or symbol,
                        isin=self._optional_value(row, "isin"),
                        sector=self._optional_value(row, "sector"),
                        industry=self._optional_value(row, "industry"),
                        instrument_type=self._optional_value(row, "instrument_type") or "EQUITY",
                        nifty500_member=self._parse_bool(
                            self._optional_value(row, "nifty500_member")
                        ),
                        provider_symbol=self._optional_value(row, "provider_symbol"),
                        provider=self._optional_value(row, "provider") or self.provider,
                    )
                )
            except Exception as exc:
                errors.append(self._parse_error(index, row, exc))

        return ProviderReadResult(
            records=records,
            errors=errors,
            rows_read=len(rows),
            source_reference=str(self.file_path),
            metadata=self.get_provider_metadata(),
        )

    async def get_daily_candles(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> ProviderReadResult[DailyCandle]:
        rows, file_error = self._read_rows()
        if file_error:
            return ProviderReadResult(records=[], errors=[file_error], rows_read=0)

        records: list[DailyCandle] = []
        errors: list[IngestionIssue] = []

        for index, row in enumerate(rows, start=2):
            try:
                trading_date = self._parse_date(self._required_value(row, "date"))
                if start and trading_date < start:
                    continue
                if end and trading_date > end:
                    continue

                records.append(
                    DailyCandle(
                        exchange=self._optional_value(row, "exchange") or self.default_exchange,
                        trading_symbol=self._required_value(row, "symbol"),
                        trading_date=trading_date,
                        open=self._parse_decimal(self._required_value(row, "open")),
                        high=self._parse_decimal(self._required_value(row, "high")),
                        low=self._parse_decimal(self._required_value(row, "low")),
                        close=self._parse_decimal(self._required_value(row, "close")),
                        adjusted_close=self._parse_optional_decimal(
                            self._optional_value(row, "adjusted_close")
                        ),
                        volume=self._parse_int(self._required_value(row, "volume")),
                        traded_value=self._parse_optional_decimal(
                            self._optional_value(row, "traded_value")
                        ),
                        source=self.source,
                    )
                )
            except Exception as exc:
                errors.append(self._parse_error(index, row, exc))

        return ProviderReadResult(
            records=records,
            errors=errors,
            rows_read=len(rows),
            source_reference=str(self.file_path),
            metadata=self.get_provider_metadata(),
        )

    async def get_intraday_candles(
        self,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ProviderReadResult[IntradayCandle]:
        rows, file_error = self._read_rows()
        if file_error:
            return ProviderReadResult(records=[], errors=[file_error], rows_read=0)

        records: list[IntradayCandle] = []
        errors: list[IngestionIssue] = []

        for index, row in enumerate(rows, start=2):
            try:
                row_interval = self._optional_value(row, "interval") or self.default_interval or interval
                timestamp = self._parse_datetime(self._required_value(row, "timestamp"))
                if start and timestamp < self._ensure_aware(start):
                    continue
                if end and timestamp > self._ensure_aware(end):
                    continue

                records.append(
                    IntradayCandle(
                        exchange=self._optional_value(row, "exchange") or self.default_exchange,
                        trading_symbol=self._required_value(row, "symbol"),
                        timestamp=timestamp,
                        interval=row_interval,
                        open=self._parse_decimal(self._required_value(row, "open")),
                        high=self._parse_decimal(self._required_value(row, "high")),
                        low=self._parse_decimal(self._required_value(row, "low")),
                        close=self._parse_decimal(self._required_value(row, "close")),
                        volume=self._parse_int(self._required_value(row, "volume")),
                        traded_value=self._parse_optional_decimal(
                            self._optional_value(row, "traded_value")
                        ),
                        vwap=self._parse_optional_decimal(self._optional_value(row, "vwap")),
                        source=self.source,
                    )
                )
            except Exception as exc:
                errors.append(self._parse_error(index, row, exc))

        return ProviderReadResult(
            records=records,
            errors=errors,
            rows_read=len(rows),
            source_reference=str(self.file_path),
            metadata=self.get_provider_metadata(),
        )

    def supports_interval(self, interval: str) -> bool:
        return interval in self.supported_intervals

    def get_provider_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source": self.source,
            "file_path": str(self.file_path),
            "delimiter": self.delimiter,
            "default_exchange": self.default_exchange,
        }

    def _read_rows(self) -> tuple[list[dict[str, str]], IngestionIssue | None]:
        try:
            with self.file_path.open("r", encoding=self.encoding, newline="") as file:
                return list(csv.DictReader(file, delimiter=self.delimiter)), None
        except Exception as exc:
            return [], IngestionIssue(
                severity="error",
                code="file_read_error",
                message=str(exc),
                row_reference=str(self.file_path),
            )

    def _column_name(self, field_name: str) -> str | None:
        return getattr(self.mapping, field_name)

    def _optional_value(self, row: dict[str, str], field_name: str) -> str | None:
        column = self._column_name(field_name)
        if not column:
            return None
        value = row.get(column)
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _required_value(self, row: dict[str, str], field_name: str) -> str:
        value = self._optional_value(row, field_name)
        if value is None:
            raise ValueError(f"missing required field: {field_name}")
        return value

    def _parse_date(self, value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass

        for date_format in self.date_formats:
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue

        raise ValueError(f"invalid date: {value}")

    def _parse_datetime(self, value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None

        if parsed is None:
            for timestamp_format in self.timestamp_formats:
                try:
                    parsed = datetime.strptime(value, timestamp_format)
                    break
                except ValueError:
                    continue

        if parsed is None:
            raise ValueError(f"invalid timestamp: {value}")

        return self._ensure_aware(parsed)

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=ASIA_KOLKATA)
        return value.astimezone(ASIA_KOLKATA)

    def _parse_decimal(self, value: str) -> Decimal:
        return Decimal(value.replace(",", "").strip())

    def _parse_optional_decimal(self, value: str | None) -> Decimal | None:
        if value is None:
            return None
        return self._parse_decimal(value)

    def _parse_int(self, value: str) -> int:
        return int(Decimal(value.replace(",", "").strip()))

    def _parse_bool(self, value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "y"}

    def _parse_error(self, index: int, row: dict[str, str], exc: Exception) -> IngestionIssue:
        return IngestionIssue(
            severity="error",
            code="parse_error",
            message=str(exc),
            row_reference=str(index),
            raw_record=row,
        )

