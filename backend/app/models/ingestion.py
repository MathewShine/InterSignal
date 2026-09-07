from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

ASIA_KOLKATA = ZoneInfo("Asia/Kolkata")


class ImportStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    DRY_RUN = "DRY_RUN"


class ImportType(StrEnum):
    INSTRUMENTS = "INSTRUMENTS"
    DAILY_CANDLES = "DAILY_CANDLES"
    INTRADAY_CANDLES = "INTRADAY_CANDLES"


class IngestionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InstrumentRecord(IngestionModel):
    exchange: str
    trading_symbol: str
    company_name: str
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    instrument_type: str
    nifty500_member: bool = False
    provider_symbol: str | None = None
    provider: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.exchange, self.trading_symbol)


class DailyCandle(IngestionModel):
    exchange: str
    trading_symbol: str
    trading_date: date
    open: Decimal = Field(max_digits=18, decimal_places=4)
    high: Decimal = Field(max_digits=18, decimal_places=4)
    low: Decimal = Field(max_digits=18, decimal_places=4)
    close: Decimal = Field(max_digits=18, decimal_places=4)
    adjusted_close: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    volume: int
    traded_value: Decimal | None = Field(default=None, max_digits=20, decimal_places=2)
    source: str
    instrument_id: UUID | None = None

    @property
    def instrument_key(self) -> tuple[str, str]:
        return (self.exchange, self.trading_symbol)

    @property
    def dedupe_key(self) -> tuple[str, str, date, str]:
        return (self.exchange, self.trading_symbol, self.trading_date, self.source)


class IntradayCandle(IngestionModel):
    exchange: str
    trading_symbol: str
    timestamp: datetime
    interval: str
    open: Decimal = Field(max_digits=18, decimal_places=4)
    high: Decimal = Field(max_digits=18, decimal_places=4)
    low: Decimal = Field(max_digits=18, decimal_places=4)
    close: Decimal = Field(max_digits=18, decimal_places=4)
    volume: int
    traded_value: Decimal | None = Field(default=None, max_digits=20, decimal_places=2)
    vwap: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    source: str
    instrument_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_timestamp(self) -> "IntradayCandle":
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("intraday timestamp must be timezone-aware")
        self.timestamp = self.timestamp.astimezone(ASIA_KOLKATA)
        return self

    @property
    def instrument_key(self) -> tuple[str, str]:
        return (self.exchange, self.trading_symbol)

    @property
    def dedupe_key(self) -> tuple[str, str, datetime, str, str]:
        return (
            self.exchange,
            self.trading_symbol,
            self.timestamp,
            self.interval,
            self.source,
        )


class IngestionIssue(IngestionModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    row_reference: str | None = None
    raw_record: dict[str, Any] | None = None


RecordT = TypeVar("RecordT")


@dataclass(slots=True)
class ProviderReadResult(Generic[RecordT]):
    records: list[RecordT]
    errors: list[IngestionIssue] = field(default_factory=list)
    rows_read: int = 0
    source_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationResult(Generic[RecordT]):
    valid_records: list[RecordT]
    errors: list[IngestionIssue] = field(default_factory=list)
    warnings: list[IngestionIssue] = field(default_factory=list)
    duplicate_count: int = 0

    @property
    def invalid_count(self) -> int:
        return len(self.errors)

    @property
    def valid_count(self) -> int:
        return len(self.valid_records)


class PersistenceResult(IngestionModel):
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0


class ImportSummary(IngestionModel):
    provider: str
    import_type: ImportType
    source_reference: str | None = None
    dry_run: bool
    status: ImportStatus
    rows_read: int = 0
    rows_valid: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    rows_rejected: int = 0
    warnings_count: int = 0
    errors_count: int = 0
    warnings: list[IngestionIssue] = Field(default_factory=list)
    errors: list[IngestionIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

