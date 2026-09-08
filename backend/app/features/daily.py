from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.features.base import AdjustedDailyBar, mean_decimal, simple_return


def trailing_return(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    return simple_return(bars[index].close, bars[index - window].close)


def simple_moving_average(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    values = [bar.close for bar in bars[index - window + 1 : index + 1]]
    return mean_decimal(values)
