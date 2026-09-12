from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from app.research.intraday.config import FIRST_TOUCH_ENGINE_VERSION
from app.research.intraday.models import (
    AmbiguityPolicy,
    CanonicalIntradayBar,
    EventType,
    ExecutionEvent,
    FirstTouch,
    FirstTouchResult,
)

LIMIT_FILL_ASSUMPTION = "ASSUMED_FILLED_ON_TOUCH"


def evaluate_first_touch(
    *,
    entry_timestamp: datetime,
    stop_price: Decimal,
    target_price: Decimal,
    bars: Iterable[CanonicalIntradayBar],
    max_holding_date: date,
    ambiguity_policy: AmbiguityPolicy = AmbiguityPolicy.CONSERVATIVE_STOP_FIRST,
    time_exit_at_final_close: bool = False,
) -> FirstTouchResult:
    if entry_timestamp.tzinfo is None or entry_timestamp.utcoffset() is None:
        raise ValueError("Entry timestamp must be timezone-aware")
    if stop_price >= target_price:
        raise ValueError("Long-position stop must be below target")
    rows = sorted(
        (
            bar
            for bar in bars
            if bar.bar_start >= entry_timestamp and bar.trading_date <= max_holding_date
        ),
        key=lambda bar: (bar.bar_start, bar.session_sequence),
    )
    session_dates = sorted({bar.trading_date for bar in rows})
    for index, bar in enumerate(rows, start=1):
        session_number = session_dates.index(bar.trading_date) + 1
        if bar.trading_date > entry_timestamp.astimezone(bar.bar_start.tzinfo).date() and bar.session_sequence == 1:
            if bar.open <= stop_price:
                return _result(
                    first_touch=FirstTouch.GAP_THROUGH_STOP,
                    policy_resolution=FirstTouch.GAP_THROUGH_STOP,
                    stop_timestamp=bar.bar_start,
                    target_timestamp=None,
                    ambiguous=False,
                    index=index,
                    session_number=session_number,
                    bar=bar,
                    event_type=EventType.STOP_TRIGGER,
                    trigger_price=stop_price,
                    execution_reference=bar.open,
                    gap_status="GAP_THROUGH_STOP",
                )
            if bar.open >= target_price:
                return _result(
                    first_touch=FirstTouch.GAP_THROUGH_TARGET,
                    policy_resolution=FirstTouch.GAP_THROUGH_TARGET,
                    stop_timestamp=None,
                    target_timestamp=bar.bar_start,
                    ambiguous=False,
                    index=index,
                    session_number=session_number,
                    bar=bar,
                    event_type=EventType.TARGET_TRIGGER,
                    trigger_price=target_price,
                    execution_reference=bar.open,
                    gap_status="GAP_THROUGH_TARGET",
                )
        stop_touched = bar.low <= stop_price
        target_touched = bar.high >= target_price
        if stop_touched and target_touched:
            resolution = {
                AmbiguityPolicy.CONSERVATIVE_STOP_FIRST: FirstTouch.STOP_FIRST,
                AmbiguityPolicy.OPTIMISTIC_TARGET_FIRST: FirstTouch.TARGET_FIRST,
                AmbiguityPolicy.AMBIGUOUS_EXCLUDED: FirstTouch.AMBIGUOUS_EXCLUDED,
            }[ambiguity_policy]
            event_type = EventType.STOP_TRIGGER if resolution == FirstTouch.STOP_FIRST else EventType.TARGET_TRIGGER
            event = None
            execution_reference = None
            if resolution != FirstTouch.AMBIGUOUS_EXCLUDED:
                trigger = stop_price if resolution == FirstTouch.STOP_FIRST else target_price
                event = _event(bar, event_type, trigger, trigger, {"intrabar_sequence": "UNKNOWN", "policy_resolution": resolution})
                execution_reference = trigger
            return FirstTouchResult(
                first_stop_touch_timestamp=bar.bar_end,
                first_target_touch_timestamp=bar.bar_end,
                first_touch=FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS,
                policy_resolution=resolution,
                ambiguous_same_bar=True,
                bars_to_touch=index,
                session_to_touch=session_number,
                gap_status=None,
                execution_reference=execution_reference,
                exit_event=event,
                research_fill_assumption=(None if event is None else LIMIT_FILL_ASSUMPTION),
            )
        if stop_touched:
            return _result(
                first_touch=FirstTouch.STOP_FIRST,
                policy_resolution=FirstTouch.STOP_FIRST,
                stop_timestamp=bar.bar_end,
                target_timestamp=None,
                ambiguous=False,
                index=index,
                session_number=session_number,
                bar=bar,
                event_type=EventType.STOP_TRIGGER,
                trigger_price=stop_price,
                execution_reference=stop_price,
                gap_status=None,
            )
        if target_touched:
            return _result(
                first_touch=FirstTouch.TARGET_FIRST,
                policy_resolution=FirstTouch.TARGET_FIRST,
                stop_timestamp=None,
                target_timestamp=bar.bar_end,
                ambiguous=False,
                index=index,
                session_number=session_number,
                bar=bar,
                event_type=EventType.TARGET_TRIGGER,
                trigger_price=target_price,
                execution_reference=target_price,
                gap_status=None,
            )
    if time_exit_at_final_close and rows:
        last = rows[-1]
        event = _event(last, EventType.TIME_EXIT, last.close, None, {"configured_final_session_close": True})
    else:
        event = None
    return FirstTouchResult(
        first_stop_touch_timestamp=None,
        first_target_touch_timestamp=None,
        first_touch=FirstTouch.NEITHER,
        policy_resolution=FirstTouch.NEITHER,
        ambiguous_same_bar=False,
        bars_to_touch=None,
        session_to_touch=None,
        gap_status=None,
        execution_reference=None if event is None else event.reference_price,
        exit_event=event,
        research_fill_assumption=None,
    )


def _result(
    *,
    first_touch: FirstTouch,
    policy_resolution: FirstTouch,
    stop_timestamp: datetime | None,
    target_timestamp: datetime | None,
    ambiguous: bool,
    index: int,
    session_number: int,
    bar: CanonicalIntradayBar,
    event_type: EventType,
    trigger_price: Decimal,
    execution_reference: Decimal,
    gap_status: str | None,
) -> FirstTouchResult:
    event_timestamp = bar.bar_start if gap_status else bar.bar_end
    event = _event(
        bar,
        event_type,
        execution_reference,
        trigger_price,
        {"gap_status": gap_status, "engine_version": FIRST_TOUCH_ENGINE_VERSION},
        event_timestamp=event_timestamp,
    )
    return FirstTouchResult(
        first_stop_touch_timestamp=stop_timestamp,
        first_target_touch_timestamp=target_timestamp,
        first_touch=first_touch,
        policy_resolution=policy_resolution,
        ambiguous_same_bar=ambiguous,
        bars_to_touch=index,
        session_to_touch=session_number,
        gap_status=gap_status,
        execution_reference=execution_reference,
        exit_event=event,
        research_fill_assumption=LIMIT_FILL_ASSUMPTION,
    )


def _event(
    bar: CanonicalIntradayBar,
    event_type: EventType,
    reference_price: Decimal,
    trigger_price: Decimal | None,
    metadata: dict[str, object],
    *,
    event_timestamp: datetime | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_timestamp=event_timestamp or bar.bar_end,
        event_type=event_type,
        symbol=bar.symbol,
        trading_date=bar.trading_date,
        session_sequence=bar.session_sequence,
        reference_price=reference_price,
        trigger_price=trigger_price,
        observed_bar=bar,
        event_source=FIRST_TOUCH_ENGINE_VERSION,
        causal=True,
        metadata=metadata,
    )
