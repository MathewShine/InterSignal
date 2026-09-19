from __future__ import annotations

import csv
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

import httpx

from app.providers.market_data import InterSignalInstrument


GROWW_INSTRUMENT_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"


class GrowwInstrumentCache:
    """Backend-only normalized cache for Groww's public instrument master."""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        downloader: Callable[[], str] | None = None,
        max_age: timedelta = timedelta(hours=24),
        fixture_rows: Iterable[dict[str, object]] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.downloader = downloader or self._download
        self.max_age = max_age
        self._fixture_rows = tuple(fixture_rows) if fixture_rows is not None else None
        self._instruments: tuple[InterSignalInstrument, ...] | None = None
        self._exact_lookup: dict[str, InterSignalInstrument] | None = None
        self._preferred_lookup: dict[str, InterSignalInstrument] | None = None
        self._token_lookup: dict[str, InterSignalInstrument] | None = None

    @property
    def refreshed_at(self) -> datetime | None:
        if self._fixture_rows is not None:
            return datetime.now(timezone.utc)
        if not self.cache_path.exists():
            return None
        return datetime.fromtimestamp(self.cache_path.stat().st_mtime, tz=timezone.utc)

    def refresh(self, *, force: bool = False) -> tuple[InterSignalInstrument, ...]:
        if self._fixture_rows is not None:
            self._instruments = self._normalize_rows(self._fixture_rows)
            self._invalidate_lookups()
            return self._instruments
        refreshed = self.refreshed_at
        stale = refreshed is None or datetime.now(timezone.utc) - refreshed > self.max_age
        if force or stale:
            content = self.downloader()
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8", newline="")
            temporary.replace(self.cache_path)
        self._instruments = self._read_cache()
        self._invalidate_lookups()
        return self._instruments

    def instruments(self) -> tuple[InterSignalInstrument, ...]:
        if self._instruments is not None:
            return self._instruments
        if self._fixture_rows is not None or self.cache_path.exists():
            return self.refresh()
        return ()

    def search(self, query: str, *, limit: int = 20) -> tuple[InterSignalInstrument, ...]:
        normalized = query.strip().casefold()
        if not normalized:
            return ()
        ranked = sorted(
            (
                instrument
                for instrument in self.instruments()
                if normalized in instrument.symbol.casefold()
                or normalized in instrument.display_name.casefold()
                or normalized in (instrument.underlying or "").casefold()
            ),
            key=lambda instrument: (
                0 if instrument.symbol.casefold() == normalized else 1,
                0 if instrument.symbol.casefold().startswith(normalized) else 1,
                0 if instrument.exchange == "NSE" else 1,
                0 if instrument.segment == "CASH" else 1,
                instrument.instrument_type != "INDEX",
                instrument.symbol,
            ),
        )
        return tuple(ranked[: max(1, min(limit, 50))])

    def find(self, symbol: str) -> InterSignalInstrument | None:
        requested = symbol.strip().upper()
        provider_symbol = requested.replace("_", "-")
        self._ensure_lookups()
        exact = self._exact_lookup or {}
        preferred = self._preferred_lookup or {}
        return (
            exact.get(requested)
            or exact.get(provider_symbol)
            or preferred.get(requested)
            or preferred.get(self._identity(requested))
        )

    @staticmethod
    def _identity(value: str) -> str:
        return "".join(character for character in value.upper() if character.isalnum())

    def find_by_exchange_token(self, token: object) -> InterSignalInstrument | None:
        normalized = str(token or "").strip()
        if not normalized:
            return None
        self._ensure_lookups()
        return (self._token_lookup or {}).get(normalized)

    @staticmethod
    def _preference(instrument: InterSignalInstrument) -> tuple[int, int, int, str]:
        return (
            0 if instrument.exchange == "NSE" else 1,
            0 if instrument.segment == "CASH" else 1,
            0 if instrument.expiry is None else 1,
            instrument.instrument_id,
        )

    def _invalidate_lookups(self) -> None:
        self._exact_lookup = None
        self._preferred_lookup = None
        self._token_lookup = None

    def _ensure_lookups(self) -> None:
        if self._exact_lookup is not None:
            return
        exact: dict[str, InterSignalInstrument] = {}
        preferred: dict[str, InterSignalInstrument] = {}
        tokens: dict[str, InterSignalInstrument] = {}
        for instrument in self.instruments():
            exact[instrument.instrument_id.upper()] = instrument
            if instrument.groww_symbol:
                exact[instrument.groww_symbol.upper()] = instrument
            if instrument.exchange_token:
                tokens[instrument.exchange_token] = instrument
            for key in {
                instrument.symbol.upper(),
                self._identity(instrument.symbol),
                self._identity(instrument.display_name),
            }:
                current = preferred.get(key)
                if current is None or self._preference(instrument) < self._preference(current):
                    preferred[key] = instrument
        self._exact_lookup = exact
        self._preferred_lookup = preferred
        self._token_lookup = tokens

    @staticmethod
    def _download() -> str:
        response = httpx.get(GROWW_INSTRUMENT_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def _read_cache(self) -> tuple[InterSignalInstrument, ...]:
        if not self.cache_path.exists():
            return ()
        with self.cache_path.open("r", encoding="utf-8-sig", newline="") as handle:
            return self._normalize_rows(csv.DictReader(handle))

    @classmethod
    def from_csv_text(cls, text: str, *, cache_path: str | Path = "fixture.csv") -> "GrowwInstrumentCache":
        return cls(cache_path, fixture_rows=csv.DictReader(StringIO(text)))

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _integer(value: object) -> int | None:
        decimal = GrowwInstrumentCache._decimal(value)
        return int(decimal) if decimal is not None else None

    @staticmethod
    def _date(value: object) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    @classmethod
    def _normalize_rows(cls, rows: Iterable[dict[str, object]]) -> tuple[InterSignalInstrument, ...]:
        instruments: list[InterSignalInstrument] = []
        for row in rows:
            exchange = str(row.get("exchange") or "").strip().upper()
            symbol = str(row.get("trading_symbol") or "").strip().upper()
            segment = str(row.get("segment") or "CASH").strip().upper()
            if not exchange or not symbol:
                continue
            raw_type = str(row.get("instrument_type") or "UNKNOWN").strip().upper()
            instrument_type = "INDEX" if raw_type in {"INDEX", "IDX"} else raw_type
            instruments.append(
                InterSignalInstrument(
                    instrument_id=f"{exchange}:{segment}:{symbol}",
                    symbol=symbol,
                    display_name=str(row.get("name") or symbol).strip() or symbol,
                    exchange=exchange,
                    segment=segment,
                    instrument_type=instrument_type,
                    exchange_token=str(row.get("exchange_token") or "").strip() or None,
                    groww_symbol=str(row.get("groww_symbol") or "").strip() or None,
                    series=str(row.get("series") or "").strip() or None,
                    isin=str(row.get("isin") or "").strip() or None,
                    underlying=str(row.get("underlying_symbol") or "").strip() or None,
                    expiry=cls._date(row.get("expiry_date")),
                    strike=cls._decimal(row.get("strike_price")),
                    lot_size=cls._integer(row.get("lot_size")),
                    tick_size=cls._decimal(row.get("tick_size")),
                )
            )
        return tuple(sorted(instruments, key=lambda item: (item.exchange, item.segment, item.symbol, item.expiry or date.max)))


__all__ = ("GROWW_INSTRUMENT_URL", "GrowwInstrumentCache")
