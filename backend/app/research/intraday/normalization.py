from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.config import CANONICAL_INTERVAL, NORMALIZATION_VERSION
from app.research.intraday.models import CanonicalIntradayBar, IntradayBarQuality
from app.research.temporal_validation.config import canonical_hash


def parse_decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value).replace(",", "").strip())


def parse_timestamp(value: Any, *, allow_naive_exchange_local: bool = False) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if not allow_naive_exchange_local:
            raise ValueError("Source timestamp is naive and has no declared timezone semantics")
        parsed = parsed.replace(tzinfo=ASIA_KOLKATA)
    return parsed.astimezone(ASIA_KOLKATA)


def normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    calendar: NseCashSessionCalendar,
    source_provider: str,
    ingested_at: datetime | None = None,
    allow_naive_exchange_local: bool = False,
) -> list[CanonicalIntradayBar]:
    ingestion_time = ingested_at or datetime.now(timezone.utc)
    if ingestion_time.tzinfo is None or ingestion_time.utcoffset() is None:
        raise ValueError("ingested_at must be timezone-aware")
    prepared: list[tuple[int, Mapping[str, Any], datetime]] = []
    for source_index, row in enumerate(rows):
        timestamp = parse_timestamp(
            row.get("bar_start", row.get("timestamp", row.get("TIMESTAMP"))),
            allow_naive_exchange_local=allow_naive_exchange_local,
        )
        prepared.append((source_index, row, timestamp))

    normalized: list[CanonicalIntradayBar] = []
    for source_index, row, bar_start in prepared:
        trading_date = _date_value(row.get("trading_date"), bar_start.date())
        session = calendar.session_for(trading_date)
        interval = str(row.get("interval", row.get("INTERVAL", CANONICAL_INTERVAL))).lower()
        if interval != CANONICAL_INTERVAL:
            raise ValueError(f"Canonical normalizer accepts only {CANONICAL_INTERVAL}, received {interval}")
        bar_end = bar_start + timedelta(minutes=5)
        source_timestamp = parse_timestamp(
            row.get("source_timestamp", bar_start),
            allow_naive_exchange_local=allow_naive_exchange_local,
        )
        offset_seconds = (bar_start - session.opens_at).total_seconds()
        aligned = offset_seconds >= 0 and offset_seconds % 300 == 0
        sequence = int(offset_seconds // 300) + 1 if aligned else 0
        flags: list[str] = []
        if not aligned or bar_start < session.opens_at or bar_end > session.closes_at:
            flags.append(IntradayBarQuality.SESSION_MISMATCH)
        normalized.append(
            CanonicalIntradayBar(
                instrument_id=_optional_text(row.get("instrument_id")),
                symbol=str(row.get("symbol", row.get("SYMBOL", ""))).strip().upper(),
                isin=_optional_text(row.get("isin")),
                exchange=str(row.get("exchange", "NSE")).strip().upper(),
                trading_date=trading_date,
                interval=interval,
                bar_start=bar_start,
                bar_end=bar_end,
                open=parse_decimal(row.get("open", row.get("OPEN"))),
                high=parse_decimal(row.get("high", row.get("HIGH"))),
                low=parse_decimal(row.get("low", row.get("LOW"))),
                close=parse_decimal(row.get("close", row.get("CLOSE"))),
                volume=_optional_int(row.get("volume", row.get("VOLUME"))),
                source_provider=source_provider,
                source_interval=interval,
                source_timestamp=source_timestamp,
                ingested_at=ingestion_time,
                normalization_version=NORMALIZATION_VERSION,
                session_id=f"NSE:{trading_date.isoformat()}",
                session_sequence=sequence,
                is_partial_bar=False,
                is_missing_context=False,
                quality_status=(
                    IntradayBarQuality.SESSION_MISMATCH if flags else IntradayBarQuality.COMPLETE
                ),
                quality_flags=tuple(str(flag) for flag in flags),
                provider_vwap=_optional_decimal(row.get("provider_vwap", row.get("VWAP"))),
                corporate_action_reference=dict(row.get("corporate_action_reference", {})),
            )
        )
    return normalized


def canonical_bar_row(bar: CanonicalIntradayBar) -> dict[str, Any]:
    return {
        "instrument_id": bar.instrument_id,
        "symbol": bar.symbol,
        "isin": bar.isin,
        "exchange": bar.exchange,
        "trading_date": bar.trading_date.isoformat(),
        "interval": bar.interval,
        "bar_start": bar.bar_start.isoformat(),
        "bar_end": bar.bar_end.isoformat(),
        "open": format(bar.open, "f"),
        "high": format(bar.high, "f"),
        "low": format(bar.low, "f"),
        "close": format(bar.close, "f"),
        "volume": bar.volume,
        "source_provider": bar.source_provider,
        "source_interval": bar.source_interval,
        "source_timestamp": bar.source_timestamp.isoformat(),
        "normalization_version": bar.normalization_version,
        "session_id": bar.session_id,
        "session_sequence": bar.session_sequence,
        "is_partial_bar": bar.is_partial_bar,
        "is_missing_context": bar.is_missing_context,
        "quality_status": str(bar.quality_status),
        "quality_flags": list(bar.quality_flags),
        "source_bar_count": bar.source_bar_count,
        "provider_vwap": None if bar.provider_vwap is None else format(bar.provider_vwap, "f"),
        "corporate_action_reference": bar.corporate_action_reference,
    }


def intraday_dataset_hash(bars: Iterable[CanonicalIntradayBar]) -> str:
    ordered = sorted(
        (canonical_bar_row(bar) for bar in bars),
        key=lambda row: (
            str(row["exchange"]),
            str(row["symbol"]),
            str(row["bar_start"]),
            str(row["interval"]),
            str(row["source_provider"]),
        ),
    )
    return canonical_hash(ordered)


def _optional_text(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(Decimal(str(value).replace(",", "")))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return parse_decimal(value)


def _date_value(value: Any, fallback: date) -> date:
    if value is None:
        return fallback
    return value if isinstance(value, date) else date.fromisoformat(str(value))
