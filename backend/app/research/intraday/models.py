from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class IntradayBarQuality(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL_SESSION = "PARTIAL_SESSION"
    MISSING_BARS = "MISSING_BARS"
    DUPLICATE_BARS = "DUPLICATE_BARS"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    OHLC_INVALID = "OHLC_INVALID"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    SOURCE_GAP = "SOURCE_GAP"
    UNUSABLE = "UNUSABLE"


class PilotDataStatus(StrEnum):
    REAL_SOURCE_DATA = "REAL_SOURCE_DATA"
    LOCAL_REAL_FIXTURE = "LOCAL_REAL_FIXTURE"
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"


class DailyIntradayReconciliationResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_SOURCE_DIFFERENCES = "CLEAN_WITH_SOURCE_DIFFERENCES"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class IntradayArchitectureResult(StrEnum):
    READY_FOR_PILOT_INGESTION = "READY_FOR_PILOT_INGESTION"
    READY_FOR_CONTROLLED_RESEARCH = "READY_FOR_CONTROLLED_RESEARCH"
    METHODOLOGY_FIX_REQUIRED = "METHODOLOGY_FIX_REQUIRED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExecutionOrderingResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_INTRABAR_AMBIGUITY = "CLEAN_WITH_INTRABAR_AMBIGUITY"
    METHODOLOGY_FIX_REQUIRED = "METHODOLOGY_FIX_REQUIRED"
    INCONCLUSIVE = "INCONCLUSIVE"


class IntradayDataQualityResult(StrEnum):
    CLEAN = "CLEAN"
    USABLE_WITH_GAPS = "USABLE_WITH_GAPS"
    POOR = "POOR"
    NO_REAL_DATA_AVAILABLE = "NO_REAL_DATA_AVAILABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class EventType(StrEnum):
    SESSION_OPEN = "SESSION_OPEN"
    BAR_OPEN = "BAR_OPEN"
    BAR_HIGH_TOUCH = "BAR_HIGH_TOUCH"
    BAR_LOW_TOUCH = "BAR_LOW_TOUCH"
    BAR_CLOSE = "BAR_CLOSE"
    OPENING_RANGE_COMPLETE = "OPENING_RANGE_COMPLETE"
    OR_BREAK_UP = "OR_BREAK_UP"
    OR_BREAK_DOWN = "OR_BREAK_DOWN"
    OR_RECLAIM = "OR_RECLAIM"
    ENTRY_CONFIRMATION = "ENTRY_CONFIRMATION"
    ENTRY_TRIGGER = "ENTRY_TRIGGER"
    ENTRY_EXECUTION = "ENTRY_EXECUTION"
    STOP_TRIGGER = "STOP_TRIGGER"
    TARGET_TRIGGER = "TARGET_TRIGGER"
    TIME_EXIT = "TIME_EXIT"
    SESSION_CLOSE = "SESSION_CLOSE"


class AmbiguityPolicy(StrEnum):
    CONSERVATIVE_STOP_FIRST = "CONSERVATIVE_STOP_FIRST"
    OPTIMISTIC_TARGET_FIRST = "OPTIMISTIC_TARGET_FIRST"
    AMBIGUOUS_EXCLUDED = "AMBIGUOUS_EXCLUDED"


class ExecutionPriceMode(StrEnum):
    BAR_CLOSE_CONFIRMATION = "BAR_CLOSE_CONFIRMATION"
    STOP_TRIGGER_PRICE = "STOP_TRIGGER_PRICE"
    TARGET_TRIGGER_PRICE = "TARGET_TRIGGER_PRICE"
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    FIXED_BPS_SLIPPAGE_OVER_REFERENCE = "FIXED_BPS_SLIPPAGE_OVER_REFERENCE"


class FirstTouch(StrEnum):
    STOP_FIRST = "STOP_FIRST"
    TARGET_FIRST = "TARGET_FIRST"
    INTRABAR_SEQUENCE_AMBIGUOUS = "INTRABAR_SEQUENCE_AMBIGUOUS"
    AMBIGUOUS_EXCLUDED = "AMBIGUOUS_EXCLUDED"
    NEITHER = "NEITHER"
    GAP_THROUGH_STOP = "GAP_THROUGH_STOP"
    GAP_THROUGH_TARGET = "GAP_THROUGH_TARGET"


class OrderType(StrEnum):
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    LIMIT_TARGET = "LIMIT_TARGET"
    MARKET_EXIT = "MARKET_EXIT"


@dataclass(frozen=True, slots=True)
class CanonicalIntradayBar:
    instrument_id: str | None
    symbol: str
    isin: str | None
    exchange: str
    trading_date: date
    interval: str
    bar_start: datetime
    bar_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    source_provider: str
    source_interval: str
    source_timestamp: datetime
    ingested_at: datetime
    normalization_version: str
    session_id: str
    session_sequence: int
    is_partial_bar: bool = False
    is_missing_context: bool = False
    quality_status: str = IntradayBarQuality.COMPLETE
    quality_flags: tuple[str, ...] = ()
    source_bar_count: int = 1
    provider_vwap: Decimal | None = None
    corporate_action_reference: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.bar_start, self.bar_end, self.source_timestamp, self.ingested_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Canonical intraday timestamps must be timezone-aware")
        if self.bar_end <= self.bar_start:
            raise ValueError("bar_end must be after bar_start")
        if self.trading_date != self.bar_start.date():
            raise ValueError("trading_date must match exchange-local bar_start date")


@dataclass(frozen=True, slots=True)
class SessionQuality:
    symbol: str
    trading_date: date
    expected_bars: int
    actual_bars: int
    missing_bars: int
    duplicate_bars: int
    coverage_pct: Decimal
    statuses: tuple[str, ...]
    strict_usable: bool
    lenient_usable: bool
    missing_timestamps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OpeningRange:
    symbol: str
    trading_date: date
    window_minutes: int
    completed_at: datetime
    high: Decimal
    low: Decimal
    midpoint: Decimal
    range_pct: Decimal
    range_atr_relative: Decimal | None
    source_bar_count: int


@dataclass(frozen=True, slots=True)
class SessionVwapPoint:
    symbol: str
    trading_date: date
    bar_timestamp: datetime
    vwap: Decimal | None
    cumulative_volume: int
    methodology: str
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    event_timestamp: datetime
    event_type: EventType
    symbol: str
    trading_date: date
    session_sequence: int
    reference_price: Decimal | None
    trigger_price: Decimal | None
    observed_bar: CanonicalIntradayBar | None
    event_source: str
    causal: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_timestamp.tzinfo is None or self.event_timestamp.utcoffset() is None:
            raise ValueError("Execution event timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class FirstTouchResult:
    first_stop_touch_timestamp: datetime | None
    first_target_touch_timestamp: datetime | None
    first_touch: FirstTouch
    policy_resolution: FirstTouch
    ambiguous_same_bar: bool
    bars_to_touch: int | None
    session_to_touch: int | None
    gap_status: str | None
    execution_reference: Decimal | None
    exit_event: ExecutionEvent | None
    research_fill_assumption: str | None


@dataclass(frozen=True, slots=True)
class DailyBarReference:
    symbol: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    source: str


@dataclass(frozen=True, slots=True)
class DailyReconciliation:
    symbol: str
    trading_date: date
    result: DailyIntradayReconciliationResult
    open_diff: Decimal | None
    high_diff: Decimal | None
    low_diff: Decimal | None
    close_diff: Decimal | None
    volume_diff: int | None
    price_tolerance: Decimal
    volume_tolerance_pct: Decimal
    notes: str
