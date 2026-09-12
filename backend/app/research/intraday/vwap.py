from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.research.intraday.config import VWAP_VERSION
from app.research.intraday.models import CanonicalIntradayBar, SessionQuality, SessionVwapPoint


def calculate_session_vwap(
    bars: Iterable[CanonicalIntradayBar],
    *,
    session_quality: SessionQuality | None = None,
) -> list[SessionVwapPoint]:
    rows = sorted(bars, key=lambda row: row.bar_start)
    weighted_total = Decimal("0")
    cumulative_volume = 0
    result: list[SessionVwapPoint] = []
    coverage_incomplete = session_quality is not None and not session_quality.strict_usable
    for bar in rows:
        flags: set[str] = set()
        if coverage_incomplete:
            flags.add("INCOMPLETE_SESSION_COVERAGE")
        if bar.volume is None:
            flags.add("VOLUME_MISSING")
            volume = 0
        else:
            volume = bar.volume
        if volume < 0:
            raise ValueError("VWAP cannot consume negative volume")
        typical_price = (bar.high + bar.low + bar.close) / Decimal("3")
        weighted_total += typical_price * volume
        cumulative_volume += volume
        if cumulative_volume == 0:
            flags.add("ZERO_CUMULATIVE_VOLUME")
            vwap = None
        else:
            vwap = weighted_total / Decimal(cumulative_volume)
        result.append(
            SessionVwapPoint(
                symbol=bar.symbol,
                trading_date=bar.trading_date,
                bar_timestamp=bar.bar_end,
                vwap=vwap,
                cumulative_volume=cumulative_volume,
                methodology=f"{VWAP_VERSION}:TYPICAL_PRICE_X_VOLUME_CUMULATIVE",
                quality_flags=tuple(sorted(flags)),
            )
        )
    return result
