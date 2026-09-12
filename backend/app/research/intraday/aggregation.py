from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.models import CanonicalIntradayBar, IntradayBarQuality


def aggregate_bars(
    bars: Iterable[CanonicalIntradayBar],
    *,
    target_minutes: int,
    calendar: NseCashSessionCalendar,
) -> list[CanonicalIntradayBar]:
    if target_minutes not in {10, 15}:
        raise ValueError("V1 supports deterministic 10m and 15m derivation only")
    grouped: dict[tuple[str, object, int], list[CanonicalIntradayBar]] = defaultdict(list)
    for bar in sorted(bars, key=lambda row: (row.symbol, row.trading_date, row.bar_start)):
        if bar.interval != "5m":
            raise ValueError("Derived bars require canonical 5m input")
        session = calendar.session_for(bar.trading_date)
        bucket = int((bar.bar_start - session.opens_at).total_seconds() // (target_minutes * 60))
        grouped[(bar.symbol, bar.trading_date, bucket)].append(bar)

    expected_source_count = target_minutes // 5
    result: list[CanonicalIntradayBar] = []
    for (_symbol, _date, bucket), source in sorted(grouped.items(), key=lambda item: item[0]):
        first = source[0]
        last = source[-1]
        flags = {flag for bar in source for flag in bar.quality_flags}
        partial = len(source) != expected_source_count
        if partial:
            flags.add("PARTIAL_DERIVED_INTERVAL")
        result.append(
            replace(
                first,
                interval=f"{target_minutes}m",
                bar_start=first.bar_start,
                bar_end=last.bar_end,
                high=max(row.high for row in source),
                low=min(row.low for row in source),
                close=last.close,
                volume=(None if any(row.volume is None for row in source) else sum(row.volume or 0 for row in source)),
                source_provider="DERIVED_FROM_NORMALIZED_5M",
                source_interval="5m",
                source_timestamp=last.source_timestamp,
                session_sequence=bucket + 1,
                is_partial_bar=partial,
                is_missing_context=partial or any(row.is_missing_context for row in source),
                quality_status=(
                    IntradayBarQuality.PARTIAL_SESSION if partial else IntradayBarQuality.COMPLETE
                ),
                quality_flags=tuple(sorted(str(flag) for flag in flags)),
                source_bar_count=len(source),
                provider_vwap=None,
            )
        )
    return result
