from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from app.backtesting.costs.cost_models import FIXED_BPS, SLIPPAGE_MODEL_VERSION
from app.backtesting.costs.slippage import slippage_raw
from app.research.intraday.models import (
    CanonicalIntradayBar,
    EventType,
    ExecutionEvent,
    ExecutionPriceMode,
)


def bars_available_at(
    bars: Iterable[CanonicalIntradayBar], decision_time: datetime
) -> list[CanonicalIntradayBar]:
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("Decision time must be timezone-aware")
    return sorted(
        (bar for bar in bars if bar.bar_end <= decision_time),
        key=lambda bar: bar.bar_end,
    )


def confirmation_bar(
    bars: Iterable[CanonicalIntradayBar], *, window_minutes: int
) -> CanonicalIntradayBar:
    if window_minutes not in {5, 10, 15}:
        raise ValueError("Supported confirmation windows are 5m, 10m, and 15m")
    rows = sorted(bars, key=lambda row: row.bar_end)
    required = window_minutes // 5
    if len(rows) < required:
        raise ValueError("Insufficient completed bars for confirmation")
    candidate = rows[required - 1]
    available = bars_available_at(rows, candidate.bar_end)
    if len(available) < required:
        raise ValueError("Confirmation attempted to consume a partial future bar")
    return candidate


def event_sort_key(event: ExecutionEvent) -> tuple[datetime, int]:
    neutral_precedence = {
        EventType.SESSION_OPEN: 0,
        EventType.BAR_OPEN: 1,
        EventType.OPENING_RANGE_COMPLETE: 2,
        EventType.ENTRY_CONFIRMATION: 3,
        EventType.ENTRY_TRIGGER: 4,
        EventType.ENTRY_EXECUTION: 5,
        EventType.BAR_CLOSE: 6,
        EventType.SESSION_CLOSE: 7,
    }
    # High and low touches deliberately share a precedence. OHLC does not reveal their order.
    precedence = neutral_precedence.get(event.event_type, 5)
    return (event.event_timestamp, precedence)


def order_events(events: Iterable[ExecutionEvent]) -> list[ExecutionEvent]:
    return sorted(events, key=event_sort_key)


@dataclass(frozen=True, slots=True)
class ExecutionPriceModel:
    mode: ExecutionPriceMode
    slippage_bps: Decimal = Decimal("0")

    def resolve(
        self,
        *,
        reference_price: Decimal,
        side: str,
        quantity: Decimal = Decimal("1"),
        next_bar: CanonicalIntradayBar | None = None,
    ) -> Decimal:
        if reference_price <= 0 or quantity <= 0:
            raise ValueError("Execution reference price and quantity must be positive")
        if self.mode == ExecutionPriceMode.NEXT_BAR_OPEN:
            if next_bar is None:
                raise ValueError("NEXT_BAR_OPEN requires a subsequent bar")
            return next_bar.open
        if self.mode == ExecutionPriceMode.FIXED_BPS_SLIPPAGE_OVER_REFERENCE:
            cost = slippage_raw(reference_price * quantity, FIXED_BPS, self.slippage_bps)
            per_unit = cost / quantity
            if side.upper() == "BUY":
                return reference_price + per_unit
            if side.upper() == "SELL":
                return reference_price - per_unit
            raise ValueError("Execution side must be BUY or SELL")
        return reference_price

    def contract(self) -> dict[str, object]:
        return {
            "ordering_responsibility": "REFERENCE_EVENT_ONLY",
            "economics_responsibility": "EXISTING_COST_AND_SLIPPAGE_LAYER",
            "slippage_version": SLIPPAGE_MODEL_VERSION,
            "duplicates_slippage_logic": False,
        }
