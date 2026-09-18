from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class MarketProviderMode(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    SEEDED = "SEEDED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class MarketQualityObservation:
    coverage_count: int
    expected_count: int
    missing_count: int


@dataclass(frozen=True, slots=True)
class MarketIndexObservation:
    symbol: str
    name: str
    value: Decimal
    change: Decimal | None
    change_pct: Decimal | None
    previous_close: Decimal | None
    timestamp: datetime
    source: str


@dataclass(frozen=True, slots=True)
class MarketUniverseObservation:
    name: str
    member_count: int
    as_of_date: date
    membership_kind: str
    source: str


@dataclass(frozen=True, slots=True)
class MarketBreadthObservation:
    advancers: int
    decliners: int
    unchanged: int
    positive_pct: Decimal
    negative_pct: Decimal
    above_vwap_pct: Decimal | None
    above_prior_close_pct: Decimal
    quality: MarketQualityObservation


@dataclass(frozen=True, slots=True)
class MarketSectorObservation:
    sector: str
    return_pct: Decimal | None
    advancers: int | None
    decliners: int | None
    unchanged: int | None
    breadth_pct: Decimal | None
    relative_strength: Decimal | None
    volume_context: Decimal | None
    quality: MarketQualityObservation


@dataclass(frozen=True, slots=True)
class MarketVolumeObservation:
    aggregate_traded_value: Decimal
    traded_value_unit: str
    median_relative_volume: Decimal | None
    above_20d_volume_count: int
    above_20d_volume_pct: Decimal | None
    quality: MarketQualityObservation


@dataclass(frozen=True, slots=True)
class MarketSessionObservation:
    status: str
    market_date: date
    session_timestamp: datetime


@dataclass(frozen=True, slots=True)
class MarketFreshnessObservation:
    source_timestamp: datetime | None


class MarketDataProvider(ABC):
    """Vendor-neutral, read-only source of normalized market observations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def mode(self) -> MarketProviderMode:
        raise NotImplementedError

    @property
    def market(self) -> str:
        return "INDIA_NSE"

    @property
    @abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_index_snapshot(self) -> tuple[MarketIndexObservation, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_universe_snapshot(self) -> MarketUniverseObservation | None:
        raise NotImplementedError

    @abstractmethod
    def get_sector_snapshot(self) -> tuple[MarketSectorObservation, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_breadth_snapshot(self) -> MarketBreadthObservation | None:
        raise NotImplementedError

    @abstractmethod
    def get_volume_snapshot(self) -> MarketVolumeObservation | None:
        raise NotImplementedError

    @abstractmethod
    def get_market_status(self) -> MarketSessionObservation | None:
        raise NotImplementedError

    @abstractmethod
    def get_freshness(self) -> MarketFreshnessObservation:
        raise NotImplementedError


class UnavailableMarketDataProvider(MarketDataProvider):
    def __init__(self, *, requested_provider: str, reason: str) -> None:
        self.requested_provider = requested_provider
        self.reason = reason

    @property
    def provider_name(self) -> str:
        return self.requested_provider.upper() if self.requested_provider else "NONE"

    @property
    def mode(self) -> MarketProviderMode:
        return MarketProviderMode.UNAVAILABLE

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ()

    def get_index_snapshot(self) -> tuple[MarketIndexObservation, ...]:
        return ()

    def get_universe_snapshot(self) -> MarketUniverseObservation | None:
        return None

    def get_sector_snapshot(self) -> tuple[MarketSectorObservation, ...]:
        return ()

    def get_breadth_snapshot(self) -> MarketBreadthObservation | None:
        return None

    def get_volume_snapshot(self) -> MarketVolumeObservation | None:
        return None

    def get_market_status(self) -> MarketSessionObservation | None:
        return None

    def get_freshness(self) -> MarketFreshnessObservation:
        return MarketFreshnessObservation(source_timestamp=None)


__all__ = (
    "MarketBreadthObservation",
    "MarketDataProvider",
    "MarketFreshnessObservation",
    "MarketIndexObservation",
    "MarketProviderMode",
    "MarketQualityObservation",
    "MarketSectorObservation",
    "MarketSessionObservation",
    "MarketUniverseObservation",
    "MarketVolumeObservation",
    "UnavailableMarketDataProvider",
)
