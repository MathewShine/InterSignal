from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.features.base import AdjustedDailyBar, safe_divide, simple_return


def positive_day_count(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> int | None:
    daily_returns = trailing_daily_returns(bars, index, window)
    if daily_returns is None:
        return None
    return sum(1 for value in daily_returns if value > 0)


def up_day_ratio(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    count = positive_day_count(bars, index, window)
    if count is None:
        return None
    return safe_divide(Decimal(count), Decimal(window))


def trailing_daily_returns(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> list[Decimal] | None:
    if index < window:
        return None
    values: list[Decimal] = []
    for offset in range(index - window + 1, index + 1):
        value = simple_return(bars[offset].close, bars[offset - 1].close)
        if value is None:
            return None
        values.append(value)
    return values
