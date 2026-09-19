from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_MARKET_INSTRUMENT_V1 = "INTERSIGNAL_MARKET_INSTRUMENT_V1"
INTERSIGNAL_MARKET_CANDLES_V1 = "INTERSIGNAL_MARKET_CANDLES_V1"
INTERSIGNAL_MARKET_SEARCH_V1 = "INTERSIGNAL_MARKET_SEARCH_V1"
INTERSIGNAL_MARKET_STREAM_V1 = "INTERSIGNAL_MARKET_STREAM_V1"
INTERSIGNAL_MARKET_PROVIDER_V1 = "INTERSIGNAL_MARKET_PROVIDER_V1"
INTERSIGNAL_MARKET_INDICES_V1 = "INTERSIGNAL_MARKET_INDICES_V1"
INTERSIGNAL_MARKET_SECTORS_V1 = "INTERSIGNAL_MARKET_SECTORS_V1"
INTERSIGNAL_OPTION_CHAIN_V1 = "INTERSIGNAL_OPTION_CHAIN_V1"


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("generated_at", "timestamp", "last_message_at", "refreshed_at", check_fields=False)
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market workspace timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class MarketInstrumentView(WorkspaceModel):
    instrument_id: str
    symbol: str
    display_name: str
    exchange: str
    segment: str
    instrument_type: str
    underlying: str | None = None
    expiry: date | None = None


class MarketDepthLevelView(WorkspaceModel):
    price: Decimal
    quantity: int = Field(ge=0)


class MarketQuoteView(WorkspaceModel):
    instrument: MarketInstrumentView
    timestamp: datetime
    ltp: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    previous_close: Decimal | None = None
    volume: int | None = Field(default=None, ge=0)
    bid: Decimal | None = None
    ask: Decimal | None = None
    buy_depth: tuple[MarketDepthLevelView, ...] = ()
    sell_depth: tuple[MarketDepthLevelView, ...] = ()
    source: str
    freshness: str
    market_session: str


class MarketSearchResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_SEARCH_V1
    generated_at: datetime
    status: str
    query: str
    total_count: int = Field(ge=0)
    instrument_master_refreshed_at: datetime | None = None
    items: tuple[MarketInstrumentView, ...] = ()
    read_only: bool = True


class MarketQuoteResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_INSTRUMENT_V1
    generated_at: datetime
    status: str
    reason: str | None = None
    provider: str
    provider_mode: str
    capabilities: tuple[str, ...] = ()
    quote: MarketQuoteView | None = None
    read_only: bool = True


class MarketCandleView(WorkspaceModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)


class MarketCandlesResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_CANDLES_V1
    generated_at: datetime
    status: str
    reason: str | None = None
    instrument: MarketInstrumentView | None = None
    source: str
    interval: str
    range: str
    start: datetime
    end: datetime
    freshness: str
    candles: tuple[MarketCandleView, ...] = ()
    last_recorded_candle_at: datetime | None = None
    read_only: bool = True


class MarketProviderStatusResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_PROVIDER_V1
    generated_at: datetime
    provider: str
    mode: str
    configured: bool
    connected: bool
    stream_state: str
    last_message_at: datetime | None = None
    capabilities: tuple[str, ...] = ()
    market_session: str
    reason: str | None = None
    code_ready: bool = True
    credential_ready: bool = False
    read_only: bool = True


class MarketIndexWorkspaceView(WorkspaceModel):
    symbol: str
    name: str
    value: Decimal
    change: Decimal | None = None
    change_pct: Decimal | None = None
    previous_close: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    timestamp: datetime
    source: str
    status: str


class MarketIndicesResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_INDICES_V1
    generated_at: datetime
    status: str
    provider: str
    items: tuple[MarketIndexWorkspaceView, ...] = ()
    read_only: bool = True


class MarketIndexDetailResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_INDICES_V1
    generated_at: datetime
    status: str
    reason: str | None = None
    item: MarketIndexWorkspaceView | None = None
    breadth: dict[str, Any] | None = None
    coverage: dict[str, Any] | None = None
    read_only: bool = True


class MarketSectorWorkspaceView(WorkspaceModel):
    sector_id: str
    name: str
    index_value: Decimal | None = None
    change_pct: Decimal | None = None
    breadth_pct: Decimal | None = None
    relative_volume: Decimal | None = None
    coverage_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)
    advancers: int | None = Field(default=None, ge=0)
    decliners: int | None = Field(default=None, ge=0)
    unchanged: int | None = Field(default=None, ge=0)


class MarketSectorsResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_SECTORS_V1
    generated_at: datetime
    status: str
    provider: str
    items: tuple[MarketSectorWorkspaceView, ...] = ()
    read_only: bool = True


class MarketSectorDetailResponse(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_SECTORS_V1
    generated_at: datetime
    status: str
    reason: str | None = None
    item: MarketSectorWorkspaceView | None = None
    constituents: tuple[MarketInstrumentView, ...] = ()
    leaders: tuple[MarketInstrumentView, ...] = ()
    laggards: tuple[MarketInstrumentView, ...] = ()
    read_only: bool = True


class MarketTickView(WorkspaceModel):
    version: str = INTERSIGNAL_MARKET_STREAM_V1
    event: str = "INSTRUMENT_UPDATE"
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
    source: str
    freshness: str


class MarketOptionLegView(WorkspaceModel):
    trading_symbol: str
    ltp: Decimal | None = None
    open_interest: int | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    iv: Decimal | None = None


class MarketOptionStrikeView(WorkspaceModel):
    strike: Decimal
    ce: MarketOptionLegView | None = None
    pe: MarketOptionLegView | None = None


class OptionChainResponse(WorkspaceModel):
    version: str = INTERSIGNAL_OPTION_CHAIN_V1
    generated_at: datetime
    status: str
    reason: str | None = None
    underlying: str
    expiry: str
    items: tuple[MarketOptionStrikeView, ...] = ()
    read_only: bool = True


__all__ = tuple(name for name in globals() if name.startswith(("INTERSIGNAL_", "Market", "Option")))
