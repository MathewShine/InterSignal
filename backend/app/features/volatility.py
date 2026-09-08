from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.features.base import AdjustedDailyBar, mean_decimal, safe_divide, sample_stdev_decimal, simple_return


def true_range(bars: Sequence[AdjustedDailyBar], index: int) -> Decimal | None:
    if index == 0:
        return None
    current = bars[index]
    previous_close = bars[index - 1].close
    return max(
        current.high - current.low,
        abs(current.high - previous_close),
        abs(current.low - previous_close),
    )


def simple_atr(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    values = [true_range(bars, offset) for offset in range(index - window + 1, index + 1)]
    if any(value is None for value in values):
        return None
    return mean_decimal([value for value in values if value is not None])


def atr_percent(atr: Decimal | None, close: Decimal) -> Decimal | None:
    return safe_divide(atr, close)


def rolling_return_volatility(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    values = [
        simple_return(bars[offset].close, bars[offset - 1].close)
        for offset in range(index - window + 1, index + 1)
    ]
    if any(value is None for value in values):
        return None
    return sample_stdev_decimal([value for value in values if value is not None])
