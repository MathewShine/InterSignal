from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.market_data import MarketProviderMode


INTERSIGNAL_MARKET_SNAPSHOT_V1 = "INTERSIGNAL_MARKET_SNAPSHOT_V1"


class MarketApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator(
        "generated_at",
        "source_timestamp",
        "received_at",
        "timestamp",
        "session_timestamp",
        check_fields=False,
    )
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market API timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class MarketAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class MarketFreshnessStatus(StrEnum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class MarketSessionStatus(StrEnum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class MarketContextView(MarketApiModel):
    country: str = "INDIA"
    exchange: str = "NSE"
    primary_index: str = "NIFTY_500"
    reference_indices: tuple[str, ...] = ("NIFTY_50",)


class MarketProviderView(MarketApiModel):
    provider_name: str
    mode: MarketProviderMode
    market: str
    capabilities: tuple[str, ...] = ()


class MarketFreshnessView(MarketApiModel):
    source_timestamp: datetime | None = None
    received_at: datetime
    age_seconds: int | None = Field(default=None, ge=0)
    freshness_status: MarketFreshnessStatus


class MarketQualityView(MarketApiModel):
    coverage_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)
    coverage_pct: Decimal | None = Field(default=None, ge=0, le=100)
    missing_count: int = Field(ge=0)


class MarketIndexView(MarketApiModel):
    symbol: str
    name: str
    value: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    previous_close: Decimal | None = None
    timestamp: datetime
    source: str
    freshness: MarketFreshnessStatus


class MarketUniverseView(MarketApiModel):
    name: str
    member_count: int = Field(ge=0)
    as_of_date: date
    membership_kind: str
    source: str


class MarketBreadthView(MarketApiModel):
    advancers: int = Field(ge=0)
    decliners: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    positive_pct: Decimal = Field(ge=0, le=100)
    negative_pct: Decimal = Field(ge=0, le=100)
    above_vwap_pct: Decimal | None = Field(default=None, ge=0, le=100)
    above_prior_close_pct: Decimal = Field(ge=0, le=100)
    quality: MarketQualityView


class MarketSectorView(MarketApiModel):
    sector: str
    return_pct: Decimal | None = None
    advancers: int | None = Field(default=None, ge=0)
    decliners: int | None = Field(default=None, ge=0)
    unchanged: int | None = Field(default=None, ge=0)
    breadth_pct: Decimal | None = Field(default=None, ge=0, le=100)
    relative_strength: Decimal | None = None
    volume_context: Decimal | None = Field(default=None, ge=0)
    quality: MarketQualityView


class MarketVolumeView(MarketApiModel):
    aggregate_traded_value: Decimal = Field(ge=0)
    traded_value_unit: str
    median_relative_volume: Decimal | None = Field(default=None, ge=0)
    above_20d_volume_count: int = Field(ge=0)
    above_20d_volume_pct: Decimal | None = Field(default=None, ge=0, le=100)
    quality: MarketQualityView


class MarketSessionView(MarketApiModel):
    status: MarketSessionStatus
    market_date: date
    session_timestamp: datetime


class MarketAvailabilityDetail(MarketApiModel):
    status: MarketAvailability
    reason: str | None = None


class MarketSectionAvailability(MarketApiModel):
    indices: MarketAvailabilityDetail
    universe: MarketAvailabilityDetail
    breadth: MarketAvailabilityDetail
    sectors: MarketAvailabilityDetail
    volume: MarketAvailabilityDetail
    session: MarketAvailabilityDetail


class MarketLimitationView(MarketApiModel):
    limitation_id: str
    section: str
    summary: str


class MarketMeta(MarketApiModel):
    read_only: bool = True
    strategy_output: bool = False
    market_regime_engine: bool = False
    broker_integration: str = "NOT_CONNECTED"
    live_provider_implemented: bool = False
    internal_paths_exposed: bool = False
    current_membership_only: bool = True
    unavailable_sections: tuple[str, ...] = ()


class MarketSnapshot(MarketApiModel):
    version: str = INTERSIGNAL_MARKET_SNAPSHOT_V1
    generated_at: datetime
    status: MarketAvailability
    market: MarketContextView = Field(default_factory=MarketContextView)
    provider: MarketProviderView
    freshness: MarketFreshnessView
    indices: tuple[MarketIndexView, ...] = ()
    universe: MarketUniverseView | None = None
    breadth: MarketBreadthView | None = None
    sectors: tuple[MarketSectorView, ...] = ()
    volume: MarketVolumeView | None = None
    session: MarketSessionView | None = None
    availability: MarketSectionAvailability
    limitations: tuple[MarketLimitationView, ...] = ()
    meta: MarketMeta = Field(default_factory=MarketMeta)


__all__ = (
    "INTERSIGNAL_MARKET_SNAPSHOT_V1",
    "MarketAvailability",
    "MarketFreshnessStatus",
    "MarketSnapshot",
)
