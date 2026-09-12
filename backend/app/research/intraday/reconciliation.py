from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.research.intraday.models import (
    CanonicalIntradayBar,
    DailyBarReference,
    DailyIntradayReconciliationResult,
    DailyReconciliation,
    PilotDataStatus,
)


def reconcile_daily_bar(
    bars: Iterable[CanonicalIntradayBar],
    daily: DailyBarReference | None,
    *,
    data_status: PilotDataStatus,
    price_tolerance: Decimal = Decimal("0.01"),
    volume_tolerance_pct: Decimal = Decimal("1"),
) -> DailyReconciliation:
    rows = sorted(bars, key=lambda row: row.bar_start)
    if not rows:
        raise ValueError("Daily reconciliation requires intraday bars")
    symbol = rows[0].symbol
    trading_date = rows[0].trading_date
    if data_status == PilotDataStatus.SYNTHETIC_TEST_FIXTURE or daily is None:
        return DailyReconciliation(
            symbol=symbol,
            trading_date=trading_date,
            result=DailyIntradayReconciliationResult.INCONCLUSIVE,
            open_diff=None,
            high_diff=None,
            low_diff=None,
            close_diff=None,
            volume_diff=None,
            price_tolerance=price_tolerance,
            volume_tolerance_pct=volume_tolerance_pct,
            notes="Synthetic fixtures are never reconciled as real-source evidence.",
        )
    open_diff = rows[0].open - daily.open
    high_diff = max(row.high for row in rows) - daily.high
    low_diff = min(row.low for row in rows) - daily.low
    close_diff = rows[-1].close - daily.close
    total_volume = None if any(row.volume is None for row in rows) else sum(row.volume or 0 for row in rows)
    volume_diff = None if total_volume is None or daily.volume is None else total_volume - daily.volume
    price_clean = all(abs(value) <= price_tolerance for value in (open_diff, high_diff, low_diff, close_diff))
    volume_pct = None
    if volume_diff is not None and daily.volume:
        volume_pct = abs(Decimal(volume_diff) * Decimal("100") / Decimal(daily.volume))
    volume_clean = volume_pct is None or volume_pct <= volume_tolerance_pct
    if price_clean and volume_clean:
        result = DailyIntradayReconciliationResult.CLEAN
    elif price_clean:
        result = DailyIntradayReconciliationResult.CLEAN_WITH_SOURCE_DIFFERENCES
    else:
        result = DailyIntradayReconciliationResult.MATERIAL_MISMATCH
    return DailyReconciliation(
        symbol=symbol,
        trading_date=trading_date,
        result=result,
        open_diff=open_diff,
        high_diff=high_diff,
        low_diff=low_diff,
        close_diff=close_diff,
        volume_diff=volume_diff,
        price_tolerance=price_tolerance,
        volume_tolerance_pct=volume_tolerance_pct,
        notes="Price differences enforce tolerance; volume-source differences are separately tolerated.",
    )
