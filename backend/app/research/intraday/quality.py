from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Iterable

from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.models import CanonicalIntradayBar, IntradayBarQuality, SessionQuality


def validate_bar(bar: CanonicalIntradayBar) -> tuple[str, ...]:
    flags = set(bar.quality_flags)
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
        flags.add(IntradayBarQuality.OHLC_INVALID)
    if bar.volume is None:
        flags.add(IntradayBarQuality.SOURCE_GAP)
    elif bar.volume < 0:
        flags.add(IntradayBarQuality.NEGATIVE_VOLUME)
    if bar.bar_end <= bar.bar_start:
        flags.add(IntradayBarQuality.SESSION_MISMATCH)
    duration_seconds = int((bar.bar_end - bar.bar_start).total_seconds())
    if duration_seconds != 300 or bar.bar_start.minute % 5 != 0 or bar.bar_start.second != 0:
        flags.add(IntradayBarQuality.SESSION_MISMATCH)
    return tuple(sorted(str(flag) for flag in flags))


def assess_session_quality(
    bars: Iterable[CanonicalIntradayBar],
    *,
    calendar: NseCashSessionCalendar,
) -> SessionQuality:
    rows = list(bars)
    if not rows:
        raise ValueError("Session quality requires at least one bar")
    symbol = rows[0].symbol
    trading_date = rows[0].trading_date
    if any(row.symbol != symbol or row.trading_date != trading_date for row in rows):
        raise ValueError("Session quality input must contain one symbol/date")
    session = calendar.session_for(trading_date)
    expected = session.expected_starts(5)
    counts = Counter(row.bar_start for row in rows)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    missing = tuple(value for value in expected if counts[value] == 0)
    statuses: set[str] = set()
    if rows != sorted(rows, key=lambda row: row.bar_start):
        statuses.add(IntradayBarQuality.OUT_OF_ORDER)
    if duplicate_count:
        statuses.add(IntradayBarQuality.DUPLICATE_BARS)
    if missing:
        statuses.add(IntradayBarQuality.MISSING_BARS)
        statuses.add(IntradayBarQuality.PARTIAL_SESSION)
    for row in rows:
        statuses.update(validate_bar(row))
        if row.bar_start not in expected:
            statuses.add(IntradayBarQuality.SESSION_MISMATCH)
    fatal = {
        str(IntradayBarQuality.DUPLICATE_BARS),
        str(IntradayBarQuality.OUT_OF_ORDER),
        str(IntradayBarQuality.OHLC_INVALID),
        str(IntradayBarQuality.NEGATIVE_VOLUME),
        str(IntradayBarQuality.SESSION_MISMATCH),
    }
    strict_usable = not statuses and len(rows) == len(expected)
    lenient_usable = not bool(statuses & fatal)
    if not strict_usable and not lenient_usable:
        statuses.add(IntradayBarQuality.UNUSABLE)
    if not statuses:
        statuses.add(IntradayBarQuality.COMPLETE)
    unique_expected = sum(1 for value in expected if counts[value] > 0)
    coverage = Decimal(unique_expected) * Decimal("100") / Decimal(len(expected))
    return SessionQuality(
        symbol=symbol,
        trading_date=trading_date,
        expected_bars=len(expected),
        actual_bars=len(rows),
        missing_bars=len(missing),
        duplicate_bars=duplicate_count,
        coverage_pct=coverage,
        statuses=tuple(sorted(str(status) for status in statuses)),
        strict_usable=strict_usable,
        lenient_usable=lenient_usable,
        missing_timestamps=tuple(value.isoformat() for value in missing),
    )


def summarize_session_quality(qualities: Iterable[SessionQuality]) -> dict[str, int]:
    rows = list(qualities)
    return {
        "total_sessions": len(rows),
        "complete": sum(IntradayBarQuality.COMPLETE in row.statuses for row in rows),
        "partial": sum(IntradayBarQuality.PARTIAL_SESSION in row.statuses for row in rows),
        "missing_bars": sum(IntradayBarQuality.MISSING_BARS in row.statuses for row in rows),
        "duplicates": sum(IntradayBarQuality.DUPLICATE_BARS in row.statuses for row in rows),
        "invalid": sum(IntradayBarQuality.OHLC_INVALID in row.statuses for row in rows),
        "unusable": sum(IntradayBarQuality.UNUSABLE in row.statuses for row in rows),
    }
