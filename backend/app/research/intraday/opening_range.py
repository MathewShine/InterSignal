from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.models import CanonicalIntradayBar, OpeningRange


def calculate_opening_range(
    bars: Iterable[CanonicalIntradayBar],
    *,
    window_minutes: int,
    calendar: NseCashSessionCalendar,
    daily_atr: Decimal | None = None,
) -> OpeningRange:
    if window_minutes not in {5, 10, 15, 30}:
        raise ValueError("OPENING_RANGE_V1 supports 5m, 10m, 15m, and 30m windows")
    rows = sorted(bars, key=lambda row: row.bar_start)
    if not rows:
        raise ValueError("Opening range requires bars")
    symbol = rows[0].symbol
    trading_date = rows[0].trading_date
    if any(row.symbol != symbol or row.trading_date != trading_date for row in rows):
        raise ValueError("Opening range input must contain one symbol/date")
    session = calendar.session_for(trading_date)
    cutoff = session.opens_at + timedelta(minutes=window_minutes)
    eligible = [row for row in rows if row.bar_start >= session.opens_at and row.bar_end <= cutoff]
    expected_count = window_minutes // 5
    if len(eligible) != expected_count:
        raise ValueError(f"Opening range {window_minutes}m requires {expected_count} complete 5m bars")
    high = max(row.high for row in eligible)
    low = min(row.low for row in eligible)
    midpoint = (high + low) / Decimal("2")
    range_pct = (high - low) * Decimal("100") / midpoint if midpoint else Decimal("0")
    atr_relative = (high - low) / daily_atr if daily_atr and daily_atr > 0 else None
    return OpeningRange(
        symbol=symbol,
        trading_date=trading_date,
        window_minutes=window_minutes,
        completed_at=cutoff,
        high=high,
        low=low,
        midpoint=midpoint,
        range_pct=range_pct,
        range_atr_relative=atr_relative,
        source_bar_count=len(eligible),
    )


def opening_range_break_state(
    bar: CanonicalIntradayBar,
    opening_range: OpeningRange,
    *,
    prior_close: Decimal | None = None,
) -> tuple[str, ...]:
    if bar.bar_end <= opening_range.completed_at:
        return ()
    events: list[str] = []
    if bar.high > opening_range.high:
        events.append("OR_BREAK_UP")
    if bar.low < opening_range.low:
        events.append("OR_BREAK_DOWN")
    if prior_close is not None and prior_close < opening_range.low <= bar.close:
        events.append("OR_RECLAIM")
    return tuple(events)
