from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from app.research.temporal_validation.config import canonical_hash, json_ready


@dataclass(frozen=True, slots=True)
class IntradayProviderCapabilityManifest:
    provider: str
    exchange: str
    instrument_type: str
    supported_intervals: tuple[str, ...]
    history_start: date | None
    history_end: date | None
    rate_limits: str | None
    adjustment_status: str
    volume_available: bool | None
    vwap_available: bool | None
    timestamp_semantics: str
    known_limitations: tuple[str, ...]
    data_status: str

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))


@dataclass(frozen=True, slots=True)
class IntradayIngestionRequest:
    symbol: str
    instrument_id: str | None
    start_date: date
    end_date: date
    interval: str
    provider: str
    purpose: str
    research_window: str
    request_id: str

    def validate(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("Ingestion end_date precedes start_date")
        if self.interval != "5m":
            raise ValueError("V1 ingestion requests must use canonical 5m")
        if not self.request_id.strip():
            raise ValueError("request_id is required")

    def request_hash(self) -> str:
        self.validate()
        return canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class IntradayIngestionAudit:
    request_id: str
    provider: str
    requested_start: date
    requested_end: date
    received_start: date | None
    received_end: date | None
    row_count: int
    missing_sessions: tuple[str, ...]
    ingestion_timestamp: datetime
    raw_hash: str
    normalization_hash: str
    status: str

    def __post_init__(self) -> None:
        if self.ingestion_timestamp.tzinfo is None or self.ingestion_timestamp.utcoffset() is None:
            raise ValueError("Ingestion audit timestamp must be timezone-aware")

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def audit_hash(self) -> str:
        return canonical_hash(self.snapshot())
