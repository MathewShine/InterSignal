from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from app.features.base import AdjustedDailyBar, mean_decimal, median_decimal, safe_divide


def daily_traded_value(bar: AdjustedDailyBar) -> Decimal:
    return bar.close * bar.volume


def rolling_median_traded_value(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    values = [daily_traded_value(bar) for bar in bars[index - window + 1 : index + 1]]
    return median_decimal(values)


def rolling_average_volume(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    return mean_decimal([bar.volume for bar in bars[index - window + 1 : index + 1]])


def relative_volume_vs_prior_median(bars: Sequence[AdjustedDailyBar], index: int, window: int) -> Decimal | None:
    if index < window:
        return None
    denominator = median_decimal([bar.volume for bar in bars[index - window : index]])
    return safe_divide(bars[index].volume, denominator)
