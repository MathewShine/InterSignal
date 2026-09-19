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


class MarketProviderCapability(StrEnum):
    INSTRUMENT_MASTER = "INSTRUMENT_MASTER"
    SEARCH = "SEARCH"
    QUOTE = "QUOTE"
    LTP = "LTP"
    OHLC = "OHLC"
    MARKET_DEPTH = "MARKET_DEPTH"
    HISTORICAL_CANDLES = "HISTORICAL_CANDLES"
    STREAMING_QUOTES = "STREAMING_QUOTES"
    STREAMING_DEPTH = "STREAMING_DEPTH"
    INDICES = "INDICES"
    SECTORS = "SECTORS"
    BREADTH = "BREADTH"
    VOLUME = "VOLUME"
    SESSION_STATUS = "SESSION_STATUS"
    FNO = "FNO"
    OPTION_CHAIN = "OPTION_CHAIN"
    CURRENT_UNIVERSE = "CURRENT_UNIVERSE"
    EOD_BREADTH = "EOD_BREADTH"
    EOD_VOLUME_CONTEXT = "EOD_VOLUME_CONTEXT"
    SECTOR_INDEX_CONTEXT = "SECTOR_INDEX_CONTEXT"
    INDEX_SNAPSHOT = "INDEX_SNAPSHOT"


@dataclass(frozen=True, slots=True)
class InterSignalInstrument:
    instrument_id: str
    symbol: str
    display_name: str
    exchange: str
    segment: str
    instrument_type: str
    exchange_token: str | None = None
    groww_symbol: str | None = None
    series: str | None = None
    isin: str | None = None
    underlying: str | None = None
    expiry: date | None = None
    strike: Decimal | None = None
    lot_size: int | None = None
    tick_size: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MarketDepthLevelObservation:
    price: Decimal
    quantity: int


@dataclass(frozen=True, slots=True)
class MarketQuoteObservation:
    instrument: InterSignalInstrument
    timestamp: datetime
    ltp: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    previous_close: Decimal | None = None
    volume: int | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    buy_depth: tuple[MarketDepthLevelObservation, ...] = ()
    sell_depth: tuple[MarketDepthLevelObservation, ...] = ()
    source: str = ""
    session_status: str = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MarketCandleObservation:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = None
    open_interest: int | None = None


@dataclass(frozen=True, slots=True)
class MarketTickObservation:
    instrument_id: str
    exchange: str
    segment: str
    symbol: str
    timestamp: datetime
    ltp: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    buy_depth: tuple[MarketDepthLevelObservation, ...] = ()
    sell_depth: tuple[MarketDepthLevelObservation, ...] = ()
    source: str = ""
    freshness: str = "FRESH"


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
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


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
    index_value: Decimal | None = None


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
    def capabilities(self) -> tuple[MarketProviderCapability | str, ...]:
        raise NotImplementedError

    @property
    def configured(self) -> bool:
        return self.mode != MarketProviderMode.UNAVAILABLE

    @property
    def unavailable_reason(self) -> str | None:
        return None

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

    def list_instruments(self) -> tuple[InterSignalInstrument, ...]:
        return ()

    def search_instruments(self, query: str, *, limit: int = 20) -> tuple[InterSignalInstrument, ...]:
        normalized = query.strip().casefold()
        if not normalized:
            return ()
        ranked = sorted(
            (
                instrument
                for instrument in self.list_instruments()
                if normalized in instrument.symbol.casefold()
                or normalized in instrument.display_name.casefold()
                or normalized in (instrument.underlying or "").casefold()
            ),
            key=lambda instrument: (
                0 if instrument.symbol.casefold() == normalized else 1,
                0 if instrument.symbol.casefold().startswith(normalized) else 1,
                instrument.symbol,
            ),
        )
        return tuple(ranked[: max(1, min(limit, 50))])

    def get_quote(self, symbol: str) -> MarketQuoteObservation | None:
        return None

    def get_candles(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> tuple[MarketCandleObservation, ...]:
        return ()

    def get_sector_constituents(self, sector_id: str) -> tuple[InterSignalInstrument, ...]:
        return ()

    def get_option_expiries(self, underlying: str) -> tuple[str, ...]:
        return ()

    def get_option_contracts(self, underlying: str, expiry: str) -> tuple[str, ...]:
        return ()

    def get_option_chain(self, underlying: str, expiry: str) -> tuple[dict[str, object], ...]:
        return ()


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

    @property
    def configured(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

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
    "InterSignalInstrument",
    "MarketBreadthObservation",
    "MarketCandleObservation",
    "MarketDataProvider",
    "MarketDepthLevelObservation",
    "MarketFreshnessObservation",
    "MarketIndexObservation",
    "MarketProviderCapability",
    "MarketProviderMode",
    "MarketQualityObservation",
    "MarketQuoteObservation",
    "MarketSectorObservation",
    "MarketSessionObservation",
    "MarketTickObservation",
    "MarketUniverseObservation",
    "MarketVolumeObservation",
    "UnavailableMarketDataProvider",
)
