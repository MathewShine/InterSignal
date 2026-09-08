from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.features.base import AdjustedDailyBar, safe_divide


def rolling_high(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    return max(bar.high for bar in bars[index - window + 1 : index + 1])


def rolling_low(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    return min(bar.low for bar in bars[index - window + 1 : index + 1])


def prior_high(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    return max(bar.high for bar in bars[index - window : index])


def prior_low(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    return min(bar.low for bar in bars[index - window : index])


def distance_to_level(close: Decimal, level: Decimal | None) -> Decimal | None:
    ratio = safe_divide(close, level)
    if ratio is None:
        return None
    return ratio - Decimal("1")


def candle_anatomy(bar: AdjustedDailyBar) -> dict[str, Decimal | None]:
    daily_range = bar.high - bar.low
    body = abs(bar.close - bar.open)
    upper_wick = bar.high - max(bar.open, bar.close)
    lower_wick = min(bar.open, bar.close) - bar.low
    close_location = None
    if daily_range != 0:
        close_location = ((bar.close - bar.low) - (bar.high - bar.close)) / daily_range
    return {
        "daily_range_pct": safe_divide(daily_range, bar.close),
        "body_pct": safe_divide(body, bar.close),
        "upper_wick_pct": safe_divide(upper_wick, bar.close),
        "lower_wick_pct": safe_divide(lower_wick, bar.close),
        "close_location_value": close_location,
    }


def gap_open_pct(bars: Sequence[AdjustedDailyBar], index: int) -> Decimal | None:
    if index == 0:
        return None
    ratio = safe_divide(bars[index].open, bars[index - 1].close)
    if ratio is None:
        return None
    return ratio - Decimal("1")


def range_width_pct(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    high = rolling_high(bars, index, window)
    low = rolling_low(bars, index, window)
    if high is None or low is None:
        return None
    return safe_divide(high - low, bars[index].close)
