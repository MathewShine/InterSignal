from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


METHODOLOGY_VERSION = "PRICE_ADJUSTED_STRUCTURAL_V1"
OFFICIAL_NSE_CA_SOURCE = "official_nse_corporate_actions"
OFFICIAL_NSE_CA_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
OFFICIAL_NSE_CA_API = "https://www.nseindia.com/api/corporates-corporateActions"

PRICE_ADJUSTMENT_ACTIONS = {"STOCK_SPLIT", "BONUS", "FACE_VALUE_CHANGE"}
CONTINUITY_BREAK_ACTIONS = {"DEMERGER", "MERGER", "SPINOFF", "CAPITAL_REDUCTION"}
IDENTITY_ACTIONS = {"SYMBOL_CHANGE", "NAME_CHANGE"}
MANUAL_REVIEW_ACTIONS = {"RIGHTS", "SPECIAL_DIVIDEND", "UNKNOWN"}
STRUCTURAL_ACTIONS = PRICE_ADJUSTMENT_ACTIONS | CONTINUITY_BREAK_ACTIONS

CORPORATE_ACTION_EVENT_FIELDS = [
    "event_id",
    "exchange",
    "symbol_at_event",
    "canonical_symbol",
    "isin",
    "company_name",
    "action_type",
    "announcement_date",
    "ex_date",
    "record_date",
    "effective_date",
    "ratio_numerator",
    "ratio_denominator",
    "old_face_value",
    "new_face_value",
    "cash_amount",
    "currency",
    "source_type",
    "source_reference",
    "source_document",
    "source_confidence",
    "adjustment_required",
    "adjustment_method",
    "review_status",
    "notes",
    "created_at",
]

ADJUSTMENT_FACTOR_FIELDS = [
    "canonical_instrument_id",
    "symbol",
    "event_date",
    "action_type",
    "raw_factor",
    "cumulative_backward_factor",
    "volume_factor",
    "factor_confidence",
    "source_event_id",
    "methodology_version",
    "review_status",
]

SOURCE_MANIFEST_FIELDS = [
    "source_id",
    "source_type",
    "source_url",
    "source_path",
    "start_date",
    "end_date",
    "fetched_at",
    "http_status",
    "rows_raw",
    "sha256",
    "notes",
]

SUSPECT_RECONCILIATION_FIELDS = [
    "symbol",
    "series",
    "isin",
    "suspect_date",
    "previous_trading_date",
    "previous_close",
    "current_open",
    "current_close",
    "raw_open_gap_percent",
    "raw_close_change_percent",
    "official_event_found",
    "official_event_ids",
    "official_action_types",
    "official_ex_dates",
    "explanation_status",
    "notes",
]

EVENTS_SUMMARY_FIELDS = [
    "action_type",
    "event_count",
    "price_adjustment_events",
    "manual_review_events",
    "continuity_break_events",
]

ADJUSTED_DAILY_FIELDS = [
    "trading_date",
    "symbol",
    "isin",
    "series",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
    "raw_volume",
    "adjusted_volume",
    "cumulative_adjustment_factor",
    "adjustment_applied",
    "adjustment_event_count",
    "adjustment_methodology_version",
    "research_usability_status",
    "source",
    "provenance",
]


@dataclass(frozen=True, slots=True)
class CorporateActionConfig:
    output_dir: Path
    start_date: date
    end_date: date
    methodology_version: str = METHODOLOGY_VERSION
    force_refresh: bool = False
    timeout_seconds: int = 30
    request_delay_seconds: float = 0.2
    adjusted_volume_enabled: bool = True
    suspect_match_window_days: int = 3
    suspect_detection_threshold: Decimal = Decimal("0.35")
    continuity_validation_tolerance: Decimal = Decimal("0.25")
    ordinary_dividend_adjustment_policy: str = "INFORMATIONAL_ONLY"
    special_dividend_adjustment_policy: str = "MANUAL_REVIEW_REQUIRED"
    rights_adjustment_policy: str = "ADJUSTMENT_REQUIRES_REVIEW"

    @property
    def reference_dir(self) -> Path:
        return self.output_dir / "reference" / "nse" / "corporate_actions"

    @property
    def raw_source_dir(self) -> Path:
        return self.reference_dir / "raw"

    @property
    def normalized_events_path(self) -> Path:
        return self.reference_dir / "corporate_action_events.csv"

    @property
    def coverage_path(self) -> Path:
        return self.reference_dir / "corporate_action_coverage.json"

    @property
    def source_manifest_path(self) -> Path:
        return self.reference_dir / "corporate_action_source_manifest.csv"

    @property
    def factor_path(self) -> Path:
        return self.reference_dir / "adjustment_factors.csv"

    @property
    def normalized_daily_dir(self) -> Path:
        return self.output_dir / "historical" / "daily" / "nse"

    @property
    def raw_daily_dir(self) -> Path:
        return self.output_dir / "raw" / "nse" / "daily"

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.output_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"


@dataclass(frozen=True, slots=True)
class CorporateActionEvent:
    event_id: str
    exchange: str
    symbol_at_event: str
    canonical_symbol: str
    isin: str | None
    company_name: str | None
    action_type: str
    announcement_date: date | None
    ex_date: date
    record_date: date | None
    effective_date: date | None
    ratio_numerator: Decimal | None
    ratio_denominator: Decimal | None
    old_face_value: Decimal | None
    new_face_value: Decimal | None
    cash_amount: Decimal | None
    currency: str | None
    source_type: str
    source_reference: str
    source_document: str | None
    source_confidence: str
    adjustment_required: bool
    adjustment_method: str
    review_status: str
    notes: str
    created_at: str

    @property
    def canonical_instrument_id(self) -> str:
        return self.isin or f"NSE:{self.canonical_symbol}:EQ"


@dataclass(frozen=True, slots=True)
class AdjustmentFactor:
    canonical_instrument_id: str
    symbol: str
    event_date: date
    action_type: str
    raw_factor: Decimal
    cumulative_backward_factor: Decimal
    volume_factor: Decimal | None
    factor_confidence: str
    source_event_id: str
    methodology_version: str
    review_status: str


@dataclass(frozen=True, slots=True)
class SourceManifestRow:
    source_id: str
    source_type: str
    source_url: str
    source_path: str
    start_date: str
    end_date: str
    fetched_at: str
    http_status: int
    rows_raw: int
    sha256: str
    notes: str


@dataclass(frozen=True, slots=True)
class DirectoryFingerprint:
    path: str
    exists: bool
    file_count: int
    total_size_bytes: int
    aggregate_sha256: str


@dataclass(frozen=True, slots=True)
class DailyRow:
    trading_date: date
    symbol: str
    series: str
    isin: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str
    source_file: str
    source_format: str
    series_classification: str
    price_adjustment_status: str
    quality_flags: str


def build_corporate_action_layer(
    *,
    config: CorporateActionConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    before_integrity = fingerprint_raw_inputs(config)

    source_bytes, source_url, http_status = acquire_official_corporate_actions_csv(config)
    raw_source_path = corporate_action_raw_source_path(config)
    raw_source_path.parent.mkdir(parents=True, exist_ok=True)
    raw_source_path.write_bytes(source_bytes)

    raw_text = source_bytes.decode("utf-8-sig", errors="replace")
    events = parse_nse_corporate_actions_csv(
        raw_text,
        source_path=raw_source_path,
        source_url=source_url,
        created_at=generated_at,
    )
    source_manifest = SourceManifestRow(
        source_id=source_id_for(config.start_date, config.end_date),
        source_type=OFFICIAL_NSE_CA_SOURCE,
        source_url=source_url,
        source_path=str(raw_source_path),
        start_date=config.start_date.isoformat(),
        end_date=config.end_date.isoformat(),
        fetched_at=generated_at,
        http_status=http_status,
        rows_raw=len(events),
        sha256=hashlib.sha256(source_bytes).hexdigest(),
        notes="Official NSE corporate-actions CSV requested from the corporate filings actions endpoint.",
    )

    factors = build_adjustment_factors(
        events,
        methodology_version=config.methodology_version,
        adjusted_volume_enabled=config.adjusted_volume_enabled,
    )
    if progress:
        progress(f"Corporate-action events normalized: {len(events)}; factors: {len(factors)}")

    write_csv(config.normalized_events_path, [corporate_action_event_row(event) for event in events], CORPORATE_ACTION_EVENT_FIELDS)
    write_csv(config.source_manifest_path, [asdict(source_manifest)], SOURCE_MANIFEST_FIELDS)
    write_csv(config.factor_path, [adjustment_factor_row(factor) for factor in factors], ADJUSTMENT_FACTOR_FIELDS)

    suspect_rows = reconcile_corporate_action_suspects(
        normalized_daily_dir=config.normalized_daily_dir,
        events=events,
        window_days=config.suspect_match_window_days,
    )
    suspect_path = config.reports_dir / "corporate_action_suspect_reconciliation.csv"
    write_csv(suspect_path, suspect_rows, SUSPECT_RECONCILIATION_FIELDS)

    pilot = build_pilot_adjustment_report(
        normalized_daily_dir=config.normalized_daily_dir,
        events=events,
        factors=factors,
        suspect_rows=suspect_rows,
        tolerance=config.continuity_validation_tolerance,
    )

    adjusted_result: dict[str, Any]
    if pilot["pilot_passed"]:
        adjusted_result = write_adjusted_daily_dataset(
            normalized_daily_dir=config.normalized_daily_dir,
            adjusted_daily_dir=config.adjusted_daily_dir,
            events=events,
            factors=factors,
            methodology_version=config.methodology_version,
            adjusted_volume_enabled=config.adjusted_volume_enabled,
            progress=progress,
        )
    else:
        adjusted_result = {
            "full_processing_completed": False,
            "reason": "Pilot validation did not pass; full adjusted dataset was not generated.",
            "record_count": 0,
            "adjusted_record_count": 0,
            "status_counts": {},
            "storage_size_bytes": directory_size(config.adjusted_daily_dir),
            "output_path": str(config.adjusted_daily_dir),
            "output_format": "partitioned CSV",
        }

    after_integrity = fingerprint_raw_inputs(config)
    duration_seconds = round(time.perf_counter() - started, 3)
    events_summary = corporate_action_events_summary(events)
    suspect_summary = Counter(row["explanation_status"] for row in suspect_rows)
    report = {
        "phase": "Step 02.3E",
        "task": "Corporate-action event layer and adjusted research price series",
        "generated_at": generated_at,
        "official_sources": {
            "nse_corporate_actions_page": OFFICIAL_NSE_CA_PAGE,
            "nse_corporate_actions_api": OFFICIAL_NSE_CA_API,
            "source_manifest_csv": str(config.source_manifest_path),
        },
        "date_coverage": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "methodology": {
            "version": config.methodology_version,
            "price_adjustment_target": "PRICE_ADJUSTED",
            "price_adjustment_policy": "Backward-adjust pre-ex-date OHLC for verified structural split, bonus, and face-value events only.",
            "ordinary_dividend_policy": config.ordinary_dividend_adjustment_policy,
            "special_dividend_policy": config.special_dividend_adjustment_policy,
            "rights_policy": config.rights_adjustment_policy,
            "merger_demerger_policy": "CONTINUITY_BREAK; no naive mechanical price factor is created.",
            "symbol_identity_policy": "Symbol/name changes are identity events, not price events; ISIN is preferred when present.",
            "adjusted_volume_policy": (
                "Adjusted volume is generated with the inverse structural price factor."
                if config.adjusted_volume_enabled
                else "Adjusted volume is left blank; raw volume is preserved."
            ),
        },
        "events": {
            "total": len(events),
            "counts_by_type": dict(sorted(Counter(event.action_type for event in events).items())),
            "price_adjustment_event_count": sum(1 for event in events if event.adjustment_required),
            "manual_review_event_count": sum(1 for event in events if event.review_status in {"ADJUSTMENT_REQUIRES_REVIEW", "MANUAL_REVIEW_REQUIRED", "UNRESOLVED"}),
            "continuity_break_event_count": sum(1 for event in events if event.review_status == "CONTINUITY_BREAK"),
            "summary_csv": str(config.reports_dir / "corporate_action_events_summary.csv"),
            "events_csv": str(config.normalized_events_path),
        },
        "adjustment_factors": {
            "count": len(factors),
            "path": str(config.factor_path),
            "methodology_version": config.methodology_version,
        },
        "suspect_reconciliation": {
            "suspects_reconciled": len(suspect_rows),
            "summary_counts": dict(sorted(suspect_summary.items())),
            "path": str(suspect_path),
        },
        "pilot": pilot,
        "adjusted_dataset": adjusted_result,
        "raw_integrity": {
            "before": {key: asdict(value) for key, value in before_integrity.items()},
            "after": {key: asdict(value) for key, value in after_integrity.items()},
            "unchanged": before_integrity == after_integrity,
        },
        "processing": {
            "duration_seconds": duration_seconds,
            "adjusted_storage_size_bytes": directory_size(config.adjusted_daily_dir),
        },
        "reports": {
            "summary_json": str(config.reports_dir / "corporate_action_summary.json"),
            "events_summary_csv": str(config.reports_dir / "corporate_action_events_summary.csv"),
            "suspect_reconciliation_csv": str(suspect_path),
            "adjusted_dataset_summary_json": str(config.reports_dir / "adjusted_dataset_summary.json"),
            "markdown": str(Path("docs") / "corporate-actions-and-adjusted-prices.md"),
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_calculations_executed": 0,
            "official_raw_nse_files_modified": before_integrity != after_integrity,
        },
        "ready_for_review": bool(pilot["pilot_passed"] and adjusted_result.get("full_processing_completed") and before_integrity == after_integrity),
    }

    write_csv(config.reports_dir / "corporate_action_events_summary.csv", events_summary, EVENTS_SUMMARY_FIELDS)
    write_json(config.coverage_path, corporate_action_coverage(report, source_manifest))
    write_json(config.reports_dir / "corporate_action_summary.json", report)
    write_json(config.reports_dir / "adjusted_dataset_summary.json", adjusted_result)
    return report


def source_id_for(start_date: date, end_date: date) -> str:
    return f"nse_corporate_actions_equities_{start_date:%Y%m%d}_{end_date:%Y%m%d}"


def corporate_action_raw_source_path(config: CorporateActionConfig) -> Path:
    return config.raw_source_dir / f"{source_id_for(config.start_date, config.end_date)}.csv"


def acquire_official_corporate_actions_csv(config: CorporateActionConfig) -> tuple[bytes, str, int]:
    source_path = corporate_action_raw_source_path(config)
    source_url = corporate_actions_url(config.start_date, config.end_date)
    if source_path.exists() and not config.force_refresh:
        return source_path.read_bytes(), source_url, 200

    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/csv,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": OFFICIAL_NSE_CA_PAGE,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            payload = response.read()
            if config.request_delay_seconds > 0:
                time.sleep(config.request_delay_seconds)
            return payload, source_url, response.status
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if source_path.exists():
            return source_path.read_bytes(), source_url, 200
        raise RuntimeError(f"Official NSE corporate-actions source unavailable: {exc.__class__.__name__}") from exc


def corporate_actions_url(start_date: date, end_date: date) -> str:
    params = urllib.parse.urlencode(
        {
            "index": "equities",
            "from_date": start_date.strftime("%d-%m-%Y"),
            "to_date": end_date.strftime("%d-%m-%Y"),
            "csv": "true",
        }
    )
    return f"{OFFICIAL_NSE_CA_API}?{params}"


def parse_nse_corporate_actions_csv(
    raw_csv: str,
    *,
    source_path: Path | str,
    source_url: str,
    created_at: str | None = None,
) -> list[CorporateActionEvent]:
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    reader = csv.DictReader(io.StringIO(raw_csv))
    events: list[CorporateActionEvent] = []
    for index, row in enumerate(reader, start=1):
        symbol = normalize_symbol(row.get("SYMBOL", ""))
        ex_date = parse_nse_date(row.get("EX-DATE", ""))
        if not symbol or ex_date is None:
            continue
        purpose = clean_text(row.get("PURPOSE", ""))
        action_type = classify_action_type(purpose)
        ratio = parse_ratio(purpose)
        old_face_value, new_face_value = parse_face_value_change(purpose)
        if old_face_value is None:
            old_face_value = parse_decimal(row.get("FACE VALUE", ""))
        cash_amount = parse_cash_amount(purpose)
        record_date = parse_nse_date(row.get("RECORD DATE", ""))
        adjustment_required, adjustment_method, review_status, notes = classify_adjustment_policy(
            action_type=action_type,
            purpose=purpose,
            ratio=ratio,
            old_face_value=old_face_value,
            new_face_value=new_face_value,
        )
        event = CorporateActionEvent(
            event_id=corporate_action_event_id(symbol=symbol, ex_date=ex_date, purpose=purpose, index=index),
            exchange="NSE",
            symbol_at_event=symbol,
            canonical_symbol=symbol,
            isin=blank_to_none(row.get("ISIN", "")),
            company_name=blank_to_none(clean_text(row.get("COMPANY NAME", ""))),
            action_type=action_type,
            announcement_date=None,
            ex_date=ex_date,
            record_date=record_date,
            effective_date=ex_date,
            ratio_numerator=ratio[0] if ratio else None,
            ratio_denominator=ratio[1] if ratio else None,
            old_face_value=old_face_value,
            new_face_value=new_face_value,
            cash_amount=cash_amount,
            currency="INR" if cash_amount is not None else None,
            source_type=OFFICIAL_NSE_CA_SOURCE,
            source_reference=source_url,
            source_document=str(source_path),
            source_confidence="VERIFIED_OFFICIAL",
            adjustment_required=adjustment_required,
            adjustment_method=adjustment_method,
            review_status=review_status,
            notes=notes or purpose,
            created_at=created_at,
        )
        events.append(event)
    return sorted(events, key=lambda event: (event.ex_date, event.symbol_at_event, event.event_id))


def classify_action_type(purpose: str) -> str:
    lower = purpose.lower()
    if not lower:
        return "UNKNOWN"
    if "change in name" in lower or "name change" in lower:
        return "NAME_CHANGE"
    if "symbol change" in lower or "change in symbol" in lower:
        return "SYMBOL_CHANGE"
    if "special dividend" in lower:
        return "SPECIAL_DIVIDEND"
    if "dividend" in lower:
        return "DIVIDEND"
    if "right" in lower:
        return "RIGHTS"
    if "demerger" in lower:
        return "DEMERGER"
    if "spin off" in lower or "spin-off" in lower or "spinoff" in lower:
        return "SPINOFF"
    if "merger" in lower or "amalgamation" in lower:
        return "MERGER"
    if "capital reduction" in lower or "reduction of capital" in lower:
        return "CAPITAL_REDUCTION"
    if "bonus" in lower and "ncrp" not in lower:
        return "BONUS"
    if "split" in lower or "sub-division" in lower or "sub division" in lower:
        return "STOCK_SPLIT"
    if "face value" in lower and "from" in lower and " to " in lower:
        return "FACE_VALUE_CHANGE"
    if "scheme" in lower or "arrangement" in lower:
        return "OTHER"
    return "OTHER"


def classify_adjustment_policy(
    *,
    action_type: str,
    purpose: str,
    ratio: tuple[Decimal, Decimal] | None,
    old_face_value: Decimal | None,
    new_face_value: Decimal | None,
) -> tuple[bool, str, str, str]:
    if action_type == "BONUS":
        if ratio is None:
            return False, "ADJUSTMENT_REQUIRES_REVIEW", "ADJUSTMENT_REQUIRES_REVIEW", "Bonus ratio was not parseable from the official purpose text."
        return True, "BACKWARD_PRICE_FACTOR", "PARSED", purpose
    if action_type in {"STOCK_SPLIT", "FACE_VALUE_CHANGE"}:
        if old_face_value and new_face_value and old_face_value > 0 and new_face_value > 0:
            return True, "BACKWARD_PRICE_FACTOR", "PARSED", purpose
        return False, "ADJUSTMENT_REQUIRES_REVIEW", "ADJUSTMENT_REQUIRES_REVIEW", "Face-value change terms were not parseable from the official purpose text."
    if action_type == "RIGHTS":
        return False, "ADJUSTMENT_REQUIRES_REVIEW", "ADJUSTMENT_REQUIRES_REVIEW", "Rights issues require subscription-price methodology review before price adjustment."
    if action_type == "SPECIAL_DIVIDEND":
        return False, "MANUAL_REVIEW_REQUIRED", "MANUAL_REVIEW_REQUIRED", "Special dividends are not included in structural price adjustment in this methodology."
    if action_type in CONTINUITY_BREAK_ACTIONS:
        return False, "CONTINUITY_BREAK", "CONTINUITY_BREAK", "Complex restructuring event; no naive mechanical price adjustment is applied."
    if action_type in IDENTITY_ACTIONS:
        return False, "IDENTITY_MAPPING", "PARSED", "Identity event only; not a price adjustment."
    if action_type == "DIVIDEND":
        return False, "INFORMATIONAL_ONLY", "PARSED", "Ordinary dividend; not applied to PRICE_ADJUSTED series."
    if action_type == "UNKNOWN":
        return False, "UNRESOLVED", "UNRESOLVED", "Corporate-action purpose could not be classified."
    return False, "INFORMATIONAL_ONLY", "PARSED", purpose


def parse_ratio(text: str) -> tuple[Decimal, Decimal] | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    numerator = parse_decimal(match.group(1))
    denominator = parse_decimal(match.group(2))
    if numerator is None or denominator is None or numerator <= 0 or denominator <= 0:
        return None
    return numerator, denominator


def bonus_price_factor(numerator: Decimal, denominator: Decimal) -> Decimal:
    if numerator <= 0 or denominator <= 0:
        raise ValueError("bonus ratio values must be positive")
    return denominator / (denominator + numerator)


def split_price_factor(old_face_value: Decimal, new_face_value: Decimal) -> Decimal:
    if old_face_value <= 0 or new_face_value <= 0:
        raise ValueError("face values must be positive")
    return new_face_value / old_face_value


def parse_face_value_change(text: str) -> tuple[Decimal | None, Decimal | None]:
    pattern = (
        r"from\s+(?:rs\.?|re\.?)?\s*([0-9]+(?:\.[0-9]+)?)\s*/?-?\s*(?:per share)?"
        r".*?\bto\s+(?:rs\.?|re\.?)?\s*([0-9]+(?:\.[0-9]+)?)"
    )
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None, None
    return parse_decimal(match.group(1)), parse_decimal(match.group(2))


def parse_cash_amount(text: str) -> Decimal | None:
    match = re.search(r"(?:rs\.?|re\.?)\s*-?\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return parse_decimal(match.group(1))


def build_adjustment_factors(
    events: Sequence[CorporateActionEvent],
    *,
    methodology_version: str = METHODOLOGY_VERSION,
    adjusted_volume_enabled: bool = True,
) -> list[AdjustmentFactor]:
    grouped: dict[str, list[CorporateActionEvent]] = defaultdict(list)
    for event in events:
        if event.adjustment_required:
            grouped[event.canonical_symbol].append(event)

    factors: list[AdjustmentFactor] = []
    for symbol, symbol_events in grouped.items():
        cumulative = Decimal("1")
        for event in sorted(symbol_events, key=lambda item: item.ex_date, reverse=True):
            raw_factor = event_raw_price_factor(event)
            if raw_factor is None:
                continue
            cumulative *= raw_factor
            volume_factor = Decimal("1") / raw_factor if adjusted_volume_enabled and raw_factor != 0 else None
            factors.append(
                AdjustmentFactor(
                    canonical_instrument_id=event.canonical_instrument_id,
                    symbol=symbol,
                    event_date=event.ex_date,
                    action_type=event.action_type,
                    raw_factor=raw_factor,
                    cumulative_backward_factor=cumulative,
                    volume_factor=volume_factor,
                    factor_confidence=event.source_confidence,
                    source_event_id=event.event_id,
                    methodology_version=methodology_version,
                    review_status="PARSED",
                )
            )
    return sorted(factors, key=lambda factor: (factor.symbol, factor.event_date, factor.source_event_id))


def event_raw_price_factor(event: CorporateActionEvent) -> Decimal | None:
    if event.action_type == "BONUS" and event.ratio_numerator and event.ratio_denominator:
        return bonus_price_factor(event.ratio_numerator, event.ratio_denominator)
    if event.action_type in {"STOCK_SPLIT", "FACE_VALUE_CHANGE"} and event.old_face_value and event.new_face_value:
        return split_price_factor(event.old_face_value, event.new_face_value)
    return None


def reconcile_corporate_action_suspects(
    *,
    normalized_daily_dir: Path,
    events: Sequence[CorporateActionEvent],
    window_days: int = 3,
) -> list[dict[str, Any]]:
    events_by_symbol: dict[str, list[CorporateActionEvent]] = defaultdict(list)
    for event in events:
        events_by_symbol[event.symbol_at_event].append(event)

    previous: dict[tuple[str, str], DailyRow] = {}
    rows: list[dict[str, Any]] = []
    for daily_path in normalized_daily_files(normalized_daily_dir):
        for row in read_daily_file(daily_path):
            key = (row.symbol, row.series)
            previous_row = previous.get(key)
            if "CORPORATE_ACTION_SUSPECT" in row.quality_flags:
                matches = nearby_events(events_by_symbol.get(row.symbol, []), row.trading_date, window_days=window_days)
                rows.append(suspect_reconciliation_row(row=row, previous_row=previous_row, matches=matches))
            previous[key] = row
    return rows


def suspect_reconciliation_row(
    *,
    row: DailyRow,
    previous_row: DailyRow | None,
    matches: Sequence[CorporateActionEvent],
) -> dict[str, Any]:
    if previous_row is None:
        open_gap = None
        close_change = None
        status = "DATA_QUALITY_ISSUE"
        notes = "Suspect row did not have a previous close in the local normalized dataset."
    else:
        open_gap = percentage_change(row.open, previous_row.close)
        close_change = percentage_change(row.close, previous_row.close)
        status, notes = classify_suspect(row=row, previous_row=previous_row, matches=matches)

    return {
        "symbol": row.symbol,
        "series": row.series,
        "isin": row.isin,
        "suspect_date": row.trading_date.isoformat(),
        "previous_trading_date": previous_row.trading_date.isoformat() if previous_row else "",
        "previous_close": decimal_string(previous_row.close) if previous_row else "",
        "current_open": decimal_string(row.open),
        "current_close": decimal_string(row.close),
        "raw_open_gap_percent": decimal_string(open_gap) if open_gap is not None else "",
        "raw_close_change_percent": decimal_string(close_change) if close_change is not None else "",
        "official_event_found": bool(matches),
        "official_event_ids": ";".join(event.event_id for event in matches),
        "official_action_types": ";".join(sorted({event.action_type for event in matches})),
        "official_ex_dates": ";".join(sorted({event.ex_date.isoformat() for event in matches})),
        "explanation_status": status,
        "notes": notes,
    }


def classify_suspect(
    *,
    row: DailyRow,
    previous_row: DailyRow,
    matches: Sequence[CorporateActionEvent],
) -> tuple[str, str]:
    if matches:
        action_types = {event.action_type for event in matches}
        if action_types & IDENTITY_ACTIONS:
            return "IDENTITY_CHANGE", "Official identity event exists near the suspect date."
        if action_types & (PRICE_ADJUSTMENT_ACTIONS | CONTINUITY_BREAK_ACTIONS):
            return "CONFIRMED_CORPORATE_ACTION", "Official structural or continuity-break event exists near the suspect date."
        return "LIKELY_CORPORATE_ACTION", "Official corporate-action event exists near the suspect date, but no structural factor is applied."

    if previous_row.close >= row.low and previous_row.close <= row.high:
        return "MARKET_MOVE", "No official action matched; prior close traded inside the current session range."
    return "UNRESOLVED", "No official corporate-action event matched the suspect date window."


def nearby_events(events: Sequence[CorporateActionEvent], target_date: date, *, window_days: int) -> list[CorporateActionEvent]:
    return [
        event
        for event in events
        if abs((event.ex_date - target_date).days) <= window_days
    ]


def build_pilot_adjustment_report(
    *,
    normalized_daily_dir: Path,
    events: Sequence[CorporateActionEvent],
    factors: Sequence[AdjustmentFactor],
    suspect_rows: Sequence[dict[str, Any]],
    tolerance: Decimal,
) -> dict[str, Any]:
    structural_symbols = [factor.symbol for factor in factors[:200]]
    complex_symbols = [event.symbol_at_event for event in events if event.action_type in CONTINUITY_BREAK_ACTIONS][:50]
    suspect_symbols = [str(row["symbol"]) for row in suspect_rows[:50]]
    indexed_rows = index_daily_rows_for_symbols(
        normalized_daily_dir,
        symbols=structural_symbols + complex_symbols + suspect_symbols,
    )
    factors_by_symbol = group_factors_by_symbol(factors)
    examples: list[dict[str, Any]] = []

    split = best_structural_pilot_example(
        action_type="STOCK_SPLIT",
        factors=factors,
        rows_by_symbol=indexed_rows,
        factors_by_symbol=factors_by_symbol,
        tolerance=tolerance,
    )
    if split:
        examples.append(split)

    bonus = best_structural_pilot_example(
        action_type="BONUS",
        factors=factors,
        rows_by_symbol=indexed_rows,
        factors_by_symbol=factors_by_symbol,
        tolerance=tolerance,
    )
    if bonus:
        examples.append(bonus)

    ordinary = ordinary_pilot_example(
        normalized_daily_dir=normalized_daily_dir,
        excluded_symbols={event.symbol_at_event for event in events},
    )
    if ordinary:
        examples.append(ordinary)

    complex_example = complex_pilot_example(events=events, rows_by_symbol=indexed_rows)
    if complex_example:
        examples.append(complex_example)

    suspect_example = suspect_pilot_example(suspect_rows=suspect_rows)
    if suspect_example:
        examples.append(suspect_example)

    structural_examples = [row for row in examples if row.get("pilot_type") in {"STOCK_SPLIT", "BONUS"}]
    structural_passed = all(row.get("validation_status") == "PASS" for row in structural_examples)
    pilot_passed = bool(structural_examples) and structural_passed and ordinary is not None
    return {
        "pilot_passed": pilot_passed,
        "examples": examples,
        "requirements": {
            "has_stock_split": any(row.get("pilot_type") == "STOCK_SPLIT" for row in examples),
            "has_bonus": any(row.get("pilot_type") == "BONUS" for row in examples),
            "has_no_action": ordinary is not None,
            "has_complex_case": complex_example is not None,
            "has_suspect": suspect_example is not None,
        },
    }


def best_structural_pilot_example(
    *,
    action_type: str,
    factors: Sequence[AdjustmentFactor],
    rows_by_symbol: dict[str, list[DailyRow]],
    factors_by_symbol: dict[str, list[AdjustmentFactor]],
    tolerance: Decimal,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for factor in factors:
        if factor.action_type != action_type:
            continue
        rows = rows_by_symbol.get(factor.symbol, [])
        example = structural_pilot_example(
            factor=factor,
            rows=rows,
            factors_by_symbol=factors_by_symbol,
            tolerance=tolerance,
        )
        if example:
            candidates.append(example)
    passing = [row for row in candidates if row["validation_status"] == "PASS"]
    if passing:
        return sorted(passing, key=lambda row: abs(Decimal(row["adjusted_gap_percent"])))[0]
    return candidates[0] if candidates else None


def structural_pilot_example(
    *,
    factor: AdjustmentFactor,
    rows: Sequence[DailyRow],
    factors_by_symbol: dict[str, list[AdjustmentFactor]],
    tolerance: Decimal,
) -> dict[str, Any] | None:
    before = [row for row in rows if row.trading_date < factor.event_date]
    event_or_after = [row for row in rows if row.trading_date >= factor.event_date]
    if not before or not event_or_after:
        return None
    previous_row = before[-1]
    current_row = event_or_after[0]
    previous_factor, previous_event_ids = cumulative_factor_for_date(
        factors_by_symbol.get(factor.symbol, []),
        previous_row.trading_date,
    )
    current_factor, current_event_ids = cumulative_factor_for_date(
        factors_by_symbol.get(factor.symbol, []),
        current_row.trading_date,
    )
    raw_gap = percentage_change(current_row.close, previous_row.close)
    adjusted_previous_close = adjust_decimal(previous_row.close, previous_factor)
    adjusted_current_close = adjust_decimal(current_row.close, current_factor)
    adjusted_gap = percentage_change(adjusted_current_close, adjusted_previous_close)
    worsened_by = abs(adjusted_gap) - abs(raw_gap)
    validation_status = "PASS" if worsened_by <= tolerance * Decimal("100") else "REVIEW"
    return {
        "pilot_type": factor.action_type,
        "symbol": factor.symbol,
        "event_date": factor.event_date.isoformat(),
        "source_event_id": factor.source_event_id,
        "raw_factor": decimal_string(factor.raw_factor),
        "previous_trading_date": previous_row.trading_date.isoformat(),
        "event_trading_date": current_row.trading_date.isoformat(),
        "raw_previous_close": decimal_string(previous_row.close),
        "raw_event_close": decimal_string(current_row.close),
        "adjusted_previous_close": decimal_string(adjusted_previous_close),
        "adjusted_event_close": decimal_string(adjusted_current_close),
        "raw_gap_percent": decimal_string(raw_gap),
        "adjusted_gap_percent": decimal_string(adjusted_gap),
        "validation_status": validation_status,
        "provenance": ";".join(sorted(set(previous_event_ids + current_event_ids))),
    }


def ordinary_pilot_example(
    *,
    normalized_daily_dir: Path,
    excluded_symbols: set[str],
) -> dict[str, Any] | None:
    previous: dict[str, DailyRow] = {}
    for daily_path in normalized_daily_files(normalized_daily_dir):
        for row in read_daily_file(daily_path):
            if row.series != "EQ" or row.symbol in excluded_symbols:
                continue
            earlier = previous.get(row.symbol)
            previous[row.symbol] = row
            if earlier is None:
                continue
            raw_gap = percentage_change(row.close, earlier.close)
            return {
                "pilot_type": "NO_ACTION",
                "symbol": row.symbol,
                "previous_trading_date": earlier.trading_date.isoformat(),
                "event_trading_date": row.trading_date.isoformat(),
                "raw_previous_close": decimal_string(earlier.close),
                "raw_event_close": decimal_string(row.close),
                "adjusted_previous_close": decimal_string(earlier.close),
                "adjusted_event_close": decimal_string(row.close),
                "raw_gap_percent": decimal_string(raw_gap),
                "adjusted_gap_percent": decimal_string(raw_gap),
                "validation_status": "PASS",
                "provenance": "No official corporate-action event found for this symbol in the source coverage.",
            }
    return None


def complex_pilot_example(
    *,
    events: Sequence[CorporateActionEvent],
    rows_by_symbol: dict[str, list[DailyRow]],
) -> dict[str, Any] | None:
    for event in events:
        if event.action_type not in CONTINUITY_BREAK_ACTIONS:
            continue
        rows = rows_by_symbol.get(event.symbol_at_event, [])
        if not rows:
            continue
        before = [row for row in rows if row.trading_date < event.ex_date]
        after = [row for row in rows if row.trading_date >= event.ex_date]
        if not before or not after:
            continue
        return {
            "pilot_type": event.action_type,
            "symbol": event.symbol_at_event,
            "event_date": event.ex_date.isoformat(),
            "source_event_id": event.event_id,
            "previous_trading_date": before[-1].trading_date.isoformat(),
            "event_trading_date": after[0].trading_date.isoformat(),
            "raw_previous_close": decimal_string(before[-1].close),
            "raw_event_close": decimal_string(after[0].close),
            "adjusted_previous_close": decimal_string(before[-1].close),
            "adjusted_event_close": decimal_string(after[0].close),
            "raw_gap_percent": decimal_string(percentage_change(after[0].close, before[-1].close)),
            "adjusted_gap_percent": decimal_string(percentage_change(after[0].close, before[-1].close)),
            "validation_status": "CONTINUITY_BREAK",
            "provenance": event.event_id,
        }
    return None


def suspect_pilot_example(suspect_rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not suspect_rows:
        return None
    preferred = next(
        (
            row
            for row in suspect_rows
            if row["explanation_status"] in {"CONFIRMED_CORPORATE_ACTION", "LIKELY_CORPORATE_ACTION"}
        ),
        suspect_rows[0],
    )
    return {
        "pilot_type": "SUSPECT_RECONCILIATION",
        "symbol": preferred["symbol"],
        "event_trading_date": preferred["suspect_date"],
        "raw_previous_close": preferred["previous_close"],
        "raw_event_close": preferred["current_close"],
        "raw_gap_percent": preferred["raw_close_change_percent"],
        "adjusted_gap_percent": "",
        "validation_status": preferred["explanation_status"],
        "provenance": preferred["official_event_ids"],
    }


def write_adjusted_daily_dataset(
    *,
    normalized_daily_dir: Path,
    adjusted_daily_dir: Path,
    events: Sequence[CorporateActionEvent],
    factors: Sequence[AdjustmentFactor],
    methodology_version: str,
    adjusted_volume_enabled: bool,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    factors_by_symbol = group_factors_by_symbol(factors)
    profile_by_symbol = research_status_profile(events)
    status_counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    first_date: date | None = None
    last_date: date | None = None
    files = normalized_daily_files(normalized_daily_dir)

    for index, source_path in enumerate(files, start=1):
        rows = read_daily_file(source_path)
        if not rows:
            continue
        output_path = adjusted_daily_path(adjusted_daily_dir, rows[0].trading_date)
        output_rows: list[dict[str, Any]] = []
        for row in rows:
            factor, event_ids = cumulative_factor_for_date(
                factors_by_symbol.get(row.symbol, []),
                row.trading_date,
            )
            status = research_usability_status(row=row, profile=profile_by_symbol.get(row.symbol))
            adjusted_volume = adjusted_volume_value(row.volume, factor) if adjusted_volume_enabled else None
            output_rows.append(
                {
                    "trading_date": row.trading_date.isoformat(),
                    "symbol": row.symbol,
                    "isin": row.isin,
                    "series": row.series,
                    "raw_open": decimal_string(row.open),
                    "raw_high": decimal_string(row.high),
                    "raw_low": decimal_string(row.low),
                    "raw_close": decimal_string(row.close),
                    "adjusted_open": decimal_string(adjust_decimal(row.open, factor)),
                    "adjusted_high": decimal_string(adjust_decimal(row.high, factor)),
                    "adjusted_low": decimal_string(adjust_decimal(row.low, factor)),
                    "adjusted_close": decimal_string(adjust_decimal(row.close, factor)),
                    "raw_volume": row.volume,
                    "adjusted_volume": decimal_string(adjusted_volume) if adjusted_volume is not None else "",
                    "cumulative_adjustment_factor": decimal_string(factor),
                    "adjustment_applied": factor != Decimal("1"),
                    "adjustment_event_count": len(event_ids),
                    "adjustment_methodology_version": methodology_version,
                    "research_usability_status": status,
                    "source": row.source,
                    "provenance": ";".join(event_ids),
                }
            )
            totals["record_count"] += 1
            if factor != Decimal("1"):
                totals["adjusted_record_count"] += 1
            status_counts[status] += 1
            first_date = row.trading_date if first_date is None else min(first_date, row.trading_date)
            last_date = row.trading_date if last_date is None else max(last_date, row.trading_date)
        write_csv(output_path, output_rows, ADJUSTED_DAILY_FIELDS)
        totals["files_written"] += 1
        if progress and index % 100 == 0:
            progress(f"Adjusted daily files written: {index}/{len(files)}")

    duration_seconds = round(time.perf_counter() - start, 3)
    record_count = totals["record_count"]
    adjusted_ready = status_counts["ADJUSTED_READY"]
    return {
        "full_processing_completed": True,
        "output_path": str(adjusted_daily_dir),
        "output_format": "partitioned CSV",
        "file_count": totals["files_written"],
        "record_count": record_count,
        "adjusted_record_count": totals["adjusted_record_count"],
        "date_range": {
            "first_trading_session": first_date.isoformat() if first_date else "",
            "last_trading_session": last_date.isoformat() if last_date else "",
        },
        "status_counts": dict(sorted(status_counts.items())),
        "adjusted_ready_count": adjusted_ready,
        "adjusted_ready_percent": decimal_string((Decimal(adjusted_ready) / Decimal(record_count) * Decimal("100")) if record_count else Decimal("0")),
        "raw_only_count": status_counts["RAW_ONLY"],
        "continuity_break_count": status_counts["CONTINUITY_BREAK"],
        "manual_review_required_count": status_counts["MANUAL_REVIEW_REQUIRED"],
        "storage_size_bytes": directory_size(adjusted_daily_dir),
        "processing_duration_seconds": duration_seconds,
    }


def cumulative_factor_for_date(
    factors: Sequence[AdjustmentFactor],
    trading_date: date,
) -> tuple[Decimal, list[str]]:
    cumulative = Decimal("1")
    event_ids: list[str] = []
    for factor in factors:
        if trading_date < factor.event_date:
            cumulative *= factor.raw_factor
            event_ids.append(factor.source_event_id)
    return cumulative, event_ids


def group_factors_by_symbol(factors: Sequence[AdjustmentFactor]) -> dict[str, list[AdjustmentFactor]]:
    grouped: dict[str, list[AdjustmentFactor]] = defaultdict(list)
    for factor in factors:
        grouped[factor.symbol].append(factor)
    for symbol, symbol_factors in grouped.items():
        grouped[symbol] = sorted(symbol_factors, key=lambda item: item.event_date)
    return grouped


def research_status_profile(events: Sequence[CorporateActionEvent]) -> dict[str, str]:
    profile: dict[str, str] = {}
    for event in events:
        current = profile.get(event.symbol_at_event)
        if event.action_type in CONTINUITY_BREAK_ACTIONS:
            profile[event.symbol_at_event] = "CONTINUITY_BREAK"
        elif event.review_status in {"ADJUSTMENT_REQUIRES_REVIEW", "MANUAL_REVIEW_REQUIRED", "UNRESOLVED"}:
            if current != "CONTINUITY_BREAK":
                profile[event.symbol_at_event] = "MANUAL_REVIEW_REQUIRED"
        elif current is None:
            profile[event.symbol_at_event] = "ADJUSTED_READY"
    return profile


def research_usability_status(*, row: DailyRow, profile: str | None) -> str:
    if row.series != "EQ" or row.series_classification != "NORMAL_EQUITY":
        return "RAW_ONLY"
    return profile or "ADJUSTED_READY"


def adjusted_daily_path(adjusted_daily_dir: Path, trading_date: date) -> Path:
    return adjusted_daily_dir / f"{trading_date:%Y}" / f"{trading_date:%m}" / f"nse_adjusted_daily_{trading_date:%Y%m%d}.csv"


def normalized_daily_files(normalized_daily_dir: Path) -> list[Path]:
    if not normalized_daily_dir.exists():
        return []
    return sorted(normalized_daily_dir.glob("*/*/nse_daily_*.csv"))


def read_daily_file(path: Path) -> list[DailyRow]:
    rows: list[DailyRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                trading_date = date.fromisoformat(row["trading_date"])
                rows.append(
                    DailyRow(
                        trading_date=trading_date,
                        symbol=normalize_symbol(row.get("trading_symbol", "")),
                        series=clean_text(row.get("series", "")),
                        isin=clean_text(row.get("isin", "")),
                        open=parse_decimal(row.get("open", "")) or Decimal("0"),
                        high=parse_decimal(row.get("high", "")) or Decimal("0"),
                        low=parse_decimal(row.get("low", "")) or Decimal("0"),
                        close=parse_decimal(row.get("close", "")) or Decimal("0"),
                        volume=int(Decimal(clean_text(row.get("volume", "0")) or "0")),
                        source=clean_text(row.get("source", "")),
                        source_file=clean_text(row.get("source_file", "")),
                        source_format=clean_text(row.get("source_format", "")),
                        series_classification=clean_text(row.get("series_classification", "")),
                        price_adjustment_status=clean_text(row.get("price_adjustment_status", "")),
                        quality_flags=clean_text(row.get("quality_flags", "")),
                    )
                )
            except (KeyError, ValueError, InvalidOperation):
                continue
    return rows


def index_daily_rows_for_symbols(normalized_daily_dir: Path, *, symbols: Iterable[str]) -> dict[str, list[DailyRow]]:
    wanted = {normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)}
    rows_by_symbol: dict[str, list[DailyRow]] = defaultdict(list)
    if not wanted:
        return rows_by_symbol
    for daily_path in normalized_daily_files(normalized_daily_dir):
        for row in read_daily_file(daily_path):
            if row.symbol in wanted and row.series == "EQ":
                rows_by_symbol[row.symbol].append(row)
    for symbol, rows in rows_by_symbol.items():
        rows_by_symbol[symbol] = sorted(rows, key=lambda item: item.trading_date)
    return dict(rows_by_symbol)


def corporate_action_events_summary(events: Sequence[CorporateActionEvent]) -> list[dict[str, Any]]:
    grouped: dict[str, list[CorporateActionEvent]] = defaultdict(list)
    for event in events:
        grouped[event.action_type].append(event)
    rows: list[dict[str, Any]] = []
    for action_type, action_events in sorted(grouped.items()):
        rows.append(
            {
                "action_type": action_type,
                "event_count": len(action_events),
                "price_adjustment_events": sum(1 for event in action_events if event.adjustment_required),
                "manual_review_events": sum(
                    1
                    for event in action_events
                    if event.review_status in {"ADJUSTMENT_REQUIRES_REVIEW", "MANUAL_REVIEW_REQUIRED", "UNRESOLVED"}
                ),
                "continuity_break_events": sum(1 for event in action_events if event.review_status == "CONTINUITY_BREAK"),
            }
        )
    return rows


def corporate_action_coverage(report: dict[str, Any], source_manifest: SourceManifestRow) -> dict[str, Any]:
    return {
        "phase": report["phase"],
        "generated_at": report["generated_at"],
        "source_manifest": asdict(source_manifest),
        "date_coverage": report["date_coverage"],
        "official_sources": report["official_sources"],
        "events": report["events"],
        "adjustment_factors": report["adjustment_factors"],
        "suspect_reconciliation": report["suspect_reconciliation"],
        "adjusted_dataset": report["adjusted_dataset"],
        "raw_integrity": report["raw_integrity"],
        "methodology": report["methodology"],
        "ready_for_review": report["ready_for_review"],
    }


def write_corporate_actions_markdown_report(report: dict[str, Any], path: Path) -> None:
    events = report["events"]
    adjusted = report["adjusted_dataset"]
    suspect = report["suspect_reconciliation"]
    pilot = report["pilot"]
    methodology = report["methodology"]
    counts = events["counts_by_type"]
    status_counts = adjusted.get("status_counts", {})
    lines = [
        "# Corporate Actions And Adjusted Prices",
        "",
        "Current phase: Step 02.3E / Command 01 - corporate-action event layer and adjusted research price series",
        "",
        "## Sources Used",
        "",
        f"- NSE corporate actions page: {report['official_sources']['nse_corporate_actions_page']}",
        f"- NSE corporate actions API: {report['official_sources']['nse_corporate_actions_api']}",
        f"- Source manifest: {report['official_sources']['source_manifest_csv']}",
        "- Raw source artifacts are cached separately from normalized events.",
        "",
        "## Coverage",
        "",
        f"- Start date: {report['date_coverage']['start_date']}",
        f"- End date: {report['date_coverage']['end_date']}",
        f"- Official events acquired: {events['total']}",
        f"- Adjustment factors generated: {report['adjustment_factors']['count']}",
        "",
        "## Action Types Found",
        "",
        f"- STOCK_SPLIT: {counts.get('STOCK_SPLIT', 0)}",
        f"- BONUS: {counts.get('BONUS', 0)}",
        f"- DIVIDEND: {counts.get('DIVIDEND', 0)}",
        f"- SPECIAL_DIVIDEND: {counts.get('SPECIAL_DIVIDEND', 0)}",
        f"- RIGHTS: {counts.get('RIGHTS', 0)}",
        f"- MERGER/DEMERGER/SPINOFF: {counts.get('MERGER', 0) + counts.get('DEMERGER', 0) + counts.get('SPINOFF', 0)}",
        f"- SYMBOL/NAME changes: {counts.get('SYMBOL_CHANGE', 0) + counts.get('NAME_CHANGE', 0)}",
        f"- OTHER/UNKNOWN: {counts.get('OTHER', 0) + counts.get('UNKNOWN', 0)}",
        "",
        "## Adjustment Methodology",
        "",
        f"- Methodology version: {methodology['version']}",
        f"- Price target: {methodology['price_adjustment_target']}",
        f"- Structural policy: {methodology['price_adjustment_policy']}",
        f"- Dividend policy: {methodology['ordinary_dividend_policy']}",
        f"- Special dividend policy: {methodology['special_dividend_policy']}",
        f"- Rights policy: {methodology['rights_policy']}",
        f"- Merger/demerger policy: {methodology['merger_demerger_policy']}",
        f"- Symbol identity policy: {methodology['symbol_identity_policy']}",
        f"- Adjusted-volume policy: {methodology['adjusted_volume_policy']}",
        "",
        "## Suspect Reconciliation",
        "",
        f"- Existing suspect rows reconciled: {suspect['suspects_reconciled']}",
        f"- CONFIRMED_CORPORATE_ACTION: {suspect['summary_counts'].get('CONFIRMED_CORPORATE_ACTION', 0)}",
        f"- LIKELY_CORPORATE_ACTION: {suspect['summary_counts'].get('LIKELY_CORPORATE_ACTION', 0)}",
        f"- MARKET_MOVE: {suspect['summary_counts'].get('MARKET_MOVE', 0)}",
        f"- DATA_QUALITY_ISSUE: {suspect['summary_counts'].get('DATA_QUALITY_ISSUE', 0)}",
        f"- IDENTITY_CHANGE: {suspect['summary_counts'].get('IDENTITY_CHANGE', 0)}",
        f"- UNRESOLVED: {suspect['summary_counts'].get('UNRESOLVED', 0)}",
        f"- Reconciliation CSV: {suspect['path']}",
        "",
        "## Pilot Examples",
        "",
    ]
    for example in pilot["examples"]:
        lines.append(
            "- "
            + ", ".join(
                [
                    f"type={example.get('pilot_type', '')}",
                    f"symbol={example.get('symbol', '')}",
                    f"date={example.get('event_date') or example.get('event_trading_date', '')}",
                    f"raw_gap={example.get('raw_gap_percent', '')}",
                    f"adjusted_gap={example.get('adjusted_gap_percent', '')}",
                    f"status={example.get('validation_status', '')}",
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Adjusted Dataset",
            "",
            f"- Full processing completed: {adjusted.get('full_processing_completed')}",
            f"- Output path: {adjusted.get('output_path')}",
            f"- Output format: {adjusted.get('output_format')}",
            f"- Records generated: {adjusted.get('record_count', 0)}",
            f"- Records with adjusted factor applied: {adjusted.get('adjusted_record_count', 0)}",
            f"- ADJUSTED_READY: {status_counts.get('ADJUSTED_READY', 0)}",
            f"- RAW_ONLY: {status_counts.get('RAW_ONLY', 0)}",
            f"- CONTINUITY_BREAK: {status_counts.get('CONTINUITY_BREAK', 0)}",
            f"- MANUAL_REVIEW_REQUIRED: {status_counts.get('MANUAL_REVIEW_REQUIRED', 0)}",
            "",
            "## Auditability",
            "",
            "- Every adjusted row carries raw OHLCV, adjusted OHLCV, cumulative factor, event count, methodology version, and source-event provenance.",
            "- Official raw NSE files and normalized RAW candles are not overwritten by this step.",
            f"- Raw input integrity unchanged: {report['raw_integrity']['unchanged']}",
            "",
            "## Known Limitations",
            "",
            "- NSE corporate-action rows do not always include ISIN values, so symbol-level identity remains the default when ISIN is absent.",
            "- Rights issues, special dividends, mergers, demergers, and spinoffs are stored and flagged, not mechanically adjusted.",
            "- This is not a total-return series; ordinary dividends remain informational only.",
            "- Suspect reconciliation is official-source based and conservative; unmatched discontinuities remain UNRESOLVED or MARKET_MOVE.",
            "",
            "## Safety",
            "",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy calculations were executed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def fingerprint_raw_inputs(config: CorporateActionConfig) -> dict[str, DirectoryFingerprint]:
    return {
        "raw_nse": fingerprint_directory(config.raw_daily_dir),
        "normalized_raw_nse": fingerprint_directory(config.normalized_daily_dir),
    }


def fingerprint_directory(path: Path) -> DirectoryFingerprint:
    if not path.exists():
        return DirectoryFingerprint(str(path), False, 0, 0, "")
    aggregate = hashlib.sha256()
    file_count = 0
    total_size = 0
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = child.relative_to(path).as_posix()
        content_hash = hashlib.sha256()
        with child.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                content_hash.update(chunk)
        digest = content_hash.hexdigest()
        size = child.stat().st_size
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(str(size).encode("ascii"))
        aggregate.update(digest.encode("ascii"))
        file_count += 1
        total_size += size
    return DirectoryFingerprint(str(path), True, file_count, total_size, aggregate.hexdigest())


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def corporate_action_event_row(event: CorporateActionEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "exchange": event.exchange,
        "symbol_at_event": event.symbol_at_event,
        "canonical_symbol": event.canonical_symbol,
        "isin": event.isin or "",
        "company_name": event.company_name or "",
        "action_type": event.action_type,
        "announcement_date": event.announcement_date.isoformat() if event.announcement_date else "",
        "ex_date": event.ex_date.isoformat(),
        "record_date": event.record_date.isoformat() if event.record_date else "",
        "effective_date": event.effective_date.isoformat() if event.effective_date else "",
        "ratio_numerator": decimal_string(event.ratio_numerator),
        "ratio_denominator": decimal_string(event.ratio_denominator),
        "old_face_value": decimal_string(event.old_face_value),
        "new_face_value": decimal_string(event.new_face_value),
        "cash_amount": decimal_string(event.cash_amount),
        "currency": event.currency or "",
        "source_type": event.source_type,
        "source_reference": event.source_reference,
        "source_document": event.source_document or "",
        "source_confidence": event.source_confidence,
        "adjustment_required": event.adjustment_required,
        "adjustment_method": event.adjustment_method,
        "review_status": event.review_status,
        "notes": event.notes,
        "created_at": event.created_at,
    }


def adjustment_factor_row(factor: AdjustmentFactor) -> dict[str, Any]:
    return {
        "canonical_instrument_id": factor.canonical_instrument_id,
        "symbol": factor.symbol,
        "event_date": factor.event_date.isoformat(),
        "action_type": factor.action_type,
        "raw_factor": decimal_string(factor.raw_factor),
        "cumulative_backward_factor": decimal_string(factor.cumulative_backward_factor),
        "volume_factor": decimal_string(factor.volume_factor),
        "factor_confidence": factor.factor_confidence,
        "source_event_id": factor.source_event_id,
        "methodology_version": factor.methodology_version,
        "review_status": factor.review_status,
    }


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(value), indent=2), encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_string(value)
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


def corporate_action_event_id(*, symbol: str, ex_date: date, purpose: str, index: int) -> str:
    payload = f"{symbol}|{ex_date.isoformat()}|{purpose}|{index}".encode("utf-8")
    return "nse-ca-" + hashlib.sha256(payload).hexdigest()[:16]


def percentage_change(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        return Decimal("0")
    return ((current - previous) / previous * Decimal("100")).quantize(Decimal("0.0001"))


def adjust_decimal(value: Decimal, factor: Decimal) -> Decimal:
    return (value * factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def adjusted_volume_value(raw_volume: int, price_factor: Decimal) -> Decimal:
    if price_factor == 0:
        return Decimal(raw_volume)
    return (Decimal(raw_volume) / price_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def parse_nse_date(value: str | None) -> date | None:
    text = clean_text(value or "")
    if not text or text == "-":
        return None
    for pattern in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_decimal(value: str | Decimal | int | float | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = clean_text(str(value))
    if not text or text == "-":
        return None
    text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_string(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    return format(normalized, "f")


def normalize_symbol(value: str) -> str:
    return clean_text(value).upper()


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def blank_to_none(value: str | None) -> str | None:
    text = clean_text(value)
    return text if text and text != "-" else None
