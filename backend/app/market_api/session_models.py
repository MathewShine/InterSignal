from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_MARKET_SESSION_V1 = "INTERSIGNAL_MARKET_SESSION_V1"
INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1 = "INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1"


class MarketSessionState(StrEnum):
    CREATED = "CREATED"
    PRE_OPEN = "PRE_OPEN"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class MarketObservationEventType(StrEnum):
    SESSION_CREATED = "SESSION_CREATED"
    PROVIDER_CONNECTED = "PROVIDER_CONNECTED"
    PROVIDER_DISCONNECTED = "PROVIDER_DISCONNECTED"
    PROVIDER_RECONNECTED = "PROVIDER_RECONNECTED"
    STREAM_READY = "STREAM_READY"
    SUBSCRIBED = "SUBSCRIBED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    TICK_RECEIVED = "TICK_RECEIVED"
    INDEX_UPDATE = "INDEX_UPDATE"
    BREADTH_UPDATE = "BREADTH_UPDATE"
    SECTOR_UPDATE = "SECTOR_UPDATE"
    SUMMARY_SNAPSHOT = "SUMMARY_SNAPSHOT"
    STALE_DATA_DETECTED = "STALE_DATA_DETECTED"
    STALE_DATA_RECOVERED = "STALE_DATA_RECOVERED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    SESSION_OPEN = "SESSION_OPEN"
    SESSION_CLOSED = "SESSION_CLOSED"
    SESSION_COMPLETED = "SESSION_COMPLETED"


class TickRecordingMode(StrEnum):
    NONE = "NONE"
    SAMPLED = "SAMPLED"
    SELECTED = "SELECTED"
    ALL = "ALL"


class MarketSessionVerdict(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


class SessionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "started_at",
        "ended_at",
        "first_tick_at",
        "last_tick_at",
        "last_provider_heartbeat_at",
        "last_market_event_at",
        "timestamp",
        "source_timestamp",
        "received_at",
        "detected_at",
        "recovered_at",
        check_fields=False,
    )
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market observation timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class MarketCoverageSummary(SessionModel):
    expected_instruments: tuple[str, ...] = ()
    active_instruments: tuple[str, ...] = ()
    observed_instruments: tuple[str, ...] = ()
    missing_instruments: tuple[str, ...] = ()
    coverage_pct: float = Field(default=0, ge=0, le=100)


class MarketInstrumentObservation(SessionModel):
    instrument_id: str
    first_update_at: datetime | None = None
    last_update_at: datetime | None = None
    last_source_timestamp: datetime | None = None
    update_count: int = Field(default=0, ge=0)
    stale_periods: int = Field(default=0, ge=0)


class MarketObservationSession(SessionModel):
    version: str = INTERSIGNAL_MARKET_SESSION_V1
    session_id: str
    market: str = "INDIA_NSE"
    market_date: date
    provider: str
    provider_mode: str
    started_at: datetime
    ended_at: datetime | None = None
    exchange_session_state: str = "UNKNOWN"
    status: MarketSessionState = MarketSessionState.CREATED
    instrument_count: int = Field(default=0, ge=0)
    stream_state: str = "NOT_AVAILABLE"
    first_tick_at: datetime | None = None
    last_tick_at: datetime | None = None
    tick_count: int = Field(default=0, ge=0)
    disconnect_count: int = Field(default=0, ge=0)
    reconnect_count: int = Field(default=0, ge=0)
    stale_interval_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    summary_snapshot_count: int = Field(default=0, ge=0)
    last_provider_heartbeat_at: datetime | None = None
    last_market_event_at: datetime | None = None
    coverage_summary: MarketCoverageSummary = Field(default_factory=MarketCoverageSummary)
    monitored_instruments: tuple[MarketInstrumentObservation, ...] = ()
    notes: tuple[str, ...] = ()
    verdict: MarketSessionVerdict | None = None
    warnings: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    read_only: bool = True


class MarketObservationEvent(SessionModel):
    version: str = INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1
    event_id: str
    session_id: str
    timestamp: datetime
    event_type: MarketObservationEventType
    provider: str
    instrument_id: str | None = None
    source_timestamp: datetime | None = None
    received_at: datetime
    freshness: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    reason_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketSessionSnapshot(SessionModel):
    version: str = INTERSIGNAL_MARKET_SESSION_V1
    session_id: str
    timestamp: datetime
    provider_state: str
    stream_state: str
    last_tick_age_seconds: float | None = Field(default=None, ge=0)
    index_states: tuple[MarketInstrumentObservation, ...] = ()
    subscription_count: int = Field(default=0, ge=0)
    coverage: MarketCoverageSummary = Field(default_factory=MarketCoverageSummary)
    breadth_available: bool = False
    sector_available: bool = False
    error_count: int = Field(default=0, ge=0)
    reconnect_count: int = Field(default=0, ge=0)


class MarketSessionSummary(SessionModel):
    version: str = INTERSIGNAL_MARKET_SESSION_V1
    session: MarketObservationSession
    duration_seconds: float = Field(default=0, ge=0)
    uptime_pct: float = Field(default=100, ge=0, le=100)
    observed_instruments: tuple[str, ...] = ()
    coverage: MarketCoverageSummary = Field(default_factory=MarketCoverageSummary)
    summary_snapshot_count: int = Field(default=0, ge=0)
    criteria: dict[str, bool] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()


class MarketSessionListResponse(SessionModel):
    version: str = INTERSIGNAL_MARKET_SESSION_V1
    generated_at: datetime
    items: tuple[MarketObservationSession, ...] = ()


class MarketSessionEventsResponse(SessionModel):
    version: str = INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1
    generated_at: datetime
    session_id: str
    items: tuple[MarketObservationEvent, ...] = ()


class MarketCurrentSessionResponse(SessionModel):
    version: str = INTERSIGNAL_MARKET_SESSION_V1
    generated_at: datetime
    session: MarketObservationSession | None = None


__all__ = (
    "INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1",
    "INTERSIGNAL_MARKET_SESSION_V1",
    "MarketCoverageSummary",
    "MarketCurrentSessionResponse",
    "MarketInstrumentObservation",
    "MarketObservationEvent",
    "MarketObservationEventType",
    "MarketObservationSession",
    "MarketSessionEventsResponse",
    "MarketSessionListResponse",
    "MarketSessionSnapshot",
    "MarketSessionState",
    "MarketSessionSummary",
    "MarketSessionVerdict",
    "TickRecordingMode",
)
