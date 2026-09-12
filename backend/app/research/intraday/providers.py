from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.models import CanonicalIntradayBar, PilotDataStatus, SessionQuality
from app.research.intraday.normalization import normalize_rows
from app.research.intraday.quality import assess_session_quality


class IntradayDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_bars(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: str = "5m",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def normalize_bars(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        calendar: NseCashSessionCalendar,
        ingested_at: datetime | None = None,
    ) -> list[CanonicalIntradayBar]:
        metadata = self.provider_metadata()
        return normalize_rows(
            rows,
            calendar=calendar,
            source_provider=self.name,
            ingested_at=ingested_at,
            allow_naive_exchange_local=metadata.get("timestamp_semantics") == "NAIVE_EXCHANGE_LOCAL_ASIA_KOLKATA",
        )

    @abstractmethod
    def provider_metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def supported_intervals(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def supported_history(self) -> tuple[date | None, date | None]:
        raise NotImplementedError

    def validate_session(
        self,
        bars: Iterable[CanonicalIntradayBar],
        *,
        calendar: NseCashSessionCalendar,
    ) -> SessionQuality:
        return assess_session_quality(bars, calendar=calendar)


class FileOrLocalFixtureProvider(IntradayDataProvider):
    name = "FILE_OR_LOCAL_FIXTURE_PROVIDER"

    def __init__(
        self,
        path: str | Path,
        *,
        data_status: PilotDataStatus,
        timestamp_semantics: str = "NAIVE_EXCHANGE_LOCAL_ASIA_KOLKATA",
        provenance: str,
    ) -> None:
        self.path = Path(path)
        self.data_status = data_status
        self.timestamp_semantics = timestamp_semantics
        self.provenance = provenance
        if data_status == PilotDataStatus.LOCAL_REAL_FIXTURE and not provenance.strip():
            raise ValueError("Local real fixtures require provenance")

    def fetch_bars(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: str = "5m",
    ) -> list[dict[str, Any]]:
        if interval not in self.supported_intervals():
            raise ValueError(f"Unsupported interval: {interval}")
        with self.path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        selected = []
        for row in rows:
            if symbol and row.get("SYMBOL", row.get("symbol", "")).upper() != symbol.upper():
                continue
            timestamp_text = row.get("TIMESTAMP", row.get("timestamp", ""))
            row_date = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00")).date()
            if start_date and row_date < start_date:
                continue
            if end_date and row_date > end_date:
                continue
            selected.append(row)
        return selected

    def provider_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "path": str(self.path),
            "data_status": self.data_status,
            "timestamp_semantics": self.timestamp_semantics,
            "provenance": self.provenance,
            "network_calls": False,
        }

    def supported_intervals(self) -> tuple[str, ...]:
        return ("5m",)

    def supported_history(self) -> tuple[date | None, date | None]:
        rows = self.fetch_bars()
        if not rows:
            return (None, None)
        dates = [datetime.fromisoformat(row.get("TIMESTAMP", row.get("timestamp", ""))).date() for row in rows]
        return (min(dates), max(dates))


class ExternalIntradayProviderPlaceholder(IntradayDataProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    def fetch_bars(self, **_: Any) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.name} is a capability placeholder; no credentials or calls are enabled")

    def provider_metadata(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "PLACEHOLDER_ONLY", "network_calls": False}

    def supported_intervals(self) -> tuple[str, ...]:
        return ()

    def supported_history(self) -> tuple[date | None, date | None]:
        return (None, None)
