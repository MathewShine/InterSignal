from __future__ import annotations

import csv
import json
import shutil
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.providers.nse.daily_reference import (
    NSEDailyReferenceProvider,
    NSEDailyRecord,
    dates_in_range,
    parse_nse_daily_reference_file,
)

OFFICIAL_NSE_SOURCE = "official_nse_daily_bhavcopy"
PRICE_ADJUSTMENT_STATUS = "RAW"
NORMAL_EQUITY_SERIES = {"EQ"}
CORPORATE_ACTION_SUSPECT_THRESHOLD = Decimal("0.35")

CANONICAL_DAILY_FIELDS = [
    "trading_date",
    "exchange",
    "trading_symbol",
    "series",
    "isin",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "traded_value",
    "source",
    "source_file",
    "source_format",
    "series_classification",
    "price_adjustment_status",
    "quality_flags",
    "normalized_at",
]

CALENDAR_FIELDS = [
    "trading_date",
    "session_type",
    "source_reference",
    "source_available",
    "notes",
]

SESSION_SUMMARY_FIELDS = [
    "trading_date",
    "status",
    "source_available",
    "source_file",
    "source_format",
    "normalized_records",
    "eq_records",
    "special_series_records",
    "invalid_records",
    "duplicate_records",
    "zero_volume_records",
    "corporate_action_suspects",
    "notes",
]

DATASET_SUMMARY_FIELDS = [
    "phase",
    "run_mode",
    "target_start_date",
    "target_end_date",
    "actual_first_trading_session",
    "actual_last_trading_session",
    "calendar_dates_checked",
    "total_trading_sessions_expected",
    "sessions_downloaded",
    "sessions_missing",
    "sessions_failed",
    "non_session_dates",
    "total_normalized_records",
    "eq_records",
    "special_series_records",
    "invalid_records",
    "duplicate_records",
    "zero_volume_records",
    "corporate_action_suspect_count",
    "raw_storage_size_bytes",
    "normalized_storage_size_bytes",
    "raw_path",
    "normalized_path",
    "calendar_path",
    "generated_at",
]


@dataclass(frozen=True, slots=True)
class NSEDailyAcquisitionConfig:
    output_dir: Path
    start_date: date
    end_date: date
    run_mode: str = "PILOT"
    resume: bool = True
    force_refresh: bool = False
    request_delay_seconds: float = 0.2
    max_retries: int = 2
    retry_base_seconds: float = 1.0
    timeout_seconds: int = 30
    max_sessions: int | None = None
    source_cache_dir: Path | None = None
    corporate_action_suspect_threshold: Decimal = CORPORATE_ACTION_SUSPECT_THRESHOLD

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw" / "nse" / "daily"

    @property
    def normalized_dir(self) -> Path:
        return self.output_dir / "historical" / "daily" / "nse"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def calendar_dir(self) -> Path:
        return self.output_dir / "reference" / "nse" / "calendar"

    @property
    def calendar_path(self) -> Path:
        return self.calendar_dir / "nse_cash_trading_calendar.csv"


@dataclass(frozen=True, slots=True)
class NSEArchiveCandidate:
    source_format: str
    url: str
    filename: str


@dataclass(frozen=True, slots=True)
class NSEArchiveFetchResult:
    trading_date: date
    status: str
    path: Path | None = None
    source_format: str = ""
    source_url: str = ""
    error: str = ""

    @property
    def source_available(self) -> bool:
        return self.path is not None and self.status in {"CACHED", "DOWNLOADED", "IMPORTED_CACHE"}


@dataclass(slots=True)
class NSECanonicalDailyRecord:
    trading_date: date
    exchange: str
    trading_symbol: str
    series: str
    isin: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    traded_value: Decimal | None
    source: str
    source_file: str
    source_format: str
    series_classification: str
    price_adjustment_status: str = PRICE_ADJUSTMENT_STATUS
    quality_flags: str = ""
    normalized_at: str = ""

    @property
    def dedupe_key(self) -> tuple[str, str, date]:
        return (self.trading_symbol, self.series, self.trading_date)


@dataclass(slots=True)
class NSEDailySessionSummary:
    trading_date: str
    status: str
    source_available: bool
    source_file: str = ""
    source_format: str = ""
    normalized_records: int = 0
    eq_records: int = 0
    special_series_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0
    zero_volume_records: int = 0
    corporate_action_suspects: int = 0
    notes: str = ""


@dataclass(slots=True)
class NSECalendarRow:
    trading_date: str
    session_type: str
    source_reference: str
    source_available: bool
    notes: str = ""


class NSEDailyArchiveClient:
    def __init__(self, config: NSEDailyAcquisitionConfig) -> None:
        self.config = config

    def get_or_download(self, trading_date: date) -> NSEArchiveFetchResult:
        missing_marker = self._missing_marker(trading_date)
        if missing_marker.exists() and not self.config.force_refresh:
            return NSEArchiveFetchResult(trading_date=trading_date, status="MISSING")

        for candidate in nse_archive_candidates(trading_date):
            destination = self._destination_path(trading_date, candidate.filename)
            if destination.exists() and not self.config.force_refresh:
                return NSEArchiveFetchResult(
                    trading_date=trading_date,
                    status="CACHED",
                    path=destination,
                    source_format=candidate.source_format,
                    source_url=candidate.url,
                )

        imported = self._import_from_source_cache(trading_date)
        if imported is not None and not self.config.force_refresh:
            return imported

        saw_non_404_error = False
        last_error = ""
        for candidate in nse_archive_candidates(trading_date):
            destination = self._destination_path(trading_date, candidate.filename)
            for attempt in range(self.config.max_retries + 1):
                try:
                    content = self._download(candidate.url)
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        last_error = f"HTTP 404 for {candidate.source_format}"
                        break
                    saw_non_404_error = True
                    last_error = f"HTTP {exc.code} for {candidate.source_format}"
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    saw_non_404_error = True
                    last_error = exc.__class__.__name__
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    self._sleep()
                    return NSEArchiveFetchResult(
                        trading_date=trading_date,
                        status="DOWNLOADED",
                        path=destination,
                        source_format=candidate.source_format,
                        source_url=candidate.url,
                    )

                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_base_seconds * (2**attempt))

        self._sleep()
        if saw_non_404_error:
            return NSEArchiveFetchResult(
                trading_date=trading_date,
                status="FAILED",
                error=last_error or "NSE archive fetch failed",
            )

        missing_marker.parent.mkdir(parents=True, exist_ok=True)
        missing_marker.write_text("missing", encoding="utf-8")
        return NSEArchiveFetchResult(
            trading_date=trading_date,
            status="MISSING",
            error=last_error or "No official daily file found",
        )

    def _download(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/csv,application/zip,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return response.read()

    def _import_from_source_cache(self, trading_date: date) -> NSEArchiveFetchResult | None:
        source_cache_dir = self.config.source_cache_dir
        if source_cache_dir is None:
            return None

        source_missing_marker = source_cache_dir / f"{trading_date.isoformat()}.missing"
        if source_missing_marker.exists():
            self._missing_marker(trading_date).parent.mkdir(parents=True, exist_ok=True)
            self._missing_marker(trading_date).write_text("missing", encoding="utf-8")
            return NSEArchiveFetchResult(trading_date=trading_date, status="MISSING")

        for candidate in nse_archive_candidates(trading_date):
            source_path = source_cache_dir / candidate.filename
            if source_path.exists():
                destination = self._destination_path(trading_date, candidate.filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, destination)
                return NSEArchiveFetchResult(
                    trading_date=trading_date,
                    status="IMPORTED_CACHE",
                    path=destination,
                    source_format=candidate.source_format,
                    source_url=candidate.url,
                )
        return None

    def _destination_path(self, trading_date: date, filename: str) -> Path:
        return self.config.raw_dir / f"{trading_date:%Y}" / f"{trading_date:%m}" / filename

    def _missing_marker(self, trading_date: date) -> Path:
        return self.config.raw_dir / f"{trading_date:%Y}" / f"{trading_date:%m}" / f"{trading_date.isoformat()}.missing"

    def _sleep(self) -> None:
        if self.config.request_delay_seconds > 0:
            time.sleep(self.config.request_delay_seconds)


def acquire_nse_daily_dataset(
    *,
    config: NSEDailyAcquisitionConfig,
    calendar_dates: Sequence[date] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if config.start_date > config.end_date:
        raise ValueError("start_date must be on or before end_date")

    selected_dates = sorted(calendar_dates or list(dates_in_range(config.start_date, config.end_date)))
    archive_client = NSEDailyArchiveClient(config)
    previous_closes: dict[tuple[str, str], tuple[date, Decimal]] = {}
    session_summaries: list[NSEDailySessionSummary] = []
    calendar_rows: list[NSECalendarRow] = []
    totals: Counter[str] = Counter()
    actual_sessions: list[date] = []

    for index, trading_date in enumerate(selected_dates, start=1):
        if progress:
            progress(f"NSE daily session [{index}/{len(selected_dates)}] {trading_date.isoformat()}")

        result = archive_client.get_or_download(trading_date)
        if result.status == "FAILED":
            totals["sessions_failed"] += 1
            session_summaries.append(
                NSEDailySessionSummary(
                    trading_date=trading_date.isoformat(),
                    status="FAILED",
                    source_available=False,
                    notes=result.error,
                )
            )
            calendar_rows.append(calendar_row_for(trading_date, result, source_available=False, notes=result.error))
            continue

        if not result.source_available or result.path is None:
            totals["non_session_dates"] += 1
            session_summaries.append(
                NSEDailySessionSummary(
                    trading_date=trading_date.isoformat(),
                    status="NON_SESSION",
                    source_available=False,
                    notes="Official daily archive not available for this date.",
                )
            )
            calendar_rows.append(
                calendar_row_for(
                    trading_date,
                    result,
                    source_available=False,
                    notes="No official cash-market daily file found; treated as non-session.",
                )
            )
            continue

        try:
            parsed_records = parse_nse_daily_reference_file(result.path)
        except (ValueError, OSError) as exc:
            totals["sessions_failed"] += 1
            session_summaries.append(
                NSEDailySessionSummary(
                    trading_date=trading_date.isoformat(),
                    status="PARSE_FAILED",
                    source_available=False,
                    source_file=str(result.path),
                    source_format=result.source_format,
                    notes=exc.__class__.__name__,
                )
            )
            calendar_rows.append(calendar_row_for(trading_date, result, source_available=False, notes="Parser could not read file."))
            continue

        date_records = [record for record in parsed_records if record.trading_date == trading_date]
        if not date_records:
            totals["non_session_dates"] += 1
            session_summaries.append(
                NSEDailySessionSummary(
                    trading_date=trading_date.isoformat(),
                    status="DATE_MISMATCH",
                    source_available=False,
                    source_file=str(result.path),
                    source_format=result.source_format,
                    notes="File exists but contains no rows for the requested trading date.",
                )
            )
            calendar_rows.append(
                calendar_row_for(
                    trading_date,
                    result,
                    source_available=False,
                    notes="Official file did not contain the requested trading date.",
                )
            )
            continue

        normalized, summary = normalize_session_records(
            date_records,
            trading_date=trading_date,
            source_path=result.path,
            source_format=result.source_format,
            previous_closes=previous_closes,
            suspect_threshold=config.corporate_action_suspect_threshold,
        )
        write_normalized_session(config.normalized_dir, trading_date, normalized)
        actual_sessions.append(trading_date)
        session_summaries.append(summary)
        calendar_rows.append(calendar_row_for(trading_date, result, source_available=True))
        totals.update(
            {
                "sessions_downloaded": 1,
                "total_normalized_records": summary.normalized_records,
                "eq_records": summary.eq_records,
                "special_series_records": summary.special_series_records,
                "invalid_records": summary.invalid_records,
                "duplicate_records": summary.duplicate_records,
                "zero_volume_records": summary.zero_volume_records,
                "corporate_action_suspect_count": summary.corporate_action_suspects,
            }
        )

        if config.max_sessions is not None and len(actual_sessions) >= config.max_sessions:
            break

    return write_nse_daily_reports(
        config=config,
        session_summaries=session_summaries,
        calendar_rows=calendar_rows,
        totals=totals,
        actual_sessions=actual_sessions,
    )


def normalize_session_records(
    records: Sequence[NSEDailyRecord],
    *,
    trading_date: date,
    source_path: Path,
    source_format: str,
    previous_closes: dict[tuple[str, str], tuple[date, Decimal]] | None = None,
    suspect_threshold: Decimal = CORPORATE_ACTION_SUSPECT_THRESHOLD,
) -> tuple[list[NSECanonicalDailyRecord], NSEDailySessionSummary]:
    normalized_at = datetime.now(timezone.utc).isoformat()
    previous_closes = previous_closes if previous_closes is not None else {}
    seen: set[tuple[str, str, date]] = set()
    normalized: list[NSECanonicalDailyRecord] = []
    counts: Counter[str] = Counter()

    for record in records:
        errors = validate_nse_daily_record(record, expected_date=trading_date)
        dedupe_key = (record.symbol, record.series, record.trading_date)
        if dedupe_key in seen:
            counts["duplicates"] += 1
            continue
        seen.add(dedupe_key)

        if errors:
            counts["invalid"] += 1
            continue

        flags: list[str] = []
        if record.volume == 0:
            flags.append("ZERO_VOLUME")
            counts["zero_volume"] += 1

        previous = previous_closes.get((record.symbol, record.series))
        if previous and should_mark_corporate_action_suspect(
            previous_date=previous[0],
            previous_close=previous[1],
            current_date=record.trading_date,
            current_close=record.close,
            threshold=suspect_threshold,
        ):
            flags.append("CORPORATE_ACTION_SUSPECT")
            counts["corporate_action_suspects"] += 1

        previous_closes[(record.symbol, record.series)] = (record.trading_date, record.close)

        series_classification = classify_series(record.series)
        if series_classification == "NORMAL_EQUITY":
            counts["eq_records"] += 1
        else:
            counts["special_series_records"] += 1

        normalized.append(
            NSECanonicalDailyRecord(
                trading_date=record.trading_date,
                exchange="NSE",
                trading_symbol=record.symbol,
                series=record.series,
                isin=record.isin,
                open=record.open,
                high=record.high,
                low=record.low,
                close=record.close,
                volume=record.volume,
                traded_value=record.traded_value,
                source=OFFICIAL_NSE_SOURCE,
                source_file=str(source_path),
                source_format=record.source_format or source_format,
                series_classification=series_classification,
                quality_flags=";".join(flags),
                normalized_at=normalized_at,
            )
        )

    summary = NSEDailySessionSummary(
        trading_date=trading_date.isoformat(),
        status="AVAILABLE",
        source_available=True,
        source_file=str(source_path),
        source_format=source_format or (records[0].source_format if records else ""),
        normalized_records=len(normalized),
        eq_records=counts["eq_records"],
        special_series_records=counts["special_series_records"],
        invalid_records=counts["invalid"],
        duplicate_records=counts["duplicates"],
        zero_volume_records=counts["zero_volume"],
        corporate_action_suspects=counts["corporate_action_suspects"],
    )
    return normalized, summary


def validate_nse_daily_record(record: NSEDailyRecord, *, expected_date: date) -> list[str]:
    errors: list[str] = []
    if record.trading_date != expected_date:
        errors.append("date_mismatch")
    if not record.symbol:
        errors.append("missing_symbol")
    if not record.series:
        errors.append("missing_series")
    for field_name in ("open", "high", "low", "close"):
        if getattr(record, field_name) <= 0:
            errors.append(f"non_positive_{field_name}")
    if record.high < record.low:
        errors.append("high_below_low")
    if record.high < record.open or record.high < record.close:
        errors.append("high_below_open_or_close")
    if record.low > record.open or record.low > record.close:
        errors.append("low_above_open_or_close")
    if record.volume < 0:
        errors.append("negative_volume")
    return errors


def should_mark_corporate_action_suspect(
    *,
    previous_date: date,
    previous_close: Decimal,
    current_date: date,
    current_close: Decimal,
    threshold: Decimal,
) -> bool:
    if previous_close <= 0 or current_close <= 0:
        return False
    if current_date - previous_date > timedelta(days=10):
        return False
    move = abs(current_close - previous_close) / previous_close
    return move >= threshold


def classify_series(series: str) -> str:
    return "NORMAL_EQUITY" if series.upper() in NORMAL_EQUITY_SERIES else "SPECIAL_SERIES"


def calendar_row_for(
    trading_date: date,
    result: NSEArchiveFetchResult,
    *,
    source_available: bool,
    notes: str = "",
) -> NSECalendarRow:
    if source_available:
        session_type = "SPECIAL" if trading_date.weekday() >= 5 else "NORMAL"
    else:
        session_type = "UNKNOWN"
    return NSECalendarRow(
        trading_date=trading_date.isoformat(),
        session_type=session_type,
        source_reference=result.source_url,
        source_available=source_available,
        notes=notes,
    )


def write_normalized_session(
    normalized_dir: Path,
    trading_date: date,
    records: Sequence[NSECanonicalDailyRecord],
) -> Path:
    output_path = normalized_session_path(normalized_dir, trading_date)
    rows = [canonical_row(record) for record in sorted(records, key=lambda row: (row.trading_symbol, row.series))]
    write_csv(output_path, rows, CANONICAL_DAILY_FIELDS)
    return output_path


def normalized_session_path(normalized_dir: Path, trading_date: date) -> Path:
    return normalized_dir / f"{trading_date:%Y}" / f"{trading_date:%m}" / f"nse_daily_{trading_date:%Y%m%d}.csv"


def write_nse_daily_reports(
    *,
    config: NSEDailyAcquisitionConfig,
    session_summaries: Sequence[NSEDailySessionSummary],
    calendar_rows: Sequence[NSECalendarRow],
    totals: Counter[str],
    actual_sessions: Sequence[date],
) -> dict[str, Any]:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    config.calendar_dir.mkdir(parents=True, exist_ok=True)

    write_csv(config.calendar_path, [asdict(row) for row in calendar_rows], CALENDAR_FIELDS)

    session_summary_path = config.reports_dir / "nse_daily_session_summary.csv"
    write_csv(
        session_summary_path,
        [asdict(summary) for summary in session_summaries],
        SESSION_SUMMARY_FIELDS,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    raw_size = directory_size(config.raw_dir)
    normalized_size = directory_size(config.normalized_dir)
    summary = {
        "phase": "Step 02.3D",
        "task": "Official NSE primary daily-history dataset",
        "generated_at": generated_at,
        "official_sources": {
            "legacy_sec_bhavdata_full": NSEDailyReferenceProvider.legacy_url_template,
            "udiff_common_bhavcopy": NSEDailyReferenceProvider.udiff_url_template,
        },
        "daily_file_formats_supported": [
            "sec_bhavdata_full CSV",
            "CM-UDiFF bhavcopy ZIP/CSV",
            "NSE XLSX-like payloads served behind legacy CSV URLs",
        ],
        "run_mode": config.run_mode,
        "target_date_range": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "actual_date_range": {
            "first_trading_session": min(actual_sessions).isoformat() if actual_sessions else "",
            "last_trading_session": max(actual_sessions).isoformat() if actual_sessions else "",
        },
        "calendar": {
            "path": str(config.calendar_path),
            "calendar_dates_checked": len(calendar_rows),
            "trading_sessions_expected": len(actual_sessions),
            "non_session_dates": totals["non_session_dates"],
        },
        "sessions": {
            "downloaded": totals["sessions_downloaded"],
            "missing": 0,
            "failed": totals["sessions_failed"],
        },
        "records": {
            "total_normalized": totals["total_normalized_records"],
            "eq_records": totals["eq_records"],
            "special_series_records": totals["special_series_records"],
            "invalid_records": totals["invalid_records"],
            "duplicate_records": totals["duplicate_records"],
            "zero_volume_records": totals["zero_volume_records"],
            "corporate_action_suspect_count": totals["corporate_action_suspect_count"],
        },
        "storage": {
            "raw_path": str(config.raw_dir),
            "normalized_path": str(config.normalized_dir),
            "normalized_format": "partitioned CSV",
            "raw_storage_size_bytes": raw_size,
            "normalized_storage_size_bytes": normalized_size,
            "session_summary_csv": str(session_summary_path),
            "summary_csv": str(config.reports_dir / "nse_daily_dataset_summary.csv"),
            "summary_json": str(config.reports_dir / "nse_daily_dataset_summary.json"),
        },
        "series_handling": {
            "normal_eligible_equity_series": sorted(NORMAL_EQUITY_SERIES),
            "special_series_policy": "Preserved with SPECIAL_SERIES classification; not silently remapped to EQ.",
        },
        "corporate_actions": {
            "price_adjustment_status": PRICE_ADJUSTMENT_STATUS,
            "next_phase": "Step 02.3E - Corporate Actions & Adjusted Research Prices",
            "note": "No prices are adjusted in Step 02.3D.",
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_calculations_executed": 0,
        },
    }

    summary_csv_path = config.reports_dir / "nse_daily_dataset_summary.csv"
    write_csv(summary_csv_path, [flat_summary_row(summary)], DATASET_SUMMARY_FIELDS)
    summary_json_path = config.reports_dir / "nse_daily_dataset_summary.json"
    summary_json_path.write_text(json.dumps(json_safe(summary), indent=2), encoding="utf-8")
    return summary


def write_nse_daily_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source = report["official_sources"]
    calendar = report["calendar"]
    sessions = report["sessions"]
    records = report["records"]
    storage = report["storage"]
    target = report["target_date_range"]
    actual = report["actual_date_range"]
    markdown = "\n".join(
        [
            "# Official NSE 5-Year Daily Dataset",
            "",
            "Current phase: Step 02.3D - Official NSE primary daily-history dataset foundation",
            "",
            "## Official Sources",
            "",
            f"- Legacy security bhavcopy: {source['legacy_sec_bhavdata_full']}",
            f"- CM-UDiFF bhavcopy: {source['udiff_common_bhavcopy']}",
            "- Authoritative source policy: official NSE archives only.",
            "",
            "## Date Coverage",
            "",
            f"- Run mode: {report['run_mode']}",
            f"- Target start date: {target['start_date']}",
            f"- Target end date: {target['end_date']}",
            f"- Actual first trading session: {actual['first_trading_session']}",
            f"- Actual last trading session: {actual['last_trading_session']}",
            f"- Calendar dates checked: {calendar['calendar_dates_checked']}",
            f"- Trading sessions found from official files: {calendar['trading_sessions_expected']}",
            f"- Non-session dates identified: {calendar['non_session_dates']}",
            "",
            "## Retrieval And Calendar",
            "",
            "- The trading calendar is derived from official daily file availability and internal trade dates.",
            "- Weekends are treated as trading sessions only when official rows exist for that date.",
            "- Holidays are not counted as missing sessions when no official daily cash file exists.",
            f"- Calendar artifact: {calendar['path']}",
            "",
            "## Normalization",
            "",
            f"- Normalized format: {storage['normalized_format']}",
            f"- Raw path: {storage['raw_path']}",
            f"- Normalized path: {storage['normalized_path']}",
            "- Canonical rows retain exchange, symbol, series, ISIN when available, OHLCV, traded value, source file, source format, and adjustment status.",
            "",
            "## Series Handling",
            "",
            f"- Normal eligible equity series: {', '.join(report['series_handling']['normal_eligible_equity_series'])}",
            "- Special series are retained with provenance and are not remapped to EQ.",
            f"- EQ records: {records['eq_records']}",
            f"- Special-series records: {records['special_series_records']}",
            "",
            "## Data Quality",
            "",
            f"- Total normalized records: {records['total_normalized']}",
            f"- Invalid records skipped: {records['invalid_records']}",
            f"- Duplicate symbol/series/date rows skipped: {records['duplicate_records']}",
            f"- Zero-volume records retained and flagged: {records['zero_volume_records']}",
            f"- Corporate-action suspect rows flagged: {records['corporate_action_suspect_count']}",
            "",
            "## Completeness",
            "",
            f"- Sessions downloaded or imported from cache: {sessions['downloaded']}",
            f"- Expected trading sessions missing after calendar derivation: {sessions['missing']}",
            f"- Sessions failed: {sessions['failed']}",
            "",
            "## Corporate Actions",
            "",
            f"- Price adjustment status: {report['corporate_actions']['price_adjustment_status']}",
            "- No adjusted prices were fabricated or applied.",
            f"- Next planned phase: {report['corporate_actions']['next_phase']}",
            "",
            "## Limitations",
            "",
            "- This foundation does not calculate strategy indicators, momentum scores, breakouts, market regime, or backtests.",
            "- Bulk rows remain local and are not persisted to Supabase.",
            "- CSV was used instead of Parquet to avoid adding a heavy dependency before review.",
            "",
            "## Safety",
            "",
            "- ZERO order endpoints were called.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy calculations were executed.",
            "",
        ]
    )
    path.write_text(markdown, encoding="utf-8")


def nse_archive_candidates(trading_date: date) -> list[NSEArchiveCandidate]:
    ddmmyyyy = trading_date.strftime("%d%m%Y")
    yyyymmdd = trading_date.strftime("%Y%m%d")
    return [
        NSEArchiveCandidate(
            source_format="legacy_sec_bhavdata_full",
            url=NSEDailyReferenceProvider.legacy_url_template.format(ddmmyyyy=ddmmyyyy),
            filename=f"sec_bhavdata_full_{ddmmyyyy}.csv",
        ),
        NSEArchiveCandidate(
            source_format="udiff_common_bhavcopy",
            url=NSEDailyReferenceProvider.udiff_url_template.format(yyyymmdd=yyyymmdd),
            filename=f"BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip",
        ),
    ]


def default_start_date(today: date | None = None) -> date:
    today = today or datetime.now().date()
    try:
        return today.replace(year=today.year - 5)
    except ValueError:
        return today.replace(year=today.year - 5, day=28)


def latest_safe_end_date(today: date | None = None) -> date:
    return today or datetime.now().date()


def build_pilot_calendar_dates(
    start: date,
    end: date,
    *,
    target_dates: int = 36,
) -> list[date]:
    all_dates = list(dates_in_range(start, end))
    if len(all_dates) <= target_dates:
        return all_dates
    if target_dates <= 1:
        return [start]

    selected: list[date] = []
    last_index = len(all_dates) - 1
    for position in range(target_dates):
        index = round(position * last_index / (target_dates - 1))
        selected.append(all_dates[index])
    return sorted(set(selected))


def canonical_row(record: NSECanonicalDailyRecord) -> dict[str, Any]:
    return {
        "trading_date": record.trading_date.isoformat(),
        "exchange": record.exchange,
        "trading_symbol": record.trading_symbol,
        "series": record.series,
        "isin": record.isin,
        "open": str(record.open),
        "high": str(record.high),
        "low": str(record.low),
        "close": str(record.close),
        "volume": record.volume,
        "traded_value": str(record.traded_value) if record.traded_value is not None else "",
        "source": record.source,
        "source_file": record.source_file,
        "source_format": record.source_format,
        "series_classification": record.series_classification,
        "price_adjustment_status": record.price_adjustment_status,
        "quality_flags": record.quality_flags,
        "normalized_at": record.normalized_at,
    }


def flat_summary_row(report: dict[str, Any]) -> dict[str, Any]:
    target = report["target_date_range"]
    actual = report["actual_date_range"]
    calendar = report["calendar"]
    sessions = report["sessions"]
    records = report["records"]
    storage = report["storage"]
    return {
        "phase": report["phase"],
        "run_mode": report["run_mode"],
        "target_start_date": target["start_date"],
        "target_end_date": target["end_date"],
        "actual_first_trading_session": actual["first_trading_session"],
        "actual_last_trading_session": actual["last_trading_session"],
        "calendar_dates_checked": calendar["calendar_dates_checked"],
        "total_trading_sessions_expected": calendar["trading_sessions_expected"],
        "sessions_downloaded": sessions["downloaded"],
        "sessions_missing": sessions["missing"],
        "sessions_failed": sessions["failed"],
        "non_session_dates": calendar["non_session_dates"],
        "total_normalized_records": records["total_normalized"],
        "eq_records": records["eq_records"],
        "special_series_records": records["special_series_records"],
        "invalid_records": records["invalid_records"],
        "duplicate_records": records["duplicate_records"],
        "zero_volume_records": records["zero_volume_records"],
        "corporate_action_suspect_count": records["corporate_action_suspect_count"],
        "raw_storage_size_bytes": storage["raw_storage_size_bytes"],
        "normalized_storage_size_bytes": storage["normalized_storage_size_bytes"],
        "raw_path": storage["raw_path"],
        "normalized_path": storage["normalized_path"],
        "calendar_path": calendar["path"],
        "generated_at": report["generated_at"],
    }


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value

