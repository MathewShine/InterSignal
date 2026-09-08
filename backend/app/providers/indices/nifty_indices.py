from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.providers.indices.base import IndexDailyRecord, IndexDefinition, canonical_index_id


class NSEOfficialIndexHistoryProvider:
    name = "NSE_OFFICIAL_INDEX_HISTORY"
    base_url = "https://www.nseindia.com"
    index_history_endpoint = "https://www.nseindia.com/api/historicalOR/indicesHistory"
    index_inventory_endpoint = "https://www.nseindia.com/api/allIndices"
    source_reference = "https://www.nseindia.com/reports-indices-historical-index-data"
    inventory_source_reference = "https://www.nseindia.com/market-data/live-equity-market-indices"

    def __init__(
        self,
        *,
        raw_dir: str | Path,
        timeout_seconds: int = 60,
        request_delay_seconds: float = 0.12,
        force_refresh: bool = False,
        chunk_days: int = 89,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.force_refresh = force_refresh
        self.chunk_days = chunk_days
        self._client: httpx.Client | None = None
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def discover_index_definitions(self) -> list[IndexDefinition]:
        payload, raw_path = self._get_json(
            self.index_inventory_endpoint,
            self.raw_dir / "index_inventory_all_indices.json",
            cache_key="all_indices",
        )
        definitions: list[IndexDefinition] = []
        for row in payload.get("data", []):
            index_name = clean_text(row.get("index"))
            category = clean_text(row.get("key"))
            if not index_name:
                continue
            definitions.append(
                IndexDefinition(
                    index_id=canonical_index_id(index_name),
                    index_name=index_name,
                    category=category,
                    source_reference=f"{self.inventory_source_reference}#{raw_path.name}",
                )
            )
        return definitions

    def fetch_index_history(
        self,
        *,
        definition: IndexDefinition,
        start_date: date,
        end_date: date,
    ) -> list[IndexDailyRecord]:
        records_by_date: dict[date, IndexDailyRecord] = {}
        for window_start, window_end in date_windows(start_date, end_date, self.chunk_days):
            raw_path = self._history_raw_path(definition.index_id, window_start, window_end)
            had_cache = raw_path.exists() and not self.force_refresh
            payload, stored_raw_path = self._get_json(
                self.index_history_endpoint,
                raw_path,
                cache_key=f"{definition.index_id}:{window_start}:{window_end}",
                params={
                    "indexType": definition.index_name,
                    "from": window_start.strftime("%d-%m-%Y"),
                    "to": window_end.strftime("%d-%m-%Y"),
                },
            )
            for row in payload.get("data", []):
                record = parse_index_history_row(
                    row,
                    index_id=definition.index_id,
                    expected_index_name=definition.index_name,
                    source_reference=f"{self.source_reference}#{stored_raw_path.name}",
                    raw_source_file=str(stored_raw_path),
                )
                if record is None:
                    continue
                if start_date <= record.trading_date <= end_date:
                    records_by_date[record.trading_date] = record
            if self.request_delay_seconds > 0 and not had_cache:
                time.sleep(self.request_delay_seconds)
        return [records_by_date[key] for key in sorted(records_by_date)]

    def _get_json(
        self,
        url: str,
        raw_path: Path,
        *,
        cache_key: str,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], Path]:
        if raw_path.exists() and not self.force_refresh:
            return json.loads(raw_path.read_text(encoding="utf-8")), raw_path

        response = self.client.get(url, params=params)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise ValueError(f"NSE returned non-JSON content for {cache_key}: {content_type}")
        payload = response.json()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload, raw_path

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0 Safari/537.36"
                    ),
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": self.source_reference,
                },
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            self._client.get(self.base_url)
            self._client.get(self.source_reference)
        return self._client

    def _history_raw_path(self, index_id: str, start_date: date, end_date: date) -> Path:
        return self.raw_dir / "history" / index_id / f"{index_id}_{start_date.isoformat()}_{end_date.isoformat()}.json"


def parse_index_history_row(
    row: dict[str, Any],
    *,
    index_id: str,
    expected_index_name: str,
    source_reference: str,
    raw_source_file: str = "",
) -> IndexDailyRecord | None:
    trading_date = parse_nse_date(clean_text(row.get("EOD_TIMESTAMP")))
    close_value = parse_decimal(row.get("EOD_CLOSE_INDEX_VAL"))
    if trading_date is None or close_value is None or close_value <= 0:
        return None
    index_name = clean_text(row.get("EOD_INDEX_NAME")) or expected_index_name
    source_date = parse_source_date(row.get("HI_TIMESTAMP")) or trading_date
    return IndexDailyRecord(
        trading_date=trading_date,
        index_id=index_id,
        index_name=index_name,
        open=parse_decimal(row.get("EOD_OPEN_INDEX_VAL")),
        high=parse_decimal(row.get("EOD_HIGH_INDEX_VAL")),
        low=parse_decimal(row.get("EOD_LOW_INDEX_VAL")),
        close=close_value,
        source="NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY",
        source_reference=source_reference,
        source_date=source_date,
        raw_source_file=raw_source_file,
    )


def date_windows(start_date: date, end_date: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=chunk_days), end_date)
        yield current, window_end
        current = window_end + timedelta(days=1)


def parse_nse_date(value: str) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.title(), fmt).date()
        except ValueError:
            continue
    return None


def parse_source_date(value: object) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_decimal(value: object) -> Decimal | None:
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def clean_text(value: object) -> str:
    return str(value or "").strip()
