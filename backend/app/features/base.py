from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, getcontext
from typing import Iterable, Sequence

getcontext().prec = 28

DAILY_FEATURES_VERSION = "DAILY_FEATURES_V1"
TIMEFRAME = "DAILY_EOD"
AVAILABILITY_TIME = "EOD"
NEXT_SESSION_DECISION_INPUT = "NEXT_SESSION_DECISION_INPUT"

STATUS_READY = "READY"
STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED = "CORPORATE_ACTION_LOOKBACK_BLOCKED"
STATUS_MISSING_INPUT_DATA = "MISSING_INPUT_DATA"
STATUS_UNIVERSE_UNCERTAIN = "UNIVERSE_UNCERTAIN"
STATUS_BENCHMARK_UNAVAILABLE = "BENCHMARK_UNAVAILABLE"
STATUS_SECTOR_CONTEXT_UNAVAILABLE = "SECTOR_CONTEXT_UNAVAILABLE"
STATUS_SECTOR_MAPPING_UNAVAILABLE = "SECTOR_MAPPING_UNAVAILABLE"
STATUS_INVALID_SOURCE_ROW = "INVALID_SOURCE_ROW"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class DailyFeatureConfig:
    feature_version: str = DAILY_FEATURES_VERSION
    return_windows: tuple[int, ...] = (1, 2, 3, 5, 10, 20)
    momentum_windows: tuple[int, ...] = (3, 5, 10, 20)
    positive_day_windows: tuple[int, ...] = (5, 10, 20)
    volume_windows: tuple[int, ...] = (5, 20)
    relative_volume_windows: tuple[int, ...] = (5, 20)
    atr_windows: tuple[int, ...] = (5, 14, 20)
    level_windows: tuple[int, ...] = (5, 10, 20, 252)
    prior_level_windows: tuple[int, ...] = (5, 20, 252)
    sma_windows: tuple[int, ...] = (5, 10, 20, 50, 200)
    volatility_windows: tuple[int, ...] = (5, 20)
    range_windows: tuple[int, ...] = (5, 10, 20)
    benchmark_return_windows: tuple[int, ...] = (1, 2, 3, 5, 10, 20)
    benchmark_relative_windows: tuple[int, ...] = (1, 3, 5, 10, 20)
    secondary_benchmark_windows: tuple[int, ...] = (5, 20)
    sector_return_windows: tuple[int, ...] = (1, 3, 5, 10, 20)
    traded_value_method: str = "ADJUSTED_CLOSE_X_ADJUSTED_VOLUME_PROXY"
    atr_methodology: str = "SIMPLE_ROLLING_MEAN"
    volatility_methodology: str = "SAMPLE_STDEV_NON_ANNUALIZED"
    source_dataset: str = "ADJUSTED_RESEARCH_DAILY_NSE"
    universe_name: str = "NIFTY_500"
    universe_version: str = "NIFTY500_MEMBERSHIP_PARTIAL_HISTORY"
    primary_benchmark_id: str = "NIFTY_500"
    secondary_benchmark_id: str = "NIFTY_50"
    benchmark_symbol: str = "NIFTY_500"
    benchmark_context_version: str = "BENCHMARK_CONTEXT_V1"
    sector_context_version: str = "SECTOR_CONTEXT_V1"
    sector_relative_features_status: str = STATUS_SECTOR_MAPPING_UNAVAILABLE


@dataclass(frozen=True, slots=True)
class AdjustedDailyBar:
    trading_date: date
    symbol: str
    isin: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source_file: str
    source: str
    research_usability_status: str
    adjustment_methodology_version: str
    provenance: str = ""


def parse_decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def safe_divide(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def simple_return(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    ratio = safe_divide(current, previous)
    if ratio is None:
        return None
    return ratio - Decimal("1")


def mean_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def median_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def sample_stdev_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    average = mean_decimal(values)
    if average is None:
        return None
    variance = sum((value - average) ** 2 for value in values) / Decimal(len(values) - 1)
    return variance.sqrt()


def clean_decimals(values: Iterable[Decimal | None]) -> list[Decimal]:
    return [value for value in values if value is not None]
