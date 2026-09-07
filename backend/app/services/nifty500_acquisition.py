from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import re
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as market_time, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.models.ingestion import DailyCandle, ImportSummary, ProviderReadResult
from app.providers.groww import GrowwAuthService, GrowwHistoricalProvider
from app.providers.groww.exceptions import (
    GrowwAuthenticationError,
    GrowwProviderError,
    GrowwProviderNotConfiguredError,
)
from app.providers.groww.historical import (
    GrowwHistoricalProviderConfig,
    INTERVAL_LIMIT_DAYS,
)
from app.services.data_quality import HistoricalDataValidator

NIFTY500_SOURCE_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
NIFTY500_REFERER = "https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-500"
NIFTY500_INDEX_NAME = "NIFTY 500"
PILOT_SYMBOLS = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "SUNPHARMA")
PRICE_ADJUSTMENT_STATUS = "UNKNOWN"

REFERENCE_FIELDS = [
    "trading_symbol",
    "company_name",
    "isin",
    "sector",
    "industry",
    "index_name",
    "source",
    "source_date",
    "active_current_member",
]

MAPPING_FIELDS = [
    "nse_symbol",
    "company_name",
    "isin",
    "groww_symbol",
    "exchange",
    "segment",
    "instrument_type",
    "mapping_status",
    "mapping_reason",
    "groww_name",
    "series",
]

DAILY_CANDLE_FIELDS = [
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "groww_symbol",
    "nse_symbol",
    "adjusted_close",
    "traded_value",
    "price_adjustment_status",
]

SUMMARY_FIELDS = [
    "nse_symbol",
    "company_name",
    "groww_symbol",
    "mapping_status",
    "fetch_status",
    "candle_count",
    "earliest_date",
    "latest_date",
    "invalid_rows",
    "duplicates",
    "missing_sessions_estimate",
    "zero_volume_count",
    "large_gap_warnings",
    "skipped_incomplete_rows",
    "current_close",
    "price_eligibility_class",
    "price_adjustment_status",
    "error_message",
    "output_file",
]


@dataclass(frozen=True, slots=True)
class ResearchPriceConfig:
    preferred_floor: Decimal = Decimal("100")
    preferred_ceiling: Decimal = Decimal("5000")
    hard_ceiling: Decimal = Decimal("7000")


@dataclass(frozen=True, slots=True)
class Nifty500Constituent:
    trading_symbol: str
    company_name: str
    isin: str
    sector: str
    industry: str
    index_name: str
    source: str
    source_date: str
    active_current_member: bool = True


@dataclass(frozen=True, slots=True)
class GrowwInstrumentMapping:
    nse_symbol: str
    company_name: str
    isin: str
    groww_symbol: str
    exchange: str
    segment: str
    instrument_type: str
    mapping_status: str
    mapping_reason: str
    groww_name: str = ""
    series: str = ""


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    output_dir: Path
    start_date: date
    end_date: date
    resume: bool = False
    dry_run: bool = False
    force_refresh: bool = False
    request_delay_seconds: float = 0.5
    max_retries: int = 2
    retry_base_seconds: float = 1.0
    timeout_seconds: int = 30
    price_config: ResearchPriceConfig = ResearchPriceConfig()
    price_adjustment_status: str = PRICE_ADJUSTMENT_STATUS

    @property
    def reference_dir(self) -> Path:
        return self.output_dir / "reference" / "nifty500"

    @property
    def historical_dir(self) -> Path:
        return self.output_dir / "historical" / "daily" / "groww"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"


@dataclass(slots=True)
class SymbolAcquisitionSummary:
    nse_symbol: str
    company_name: str
    isin: str
    groww_symbol: str
    mapping_status: str
    mapping_reason: str
    fetch_status: str
    candle_count: int = 0
    earliest_date: str = ""
    latest_date: str = ""
    invalid_rows: int = 0
    duplicates: int = 0
    missing_sessions_estimate: int = 0
    zero_volume_count: int = 0
    large_gap_warnings: int = 0
    skipped_incomplete_rows: int = 0
    current_close: str = ""
    price_eligibility_class: str = "UNKNOWN_PRICE"
    error_message: str = ""
    output_file: str = ""
    price_adjustment_status: str = PRICE_ADJUSTMENT_STATUS


def download_nifty500_source(
    *,
    url: str = NIFTY500_SOURCE_URL,
    timeout_seconds: int = 30,
) -> tuple[str, dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": NIFTY500_REFERER,
        "Accept": "text/csv,*/*",
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
        response_headers = dict(response.headers.items())

    downloaded_at = datetime.now(timezone.utc)
    source_date = source_date_from_headers(response_headers, fallback=downloaded_at.date())
    metadata = {
        "source_url": url,
        "source": "Nifty Indices official constituent CSV",
        "source_date": source_date.isoformat(),
        "downloaded_at": downloaded_at.isoformat(),
        "http_last_modified": response_headers.get("Last-Modified"),
        "http_content_type": response_headers.get("Content-Type"),
    }
    return raw_bytes.decode("utf-8-sig"), metadata


def source_date_from_headers(headers: dict[str, str], *, fallback: date) -> date:
    last_modified = headers.get("Last-Modified")
    if last_modified:
        try:
            return parsedate_to_datetime(last_modified).date()
        except (TypeError, ValueError, IndexError, OverflowError):
            pass
    return fallback


def normalize_nifty500_constituents(
    raw_csv: str,
    *,
    source_date: str,
    source_url: str = NIFTY500_SOURCE_URL,
) -> list[Nifty500Constituent]:
    reader = csv.DictReader(io.StringIO(raw_csv.lstrip("\ufeff")))
    required_columns = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    missing_columns = required_columns - set(reader.fieldnames or [])
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Nifty 500 source is missing required columns: {missing}")

    constituents: list[Nifty500Constituent] = []
    for row in reader:
        symbol = clean_value(row.get("Symbol")).upper()
        series = clean_value(row.get("Series")).upper()
        if not symbol:
            continue
        constituents.append(
            Nifty500Constituent(
                trading_symbol=symbol,
                company_name=clean_value(row.get("Company Name")),
                isin=clean_value(row.get("ISIN Code")).upper(),
                sector="",
                industry=clean_value(row.get("Industry")),
                index_name=NIFTY500_INDEX_NAME,
                source=source_url,
                source_date=source_date,
                active_current_member=series == "EQ",
            )
        )
    return constituents


def write_reference_files(
    *,
    raw_csv: str,
    constituents: Sequence[Nifty500Constituent],
    metadata: dict[str, Any],
    reference_dir: Path,
) -> None:
    reference_dir.mkdir(parents=True, exist_ok=True)
    raw_path = reference_dir / "nifty500_constituents_raw.csv"
    normalized_path = reference_dir / "nifty500_constituents_normalized.csv"
    metadata_path = reference_dir / "nifty500_source_metadata.json"

    raw_path.write_text(raw_csv, encoding="utf-8")
    write_csv(normalized_path, [asdict(row) for row in constituents], REFERENCE_FIELDS)
    metadata_with_count = {**metadata, "constituent_count": len(constituents)}
    metadata_path.write_text(
        json.dumps(json_safe(metadata_with_count), indent=2),
        encoding="utf-8",
    )


def map_constituents_to_groww(
    constituents: Sequence[Nifty500Constituent],
    instruments: Iterable[dict[str, Any]],
) -> list[GrowwInstrumentMapping]:
    normalized_instruments = [normalize_groww_instrument(row) for row in instruments]
    mappings: list[GrowwInstrumentMapping] = []

    for constituent in constituents:
        by_isin = [
            instrument
            for instrument in normalized_instruments
            if constituent.isin and instrument.get("isin") == constituent.isin
        ]
        if by_isin:
            mappings.append(resolve_candidates(constituent, by_isin, "isin_exact"))
            continue

        by_symbol = [
            instrument
            for instrument in normalized_instruments
            if instrument.get("exchange") == "NSE"
            and instrument.get("trading_symbol") == constituent.trading_symbol
        ]
        if by_symbol:
            mappings.append(resolve_candidates(constituent, by_symbol, "symbol_exact"))
            continue

        mappings.append(
            GrowwInstrumentMapping(
                nse_symbol=constituent.trading_symbol,
                company_name=constituent.company_name,
                isin=constituent.isin,
                groww_symbol="",
                exchange="NSE",
                segment="",
                instrument_type="",
                mapping_status="NOT_FOUND",
                mapping_reason="No Groww instrument matched by ISIN or exact NSE symbol.",
            )
        )

    return mappings


def resolve_candidates(
    constituent: Nifty500Constituent,
    candidates: Sequence[dict[str, str]],
    reason: str,
) -> GrowwInstrumentMapping:
    exchange_candidates = [row for row in candidates if row.get("exchange") == "NSE"]
    candidates = exchange_candidates or list(candidates)
    cash_equity = [row for row in candidates if is_cash_equity(row)]
    if not cash_equity:
        return mapping_from_candidate(
            constituent,
            candidates[0],
            status="NON_CASH_EQUITY",
            reason=f"{reason}; instrument exists but is not NSE CASH EQ.",
        )

    active = [row for row in cash_equity if is_active_instrument(row)]
    if not active:
        return mapping_from_candidate(
            constituent,
            cash_equity[0],
            status="INACTIVE",
            reason=f"{reason}; instrument is not marked active for trading.",
        )

    exact_symbol = [
        row for row in active if row.get("trading_symbol") == constituent.trading_symbol
    ]
    selection = exact_symbol or active
    if len(selection) == 1:
        return mapping_from_candidate(
            constituent,
            selection[0],
            status="MATCHED",
            reason=reason if exact_symbol else f"{reason}; symbol differs but ISIN matched.",
        )

    return mapping_from_candidate(
        constituent,
        selection[0],
        status="AMBIGUOUS",
        reason=f"{reason}; multiple active NSE CASH EQ instruments matched.",
    )


def mapping_from_candidate(
    constituent: Nifty500Constituent,
    candidate: dict[str, str],
    *,
    status: str,
    reason: str,
) -> GrowwInstrumentMapping:
    return GrowwInstrumentMapping(
        nse_symbol=constituent.trading_symbol,
        company_name=constituent.company_name,
        isin=constituent.isin,
        groww_symbol=candidate.get("groww_symbol", ""),
        exchange=candidate.get("exchange", ""),
        segment=candidate.get("segment", ""),
        instrument_type=candidate.get("instrument_type", ""),
        mapping_status=status,
        mapping_reason=reason,
        groww_name=candidate.get("name", ""),
        series=candidate.get("series", ""),
    )


def normalize_groww_instrument(row: dict[str, Any]) -> dict[str, str]:
    return {
        "exchange": clean_value(row.get("exchange")).upper(),
        "trading_symbol": clean_value(row.get("trading_symbol")).upper(),
        "groww_symbol": clean_value(row.get("groww_symbol")).upper(),
        "name": clean_value(row.get("name")),
        "instrument_type": clean_value(row.get("instrument_type")).upper(),
        "segment": clean_value(row.get("segment")).upper(),
        "series": clean_value(row.get("series")).upper(),
        "isin": clean_value(row.get("isin")).upper(),
        "buy_allowed": clean_value(row.get("buy_allowed")),
        "sell_allowed": clean_value(row.get("sell_allowed")),
        "is_reserved": clean_value(row.get("is_reserved")),
    }


def is_cash_equity(row: dict[str, str]) -> bool:
    return (
        row.get("exchange") == "NSE"
        and row.get("segment") == "CASH"
        and row.get("instrument_type") == "EQ"
        and row.get("series") in {"", "EQ"}
    )


def is_active_instrument(row: dict[str, str]) -> bool:
    is_reserved = row.get("is_reserved", "").lower() in {"1", "true", "yes"}
    if is_reserved:
        return False

    buy_allowed = row.get("buy_allowed")
    sell_allowed = row.get("sell_allowed")
    if buy_allowed == "0" and sell_allowed == "0":
        return False
    return True


async def acquire_daily_history(
    mappings: Sequence[GrowwInstrumentMapping],
    *,
    config: AcquisitionConfig,
    auth_service: GrowwAuthService,
    progress: Callable[[str], None] | None = None,
    provider_factory: Callable[[GrowwInstrumentMapping], Any] | None = None,
) -> list[SymbolAcquisitionSummary]:
    config.historical_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[SymbolAcquisitionSummary] = []

    for index, mapping in enumerate(mappings, start=1):
        if progress:
            progress(f"[{index}/{len(mappings)}] {mapping.nse_symbol}")
        summary = await acquire_symbol_daily_history(
            mapping,
            config=config,
            auth_service=auth_service,
            provider_factory=provider_factory,
        )
        summaries.append(summary)
        write_progress_file(config.reports_dir, summaries)

    return summaries


async def acquire_symbol_daily_history(
    mapping: GrowwInstrumentMapping,
    *,
    config: AcquisitionConfig,
    auth_service: GrowwAuthService,
    provider_factory: Callable[[GrowwInstrumentMapping], Any] | None = None,
) -> SymbolAcquisitionSummary:
    output_path = symbol_daily_path(config.historical_dir, mapping.nse_symbol)
    if mapping.mapping_status != "MATCHED":
        return unmapped_summary(mapping, config, output_path)

    if config.resume and output_path.exists() and not config.force_refresh:
        records = read_daily_csv(output_path, mapping=mapping)
        return summarize_records(
            mapping,
            records,
            config=config,
            output_path=output_path,
        )

    if config.dry_run:
        return SymbolAcquisitionSummary(
            nse_symbol=mapping.nse_symbol,
            company_name=mapping.company_name,
            isin=mapping.isin,
            groww_symbol=mapping.groww_symbol,
            mapping_status=mapping.mapping_status,
            mapping_reason=mapping.mapping_reason,
            fetch_status="DRY_RUN",
            output_file=str(output_path),
            price_adjustment_status=config.price_adjustment_status,
        )

    records: list[DailyCandle] = []
    invalid_rows = 0
    skipped_incomplete = 0
    error_messages: list[str] = []
    validator = HistoricalDataValidator()

    for chunk_start, chunk_end in chunk_date_range(
        config.start_date,
        config.end_date,
        max_days=INTERVAL_LIMIT_DAYS["1d"],
    ):
        chunk_result: ProviderReadResult[DailyCandle] | None = None
        for attempt in range(config.max_retries + 1):
            try:
                provider = (
                    provider_factory(mapping)
                    if provider_factory
                    else groww_provider_for_mapping(mapping, config, auth_service)
                )
                chunk_result = await provider.get_daily_candles(
                    start=chunk_start,
                    end=chunk_end,
                )
                break
            except (GrowwProviderNotConfiguredError, GrowwAuthenticationError):
                raise
            except Exception as exc:
                if attempt >= config.max_retries:
                    error_messages.append(
                        f"{chunk_start.isoformat()}->{chunk_end.isoformat()}: {exc.__class__.__name__}"
                    )
                    break
                await asyncio.sleep(config.retry_base_seconds * (2 ** attempt))

        if chunk_result is not None:
            validation = validator.validate_daily_candles(chunk_result.records)
            records.extend(validation.valid_records)
            invalid_rows += len(chunk_result.errors) + validation.invalid_count
            skipped_incomplete += int(chunk_result.metadata.get("skipped_incomplete_rows", 0))

        if config.request_delay_seconds > 0:
            await asyncio.sleep(config.request_delay_seconds)

    merged_records, duplicates = merge_daily_records(records)
    if merged_records:
        write_daily_csv(
            output_path,
            merged_records,
            mapping=mapping,
            price_adjustment_status=config.price_adjustment_status,
        )

    summary = summarize_records(
        mapping,
        merged_records,
        config=config,
        output_path=output_path,
        invalid_rows=invalid_rows,
        duplicates=duplicates,
        skipped_incomplete_rows=skipped_incomplete,
        error_message="; ".join(error_messages),
    )
    if error_messages and summary.fetch_status == "COMPLETE":
        summary.fetch_status = "PARTIAL"
    return summary


def groww_provider_for_mapping(
    mapping: GrowwInstrumentMapping,
    config: AcquisitionConfig,
    auth_service: GrowwAuthService,
) -> GrowwHistoricalProvider:
    return GrowwHistoricalProvider(
        GrowwHistoricalProviderConfig(
            exchange=mapping.exchange or "NSE",
            segment=mapping.segment or "CASH",
            trading_symbol=mapping.nse_symbol,
            groww_symbol=mapping.groww_symbol,
            company_name=mapping.company_name,
            instrument_type=mapping.instrument_type or "EQ",
            timeout_seconds=config.timeout_seconds,
        ),
        auth_service=auth_service,
    )


def summarize_records(
    mapping: GrowwInstrumentMapping,
    records: Sequence[DailyCandle],
    *,
    config: AcquisitionConfig,
    output_path: Path,
    invalid_rows: int = 0,
    duplicates: int = 0,
    skipped_incomplete_rows: int = 0,
    error_message: str = "",
) -> SymbolAcquisitionSummary:
    sorted_records = sorted(records, key=lambda record: record.trading_date)
    earliest_date = sorted_records[0].trading_date if sorted_records else None
    latest_date = sorted_records[-1].trading_date if sorted_records else None
    current_close = sorted_records[-1].close if sorted_records else None
    missing_sessions = (
        max(0, estimate_weekday_sessions(earliest_date, latest_date) - len(sorted_records))
        if earliest_date and latest_date
        else 0
    )
    large_gaps = count_large_daily_gaps(sorted_records)
    fetch_status = fetch_status_for_records(
        sorted_records,
        config=config,
        invalid_rows=invalid_rows,
        skipped_incomplete_rows=skipped_incomplete_rows,
        missing_sessions_estimate=missing_sessions,
        large_gap_warnings=large_gaps,
        error_message=error_message,
    )

    return SymbolAcquisitionSummary(
        nse_symbol=mapping.nse_symbol,
        company_name=mapping.company_name,
        isin=mapping.isin,
        groww_symbol=mapping.groww_symbol,
        mapping_status=mapping.mapping_status,
        mapping_reason=mapping.mapping_reason,
        fetch_status=fetch_status,
        candle_count=len(sorted_records),
        earliest_date=earliest_date.isoformat() if earliest_date else "",
        latest_date=latest_date.isoformat() if latest_date else "",
        invalid_rows=invalid_rows,
        duplicates=duplicates,
        missing_sessions_estimate=missing_sessions,
        zero_volume_count=sum(1 for record in sorted_records if record.volume == 0),
        large_gap_warnings=large_gaps,
        skipped_incomplete_rows=skipped_incomplete_rows,
        current_close=str(current_close) if current_close is not None else "",
        price_eligibility_class=classify_price(current_close, config.price_config),
        error_message=error_message,
        output_file=str(output_path) if sorted_records else "",
        price_adjustment_status=config.price_adjustment_status,
    )


def fetch_status_for_records(
    records: Sequence[DailyCandle],
    *,
    config: AcquisitionConfig,
    invalid_rows: int,
    skipped_incomplete_rows: int,
    missing_sessions_estimate: int,
    large_gap_warnings: int,
    error_message: str,
) -> str:
    if not records:
        return "FAILED"
    if invalid_rows > 0 or error_message:
        return "PARTIAL"
    if skipped_incomplete_rows > 5:
        return "PARTIAL"
    if large_gap_warnings > 0:
        return "PARTIAL"
    if missing_sessions_estimate > 120:
        return "PARTIAL"

    earliest = records[0].trading_date
    latest = records[-1].trading_date
    if earliest > config.start_date + timedelta(days=14):
        return "PARTIAL"
    if latest < config.end_date - timedelta(days=7):
        return "PARTIAL"
    return "COMPLETE"


def unmapped_summary(
    mapping: GrowwInstrumentMapping,
    config: AcquisitionConfig,
    output_path: Path,
) -> SymbolAcquisitionSummary:
    return SymbolAcquisitionSummary(
        nse_symbol=mapping.nse_symbol,
        company_name=mapping.company_name,
        isin=mapping.isin,
        groww_symbol=mapping.groww_symbol,
        mapping_status=mapping.mapping_status,
        mapping_reason=mapping.mapping_reason,
        fetch_status="UNMAPPED",
        error_message=mapping.mapping_reason,
        output_file=str(output_path),
        price_adjustment_status=config.price_adjustment_status,
    )


def chunk_date_range(start: date, end: date, *, max_days: int) -> list[tuple[date, date]]:
    if start > end:
        raise ValueError("start date must be on or before end date")

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def merge_daily_records(records: Iterable[DailyCandle]) -> tuple[list[DailyCandle], int]:
    by_date: dict[date, DailyCandle] = {}
    duplicate_count = 0
    for record in sorted(records, key=lambda value: value.trading_date):
        if record.trading_date in by_date:
            duplicate_count += 1
        by_date[record.trading_date] = record
    return [by_date[key] for key in sorted(by_date)], duplicate_count


def estimate_weekday_sessions(start: date, end: date) -> int:
    if start > end:
        return 0
    total = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            total += 1
        cursor += timedelta(days=1)
    return total


def count_large_daily_gaps(records: Sequence[DailyCandle], *, gap_days: int = 7) -> int:
    count = 0
    sorted_records = sorted(records, key=lambda record: record.trading_date)
    for previous, current in zip(sorted_records, sorted_records[1:]):
        if current.trading_date - previous.trading_date > timedelta(days=gap_days):
            count += 1
    return count


def classify_price(
    close: Decimal | None,
    price_config: ResearchPriceConfig | None = None,
) -> str:
    if close is None:
        return "UNKNOWN_PRICE"

    config = price_config or ResearchPriceConfig()
    if close < config.preferred_floor:
        return "BELOW_PRICE_FLOOR"
    if close <= config.preferred_ceiling:
        return "ELIGIBLE_PRICE"
    if close <= config.hard_ceiling:
        return "ABOVE_PREFERRED_RANGE"
    return "ABOVE_HARD_LIMIT"


def write_daily_csv(
    path: Path,
    records: Sequence[DailyCandle],
    *,
    mapping: GrowwInstrumentMapping,
    price_adjustment_status: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in sorted(records, key=lambda value: value.trading_date):
        rows.append(
            {
                "trading_date": record.trading_date.isoformat(),
                "open": str(record.open),
                "high": str(record.high),
                "low": str(record.low),
                "close": str(record.close),
                "volume": record.volume,
                "source": record.source,
                "groww_symbol": mapping.groww_symbol,
                "nse_symbol": mapping.nse_symbol,
                "adjusted_close": str(record.adjusted_close) if record.adjusted_close else "",
                "traded_value": str(record.traded_value) if record.traded_value else "",
                "price_adjustment_status": price_adjustment_status,
            }
        )
    write_csv(path, rows, DAILY_CANDLE_FIELDS)


def read_daily_csv(path: Path, *, mapping: GrowwInstrumentMapping) -> list[DailyCandle]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return [
            DailyCandle(
                exchange=mapping.exchange or "NSE",
                trading_symbol=mapping.nse_symbol,
                trading_date=date.fromisoformat(row["trading_date"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]),
                adjusted_close=Decimal(row["adjusted_close"]) if row.get("adjusted_close") else None,
                traded_value=Decimal(row["traded_value"]) if row.get("traded_value") else None,
                source=row.get("source") or "groww",
            )
            for row in reader
        ]


def write_mapping_csv(path: Path, mappings: Sequence[GrowwInstrumentMapping]) -> None:
    write_csv(path, [asdict(mapping) for mapping in mappings], MAPPING_FIELDS)


def write_reports(
    *,
    summaries: Sequence[SymbolAcquisitionSummary],
    mappings: Sequence[GrowwInstrumentMapping],
    constituents: Sequence[Nifty500Constituent],
    config: AcquisitionConfig,
    source_metadata: dict[str, Any],
    full_acquisition_run: bool,
    pilot_symbols: Sequence[str],
    markdown_path: Path,
) -> dict[str, Any]:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = [asdict(summary) for summary in summaries]
    csv_path = config.reports_dir / "nifty500_daily_acquisition_summary.csv"
    json_path = config.reports_dir / "nifty500_daily_acquisition_summary.json"
    write_csv(csv_path, summary_rows, SUMMARY_FIELDS)

    report = build_report_payload(
        summaries=summaries,
        mappings=mappings,
        constituents=constituents,
        config=config,
        source_metadata=source_metadata,
        full_acquisition_run=full_acquisition_run,
        pilot_symbols=pilot_symbols,
        csv_path=csv_path,
        json_path=json_path,
    )
    json_path.write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_markdown_report(report), encoding="utf-8")
    return report


def build_report_payload(
    *,
    summaries: Sequence[SymbolAcquisitionSummary],
    mappings: Sequence[GrowwInstrumentMapping],
    constituents: Sequence[Nifty500Constituent],
    config: AcquisitionConfig,
    source_metadata: dict[str, Any],
    full_acquisition_run: bool,
    pilot_symbols: Sequence[str],
    csv_path: Path,
    json_path: Path,
) -> dict[str, Any]:
    mapping_counts = Counter(mapping.mapping_status for mapping in mappings)
    fetch_counts = Counter(summary.fetch_status for summary in summaries)
    earliest_dates = [summary.earliest_date for summary in summaries if summary.earliest_date]
    latest_dates = [summary.latest_date for summary in summaries if summary.latest_date]
    total_candles = sum(summary.candle_count for summary in summaries)

    return {
        "phase": "Step 02.3C",
        "task": "Nifty 500 daily data acquisition",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_metadata,
        "constituent_count": len(constituents),
        "mapping_counts": dict(mapping_counts),
        "fetch_counts": dict(fetch_counts),
        "full_acquisition_run": full_acquisition_run,
        "pilot_symbols": list(pilot_symbols),
        "target_date_range": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "overall_coverage": {
            "earliest_date": min(earliest_dates) if earliest_dates else "",
            "latest_date": max(latest_dates) if latest_dates else "",
            "total_daily_candles": total_candles,
        },
        "storage": {
            "format": "CSV",
            "historical_path": str(config.historical_dir),
            "summary_csv": str(csv_path),
            "summary_json": str(json_path),
            "mapping_csv": str(config.reference_dir / "nifty500_groww_mapping.csv"),
        },
        "corporate_actions": {
            "price_adjustment_status": config.price_adjustment_status,
            "note": "Groww adjustment behavior is not confirmed here; prices are not altered.",
        },
        "safety": {
            "read_only": True,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
        },
        "summaries": [asdict(summary) for summary in summaries],
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    mapping_counts = report["mapping_counts"]
    fetch_counts = report["fetch_counts"]
    source = report["source"]
    target = report["target_date_range"]
    coverage = report["overall_coverage"]
    storage = report["storage"]
    summaries = report["summaries"]
    total_invalid_rows = sum(int(row.get("invalid_rows") or 0) for row in summaries)
    total_duplicates = sum(int(row.get("duplicates") or 0) for row in summaries)
    total_missing_sessions = sum(int(row.get("missing_sessions_estimate") or 0) for row in summaries)
    total_zero_volume = sum(int(row.get("zero_volume_count") or 0) for row in summaries)
    total_large_gaps = sum(int(row.get("large_gap_warnings") or 0) for row in summaries)
    total_skipped_incomplete = sum(int(row.get("skipped_incomplete_rows") or 0) for row in summaries)

    return "\n".join(
        [
            "# Nifty 500 Daily Data Acquisition",
            "",
            "Current phase: Step 02.3C - Nifty 500 Universe Acquisition & Historical Dataset Download",
            "",
            "## Source",
            "",
            f"- Universe source: {source.get('source')}",
            f"- Source URL: {source.get('source_url')}",
            f"- Source date: {source.get('source_date')}",
            f"- Constituent count: {report['constituent_count']}",
            "",
            "## Groww Mapping",
            "",
            f"- Matched: {mapping_counts.get('MATCHED', 0)}",
            f"- Ambiguous: {mapping_counts.get('AMBIGUOUS', 0)}",
            f"- Not found: {mapping_counts.get('NOT_FOUND', 0)}",
            f"- Inactive: {mapping_counts.get('INACTIVE', 0)}",
            f"- Non-cash equity: {mapping_counts.get('NON_CASH_EQUITY', 0)}",
            "",
            "## Acquisition Scope",
            "",
            f"- Pilot symbols: {', '.join(report['pilot_symbols'])}",
            f"- Full Nifty 500 acquisition run: {report['full_acquisition_run']}",
            f"- Target start date: {target.get('start_date')}",
            f"- Target end date: {target.get('end_date')}",
            f"- Overall earliest date received: {coverage.get('earliest_date')}",
            f"- Overall latest date received: {coverage.get('latest_date')}",
            f"- Total daily candles downloaded: {coverage.get('total_daily_candles')}",
            "",
            "## Fetch Results",
            "",
            f"- COMPLETE: {fetch_counts.get('COMPLETE', 0)}",
            f"- PARTIAL: {fetch_counts.get('PARTIAL', 0)}",
            f"- FAILED: {fetch_counts.get('FAILED', 0)}",
            f"- UNMAPPED: {fetch_counts.get('UNMAPPED', 0)}",
            f"- DRY_RUN: {fetch_counts.get('DRY_RUN', 0)}",
            "",
            "## Storage",
            "",
            f"- Format: {storage.get('format')}",
            f"- Historical path: {storage.get('historical_path')}",
            f"- Summary CSV: {storage.get('summary_csv')}",
            f"- Summary JSON: {storage.get('summary_json')}",
            f"- Mapping CSV: {storage.get('mapping_csv')}",
            "",
            "## Data Quality",
            "",
            "- OHLCV records are normalized into InterSignal `DailyCandle` models.",
            "- Duplicate dates are merged per symbol after chunked requests.",
            "- Missing sessions are estimated from weekdays only; exchange holidays are not subtracted yet.",
            "- Rows with incomplete required OHLCV fields are skipped and counted.",
            f"- Invalid rows: {total_invalid_rows}",
            f"- Duplicate rows merged: {total_duplicates}",
            f"- Missing sessions estimate: {total_missing_sessions}",
            f"- Zero-volume rows: {total_zero_volume}",
            f"- Large-gap warnings: {total_large_gaps}",
            f"- Incomplete Groww rows skipped: {total_skipped_incomplete}",
            "",
            "## Corporate Actions",
            "",
            f"- Price adjustment status: {report['corporate_actions']['price_adjustment_status']}",
            "- No price adjustments were fabricated or applied.",
            "",
            "## Rate Limiting And Resume",
            "",
            "- Daily Groww requests are chunked into documented 180-day windows.",
            "- Requests use configurable delay, retries, and exponential backoff.",
            "- Resume mode reuses existing per-symbol CSV files.",
            "",
            "## Safety",
            "",
            "- ZERO order endpoints were called.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- Credentials remain local to ignored `backend/.env`.",
            "",
        ]
    )


def write_progress_file(
    reports_dir: Path,
    summaries: Sequence[SymbolAcquisitionSummary],
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    progress_path = reports_dir / "nifty500_daily_acquisition_progress.json"
    progress_path.write_text(
        json.dumps(json_safe([asdict(summary) for summary in summaries]), indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def symbol_daily_path(historical_dir: Path, symbol: str) -> Path:
    return historical_dir / f"{safe_filename(symbol)}.csv"


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Z0-9._-]+", "_", value.upper()).strip("_")


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def select_mappings(
    mappings: Sequence[GrowwInstrumentMapping],
    *,
    symbols: Sequence[str] | None = None,
    max_symbols: int | None = None,
) -> list[GrowwInstrumentMapping]:
    if symbols:
        wanted = {symbol.strip().upper() for symbol in symbols}
        selected = [mapping for mapping in mappings if mapping.nse_symbol in wanted]
        return order_by_symbols(selected, symbols)

    selected = list(mappings)
    if max_symbols is not None:
        selected = selected[:max_symbols]
    return selected


def select_pilot_mappings(
    mappings: Sequence[GrowwInstrumentMapping],
    pilot_symbols: Sequence[str] = PILOT_SYMBOLS,
) -> list[GrowwInstrumentMapping]:
    return select_mappings(mappings, symbols=pilot_symbols)


def order_by_symbols(
    mappings: Sequence[GrowwInstrumentMapping],
    symbols: Sequence[str],
) -> list[GrowwInstrumentMapping]:
    by_symbol = {mapping.nse_symbol: mapping for mapping in mappings}
    return [by_symbol[symbol.strip().upper()] for symbol in symbols if symbol.strip().upper() in by_symbol]


def default_start_date(today: date | None = None) -> date:
    value = today or date.today()
    try:
        return value.replace(year=value.year - 5)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year - 5)


def latest_safe_end_date(today: date | None = None) -> date:
    value = today or date.today()
    if value.weekday() >= 5:
        while value.weekday() >= 5:
            value -= timedelta(days=1)
        return value
    return value


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value
