from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from app.providers.indices.base import (
    ALLOWED_SECTOR_MAPPING_STATUSES,
    BENCHMARK_INDEXES,
    PRIMARY_BENCHMARK_ID,
    SECONDARY_BENCHMARK_ID,
)
from app.services.nifty500_membership import canonical_symbol

@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    trading_date: date
    close: Decimal


@dataclass(frozen=True, slots=True)
class IndexObservation:
    trading_date: date
    index_id: str
    index_name: str
    close: Decimal


@dataclass(frozen=True, slots=True)
class SectorMapping:
    symbol: str
    isin: str
    sector_name: str
    sector_index_id: str
    valid_from: date | None
    valid_to: date | None
    mapping_source: str
    mapping_status: str
    confidence: str
    notes: str = ""


class BenchmarkProvider:
    name = "benchmark_provider"

    def is_available(self) -> bool:
        raise NotImplementedError

    def return_for(self, trading_date: date, window: int) -> Decimal | None:
        raise NotImplementedError


class UnavailableBenchmarkProvider(BenchmarkProvider):
    name = "UNAVAILABLE_OFFICIAL_BENCHMARK_HISTORY"

    def __init__(self, reason: str = "Official benchmark close history is not present locally.") -> None:
        self.reason = reason

    def is_available(self) -> bool:
        return False

    def return_for(self, trading_date: date, window: int) -> Decimal | None:
        return None


class LocalOfficialIndexContextProvider(BenchmarkProvider):
    name = "LOCAL_OFFICIAL_NSE_INDEX_CONTEXT"

    def __init__(
        self,
        *,
        data_dir: Path,
        trading_sessions: Sequence[date],
        allowed_sector_mapping_statuses: Sequence[str] = ALLOWED_SECTOR_MAPPING_STATUSES,
    ) -> None:
        self.data_dir = data_dir
        self.trading_sessions = tuple(sorted(trading_sessions))
        self.session_index = {session: offset for offset, session in enumerate(self.trading_sessions)}
        self.allowed_sector_mapping_statuses = tuple(allowed_sector_mapping_statuses)
        self.benchmark_records = load_index_records(data_dir / "reference" / "nse" / "indices" / "normalized" / "benchmark_daily.csv")
        self.sector_records = load_index_records(data_dir / "reference" / "nse" / "indices" / "normalized" / "sector_index_daily.csv")
        self.sector_mappings = load_sector_mappings(
            data_dir / "reference" / "nse" / "indices" / "normalized" / "stock_sector_mapping.csv"
        )
        self.reason = "" if self.is_available() else "Official normalized benchmark history is not present locally."

    def is_available(self) -> bool:
        return PRIMARY_BENCHMARK_ID in self.benchmark_records

    def return_for(self, trading_date: date, window: int) -> Decimal | None:
        return self.benchmark_return_for(PRIMARY_BENCHMARK_ID, trading_date, window)

    def benchmark_return_for(self, benchmark_id: str, trading_date: date, window: int) -> Decimal | None:
        return return_for_window(self.benchmark_records, self.trading_sessions, self.session_index, benchmark_id, trading_date, window)

    def benchmark_name(self, benchmark_id: str) -> str:
        rows = self.benchmark_records.get(benchmark_id, {})
        if rows:
            return next(iter(rows.values())).index_name
        return BENCHMARK_INDEXES.get(benchmark_id, benchmark_id)

    def sector_mapping_for(self, symbol: str, trading_date: date) -> SectorMapping:
        normalized = canonical_symbol(symbol)
        mappings = self.sector_mappings.get(normalized, [])
        fallback: SectorMapping | None = None
        saw_mapping = False
        for mapping in mappings:
            saw_mapping = True
            if mapping.mapping_status not in self.allowed_sector_mapping_statuses:
                fallback = fallback or mapping
                continue
            if mapping.valid_from is None:
                continue
            if mapping.valid_from <= trading_date and (mapping.valid_to is None or trading_date <= mapping.valid_to):
                return mapping
        if fallback is not None:
            return fallback
        return SectorMapping(
            symbol=normalized,
            isin="",
            sector_name="",
            sector_index_id="",
            valid_from=None,
            valid_to=None,
            mapping_source="",
            mapping_status="UNAVAILABLE",
            confidence="NONE",
            notes=(
                "No stock-to-sector index mapping was valid for the feature date."
                if saw_mapping
                else "No official stock-to-sector index mapping was available."
            ),
        )

    def sector_return_for(self, sector_index_id: str, trading_date: date, window: int) -> Decimal | None:
        return return_for_window(self.sector_records, self.trading_sessions, self.session_index, sector_index_id, trading_date, window)

    def sector_index_name(self, sector_index_id: str) -> str:
        rows = self.sector_records.get(sector_index_id, {})
        if rows:
            return next(iter(rows.values())).index_name
        return sector_index_id

    def sector_above_sma20(self, sector_index_id: str, trading_date: date) -> bool | None:
        closes = values_for_window(self.sector_records, self.trading_sessions, self.session_index, sector_index_id, trading_date, 19)
        if closes is None:
            return None
        current = closes[-1]
        average = sum(closes, Decimal("0")) / Decimal(len(closes))
        return current > average

    def sector_context_available(self) -> bool:
        return bool(self.sector_records)


def resolve_benchmark_provider(data_dir: Path, trading_sessions: Sequence[date] | None = None) -> BenchmarkProvider:
    provider = LocalOfficialIndexContextProvider(data_dir=data_dir, trading_sessions=trading_sessions or ())
    if provider.is_available():
        return provider
    return UnavailableBenchmarkProvider(provider.reason)


def resolve_relative_strength_context_provider(
    data_dir: Path,
    trading_sessions: Sequence[date],
) -> LocalOfficialIndexContextProvider:
    return LocalOfficialIndexContextProvider(data_dir=data_dir, trading_sessions=trading_sessions)


def return_for_window(
    records: dict[str, dict[date, IndexObservation]],
    trading_sessions: Sequence[date],
    session_index: dict[date, int],
    index_id: str,
    trading_date: date,
    window: int,
) -> Decimal | None:
    values = values_for_window(records, trading_sessions, session_index, index_id, trading_date, window)
    if values is None:
        return None
    previous = values[0]
    current = values[-1]
    if previous <= 0:
        return None
    return current / previous - Decimal("1")


def values_for_window(
    records: dict[str, dict[date, IndexObservation]],
    trading_sessions: Sequence[date],
    session_index: dict[date, int],
    index_id: str,
    trading_date: date,
    window: int,
) -> list[Decimal] | None:
    current_index = session_index.get(trading_date)
    by_date = records.get(index_id)
    if current_index is None or by_date is None or current_index < window:
        return None
    window_sessions = trading_sessions[current_index - window : current_index + 1]
    observations = [by_date.get(session) for session in window_sessions]
    if any(observation is None for observation in observations):
        return None
    return [observation.close for observation in observations if observation is not None]


def load_index_records(path: Path) -> dict[str, dict[date, IndexObservation]]:
    if not path.exists():
        return {}
    records: dict[str, dict[date, IndexObservation]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            trading_date = parse_date(row.get("trading_date"))
            index_id = row.get("benchmark_id") or row.get("sector_index_id") or row.get("index_id") or ""
            close_value = parse_decimal(row.get("close"))
            if trading_date is None or not index_id or close_value is None or close_value <= 0:
                continue
            records[index_id][trading_date] = IndexObservation(
                trading_date=trading_date,
                index_id=index_id,
                index_name=row.get("index_name", ""),
                close=close_value,
            )
    return {index_id: dict(rows) for index_id, rows in records.items()}


def load_sector_mappings(path: Path) -> dict[str, list[SectorMapping]]:
    if not path.exists():
        return {}
    rows: dict[str, list[SectorMapping]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            symbol = canonical_symbol(row.get("symbol", ""))
            if not symbol:
                continue
            rows[symbol].append(
                SectorMapping(
                    symbol=symbol,
                    isin=row.get("isin", ""),
                    sector_name=row.get("sector_name", ""),
                    sector_index_id=row.get("sector_index_id", ""),
                    valid_from=parse_date(row.get("valid_from")),
                    valid_to=parse_date(row.get("valid_to")),
                    mapping_source=row.get("mapping_source", ""),
                    mapping_status=row.get("mapping_status", "UNAVAILABLE"),
                    confidence=row.get("confidence", ""),
                    notes=row.get("notes", ""),
                )
            )
    return {symbol: sorted(mappings, key=mapping_sort_key) for symbol, mappings in rows.items()}


def mapping_sort_key(mapping: SectorMapping) -> tuple[int, date]:
    preferred = 0 if mapping.mapping_status in ALLOWED_SECTOR_MAPPING_STATUSES else 1
    valid_from = mapping.valid_from or date.min
    return preferred, valid_from


def parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None
