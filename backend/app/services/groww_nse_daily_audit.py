from __future__ import annotations

import asyncio
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.models.ingestion import ASIA_KOLKATA, DailyCandle
from app.providers.groww import GrowwAuthService, GrowwHistoricalProvider
from app.providers.groww.historical import (
    GrowwHistoricalProviderConfig,
    INTERVAL_LIMIT_DAYS,
)
from app.providers.nse import NSEDailyReferenceProvider, NSEDailyRecord, NSEDailySession
from app.services.nifty500_acquisition import (
    GrowwInstrumentMapping,
    NIFTY500_INDEX_NAME,
    PRICE_ADJUSTMENT_STATUS,
    chunk_date_range,
    map_constituents_to_groww,
    normalize_nifty500_constituents,
)

PRICE_TOLERANCE = Decimal("0.05")
VOLUME_TOLERANCE_PERCENT = Decimal("0.005")
PILOT_SYMBOLS = ("RELIANCE", "TCS", "HDFCBANK", "INFY", "SUNPHARMA")

ROW_AUDIT_FIELDS = [
    "symbol",
    "groww_raw_timestamp",
    "raw_row_classification",
    "parsed_date",
    "nse_trading_day",
    "nse_has_symbol_record",
    "comparison_status",
    "notes",
]

SUMMARY_FIELDS = [
    "symbol",
    "nse_expected_sessions",
    "groww_valid_sessions",
    "groww_missing_sessions",
    "groww_incomplete_sessions",
    "non_trading_placeholders",
    "both_present_match",
    "both_present_mismatch",
    "nse_only_sessions",
    "groww_only_sessions",
    "completeness_percent",
    "final_status",
]


@dataclass(frozen=True, slots=True)
class AuditConfig:
    output_dir: Path
    start_date: date
    end_date: date
    request_delay_seconds: float = 0.5
    nse_request_delay_seconds: float = 0.1
    max_retries: int = 2
    timeout_seconds: int = 30
    price_tolerance: Decimal = PRICE_TOLERANCE
    volume_tolerance_percent: Decimal = VOLUME_TOLERANCE_PERCENT
    price_adjustment_status: str = PRICE_ADJUSTMENT_STATUS

    @property
    def audit_dir(self) -> Path:
        return self.output_dir / "reports" / "groww_nse_audit"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def nse_cache_dir(self) -> Path:
        return self.output_dir / "reference" / "nse" / "daily" / "raw"


@dataclass(frozen=True, slots=True)
class GrowwRawDailyRow:
    symbol: str
    groww_symbol: str
    raw_timestamp: str
    parsed_date: date | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
    raw: Any

    @property
    def has_valid_ohlcv(self) -> bool:
        return all(
            value is not None
            for value in (self.parsed_date, self.open, self.high, self.low, self.close, self.volume)
        )


@dataclass(slots=True)
class RowAuditRecord:
    symbol: str
    groww_raw_timestamp: str
    raw_row_classification: str
    parsed_date: str
    nse_trading_day: bool
    nse_has_symbol_record: bool
    comparison_status: str
    notes: str = ""


@dataclass(slots=True)
class DateComparison:
    symbol: str
    trading_date: date
    status: str
    price_abs_diff_max: Decimal = Decimal("0")
    price_pct_diff_max: Decimal = Decimal("0")
    volume_abs_diff: int = 0
    volume_pct_diff: Decimal = Decimal("0")
    notes: str = ""


@dataclass(slots=True)
class SymbolAuditSummary:
    symbol: str
    nse_expected_sessions: int
    groww_valid_sessions: int
    groww_missing_sessions: int
    groww_incomplete_sessions: int
    non_trading_placeholders: int
    both_present_match: int
    both_present_mismatch: int
    nse_only_sessions: int
    groww_only_sessions: int
    completeness_percent: str
    final_status: str


def parse_groww_raw_row(
    *,
    symbol: str,
    groww_symbol: str,
    row: Any,
) -> GrowwRawDailyRow:
    raw_timestamp = ""
    parsed_date: date | None = None
    open_: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None

    try:
        if isinstance(row, dict):
            raw_timestamp = str(row.get("timestamp") or row.get("time") or row.get("date") or "")
            raw_values = [
                raw_timestamp,
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
            ]
        else:
            raw_values = list(row[:6])
            raw_timestamp = str(raw_values[0])

        parsed_date = parse_groww_date(raw_values[0])
        open_ = optional_decimal(raw_values[1])
        high = optional_decimal(raw_values[2])
        low = optional_decimal(raw_values[3])
        close = optional_decimal(raw_values[4])
        volume = optional_int(raw_values[5])
    except (IndexError, TypeError, ValueError, InvalidOperation):
        pass

    return GrowwRawDailyRow(
        symbol=symbol,
        groww_symbol=groww_symbol,
        raw_timestamp=raw_timestamp,
        parsed_date=parsed_date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        raw=row,
    )


def classify_groww_row(
    row: GrowwRawDailyRow,
    *,
    is_duplicate: bool,
    nse_trading_day: bool,
) -> str:
    if is_duplicate:
        return "DUPLICATE"
    if row.parsed_date is None:
        return "INVALID_DATE"
    if not nse_trading_day and not row.has_valid_ohlcv:
        return "PLACEHOLDER"

    missing_prices = [
        value is None for value in (row.open, row.high, row.low, row.close)
    ]
    if any(missing_prices):
        return "MISSING_PRICE_FIELD"
    if row.volume is None:
        return "MISSING_VOLUME"
    if not row.has_valid_ohlcv:
        return "INCOMPLETE_OHLCV"
    return "VALID"


def compare_daily_values(
    groww: GrowwRawDailyRow,
    nse: NSEDailyRecord,
    *,
    price_tolerance: Decimal = PRICE_TOLERANCE,
    volume_tolerance_percent: Decimal = VOLUME_TOLERANCE_PERCENT,
) -> DateComparison:
    price_pairs = [
        (groww.open, nse.open),
        (groww.high, nse.high),
        (groww.low, nse.low),
        (groww.close, nse.close),
    ]
    price_abs_diffs = [abs((left or Decimal("0")) - right) for left, right in price_pairs]
    price_pct_diffs = [
        Decimal("0") if right == 0 else abs((left or Decimal("0")) - right) / right
        for left, right in price_pairs
    ]
    volume_abs_diff = abs((groww.volume or 0) - nse.volume)
    volume_pct_diff = (
        Decimal("0")
        if nse.volume == 0
        else Decimal(volume_abs_diff) / Decimal(nse.volume)
    )

    if max(price_abs_diffs) <= price_tolerance and volume_pct_diff <= volume_tolerance_percent:
        status = "BOTH_PRESENT_MATCH"
    else:
        status = "BOTH_PRESENT_VALUE_MISMATCH"

    return DateComparison(
        symbol=groww.symbol,
        trading_date=groww.parsed_date or nse.trading_date,
        status=status,
        price_abs_diff_max=max(price_abs_diffs),
        price_pct_diff_max=max(price_pct_diffs),
        volume_abs_diff=volume_abs_diff,
        volume_pct_diff=volume_pct_diff,
    )


async def fetch_groww_raw_daily_rows(
    mapping: GrowwInstrumentMapping,
    *,
    config: AuditConfig,
    auth_service: GrowwAuthService,
) -> list[GrowwRawDailyRow]:
    provider = GrowwHistoricalProvider(
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

    rows: list[GrowwRawDailyRow] = []
    for chunk_start, chunk_end in chunk_date_range(
        config.start_date,
        config.end_date,
        max_days=INTERVAL_LIMIT_DAYS["1d"],
    ):
        raw_rows = await provider.get_raw_daily_candles(start=chunk_start, end=chunk_end)
        rows.extend(
            parse_groww_raw_row(
                symbol=mapping.nse_symbol,
                groww_symbol=mapping.groww_symbol,
                row=row,
            )
            for row in raw_rows
        )
        if config.request_delay_seconds > 0:
            await asyncio.sleep(config.request_delay_seconds)
    return rows


def compare_symbol(
    *,
    symbol: str,
    groww_rows: Sequence[GrowwRawDailyRow],
    nse_sessions: dict[date, NSEDailySession],
    config: AuditConfig,
) -> tuple[SymbolAuditSummary, list[RowAuditRecord], list[DateComparison]]:
    trading_days = {
        trading_date
        for trading_date, session in nse_sessions.items()
        if session.is_trading_session
    }
    nse_symbol_days = {
        trading_date
        for trading_date, session in nse_sessions.items()
        if session.records.get(symbol)
    }

    row_audits: list[RowAuditRecord] = []
    raw_by_date: dict[date, list[tuple[GrowwRawDailyRow, str]]] = {}
    seen_dates: set[date] = set()

    for row in groww_rows:
        parsed = row.parsed_date
        duplicate = parsed in seen_dates if parsed else False
        if parsed:
            seen_dates.add(parsed)
        nse_trading_day = parsed in trading_days if parsed else False
        classification = classify_groww_row(
            row,
            is_duplicate=duplicate,
            nse_trading_day=nse_trading_day,
        )
        if parsed:
            raw_by_date.setdefault(parsed, []).append((row, classification))

        nse_has_symbol = parsed in nse_symbol_days if parsed else False
        comparison_status = comparison_status_for_raw_row(
            row,
            classification=classification,
            nse_trading_day=nse_trading_day,
            nse_has_symbol=nse_has_symbol,
        )
        row_audits.append(
            RowAuditRecord(
                symbol=symbol,
                groww_raw_timestamp=row.raw_timestamp,
                raw_row_classification=classification,
                parsed_date=parsed.isoformat() if parsed else "",
                nse_trading_day=nse_trading_day,
                nse_has_symbol_record=nse_has_symbol,
                comparison_status=comparison_status,
                notes=notes_for_raw_row(classification, nse_trading_day, nse_has_symbol),
            )
        )

    comparisons: list[DateComparison] = []
    for trading_date in sorted(trading_days):
        session = nse_sessions[trading_date]
        nse_record = session.records.get(symbol)
        dated_rows = raw_by_date.get(trading_date, [])
        valid_rows = [
            row for row, classification in dated_rows if classification == "VALID"
        ]
        incomplete_rows = [
            row for row, classification in dated_rows if classification not in {"VALID", "DUPLICATE"}
        ]

        if nse_record and valid_rows:
            comparisons.append(
                compare_daily_values(
                    valid_rows[0],
                    nse_record,
                    price_tolerance=config.price_tolerance,
                    volume_tolerance_percent=config.volume_tolerance_percent,
                )
            )
        elif nse_record and incomplete_rows:
            comparisons.append(
                DateComparison(
                    symbol=symbol,
                    trading_date=trading_date,
                    status="GROWW_INCOMPLETE",
                    notes="Groww row exists but is missing required OHLCV.",
                )
            )
        elif nse_record:
            comparisons.append(
                DateComparison(
                    symbol=symbol,
                    trading_date=trading_date,
                    status="GROWW_MISSING",
                    notes="NSE has a valid record but Groww returned no row.",
                )
            )
        elif dated_rows:
            comparisons.append(
                DateComparison(
                    symbol=symbol,
                    trading_date=trading_date,
                    status="NSE_MISSING",
                    notes="Groww returned a row but NSE has no symbol record.",
                )
            )

    groww_only_dates = [
        parsed_date
        for parsed_date in raw_by_date
        if parsed_date not in trading_days
    ]
    for parsed_date in sorted(groww_only_dates):
        comparisons.append(
            DateComparison(
                symbol=symbol,
                trading_date=parsed_date,
                status="NON_TRADING_DAY_PLACEHOLDER",
                notes="Groww row date is not an NSE trading session.",
            )
        )

    comparison_counts = Counter(comparison.status for comparison in comparisons)
    valid_sessions = comparison_counts["BOTH_PRESENT_MATCH"] + comparison_counts["BOTH_PRESENT_VALUE_MISMATCH"]
    expected_sessions = len(nse_symbol_days)
    incomplete_sessions = comparison_counts["GROWW_INCOMPLETE"]
    missing_sessions = comparison_counts["GROWW_MISSING"]
    completeness = Decimal("0")
    if expected_sessions:
        completeness = (Decimal(valid_sessions) / Decimal(expected_sessions)) * Decimal("100")

    final_status = (
        "COMPLETE"
        if expected_sessions and valid_sessions == expected_sessions and comparison_counts["BOTH_PRESENT_VALUE_MISMATCH"] == 0
        else "PARTIAL"
    )

    return (
        SymbolAuditSummary(
            symbol=symbol,
            nse_expected_sessions=expected_sessions,
            groww_valid_sessions=valid_sessions,
            groww_missing_sessions=missing_sessions,
            groww_incomplete_sessions=incomplete_sessions,
            non_trading_placeholders=comparison_counts["NON_TRADING_DAY_PLACEHOLDER"],
            both_present_match=comparison_counts["BOTH_PRESENT_MATCH"],
            both_present_mismatch=comparison_counts["BOTH_PRESENT_VALUE_MISMATCH"],
            nse_only_sessions=missing_sessions + incomplete_sessions,
            groww_only_sessions=comparison_counts["NON_TRADING_DAY_PLACEHOLDER"],
            completeness_percent=str(completeness.quantize(Decimal("0.01"))),
            final_status=final_status,
        ),
        row_audits,
        comparisons,
    )


def comparison_status_for_raw_row(
    row: GrowwRawDailyRow,
    *,
    classification: str,
    nse_trading_day: bool,
    nse_has_symbol: bool,
) -> str:
    if classification == "VALID" and nse_has_symbol:
        return "MATCH_PENDING_VALUE_CHECK"
    if classification == "VALID" and not nse_trading_day:
        return "NON_TRADING_DAY_PLACEHOLDER"
    if classification == "VALID":
        return "NSE_MISSING"
    if not nse_trading_day:
        return "NON_TRADING_DAY_PLACEHOLDER"
    if nse_has_symbol:
        return "GROWW_INCOMPLETE"
    return "OTHER"


def notes_for_raw_row(
    classification: str,
    nse_trading_day: bool,
    nse_has_symbol: bool,
) -> str:
    if classification == "MISSING_PRICE_FIELD" and nse_has_symbol:
        return "Groww row is missing at least one price field on an NSE trading day."
    if classification == "MISSING_VOLUME" and nse_has_symbol:
        return "Groww row is missing volume on an NSE trading day."
    if classification == "PLACEHOLDER":
        return "Groww row appears to be a non-trading-day placeholder."
    if classification == "VALID" and nse_has_symbol:
        return "Groww row is valid; values are checked in date comparison."
    return ""


def write_audit_outputs(
    *,
    summaries: Sequence[SymbolAuditSummary],
    row_audits_by_symbol: dict[str, list[RowAuditRecord]],
    comparisons_by_symbol: dict[str, list[DateComparison]],
    config: AuditConfig,
    source_metadata: dict[str, Any],
    markdown_path: Path,
) -> dict[str, Any]:
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)

    for symbol, row_audits in row_audits_by_symbol.items():
        write_csv(
            config.audit_dir / f"{symbol}_row_audit.csv",
            [asdict(row) for row in row_audits],
            ROW_AUDIT_FIELDS,
        )

    summary_csv_path = config.reports_dir / "groww_nse_daily_audit_summary.csv"
    summary_json_path = config.reports_dir / "groww_nse_daily_audit_summary.json"
    write_csv(summary_csv_path, [asdict(summary) for summary in summaries], SUMMARY_FIELDS)

    report = build_audit_report(
        summaries=summaries,
        row_audits_by_symbol=row_audits_by_symbol,
        comparisons_by_symbol=comparisons_by_symbol,
        config=config,
        source_metadata=source_metadata,
        summary_csv_path=summary_csv_path,
        summary_json_path=summary_json_path,
        markdown_path=markdown_path,
    )
    summary_json_path.write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_markdown_report(report), encoding="utf-8")
    return report


def build_audit_report(
    *,
    summaries: Sequence[SymbolAuditSummary],
    row_audits_by_symbol: dict[str, list[RowAuditRecord]],
    comparisons_by_symbol: dict[str, list[DateComparison]],
    config: AuditConfig,
    source_metadata: dict[str, Any],
    summary_csv_path: Path,
    summary_json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    all_comparisons = [
        comparison
        for comparisons in comparisons_by_symbol.values()
        for comparison in comparisons
    ]
    comparison_counts = Counter(comparison.status for comparison in all_comparisons)
    summary_counts = Counter(summary.final_status for summary in summaries)
    total_expected = sum(summary.nse_expected_sessions for summary in summaries)
    total_valid = sum(summary.groww_valid_sessions for summary in summaries)
    total_incomplete = sum(summary.groww_incomplete_sessions for summary in summaries)
    total_missing = sum(summary.groww_missing_sessions for summary in summaries)
    total_non_trading_placeholders = sum(summary.non_trading_placeholders for summary in summaries)
    total_mismatches = sum(summary.both_present_mismatch for summary in summaries)
    total_matches = sum(summary.both_present_match for summary in summaries)
    root_cause_breakdown = incomplete_root_cause_breakdown(row_audits_by_symbol)
    classification = decide_source_classification(
        expected_sessions=total_expected,
        incomplete_sessions=total_incomplete,
        missing_sessions=total_missing,
        mismatches=total_mismatches,
    )

    return {
        "phase": "Step 02.3C Fix",
        "task": "Groww vs NSE daily data audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pilot_symbols": [summary.symbol for summary in summaries],
        "date_range": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "sources": source_metadata,
        "expected_nse_sessions_per_symbol": summaries[0].nse_expected_sessions if summaries else 0,
        "totals": {
            "nse_expected_symbol_sessions": total_expected,
            "groww_valid_sessions": total_valid,
            "groww_incomplete_sessions": total_incomplete,
            "groww_missing_sessions": total_missing,
            "non_trading_placeholders": total_non_trading_placeholders,
            "both_present_match": total_matches,
            "both_present_mismatch": total_mismatches,
        },
        "incomplete_root_cause_breakdown": root_cause_breakdown,
        "comparison_counts": dict(comparison_counts),
        "symbol_status_counts": dict(summary_counts),
        "value_mismatch_stats": mismatch_stats(all_comparisons),
        "corporate_action_adjustment_status": infer_adjustment_status(total_mismatches),
        "final_classification": classification,
        "recommended_next_action": recommended_next_action(classification),
        "storage": {
            "row_audit_dir": str(config.audit_dir),
            "summary_csv": str(summary_csv_path),
            "summary_json": str(summary_json_path),
            "nse_cache_dir": str(config.nse_cache_dir),
            "markdown_report": str(markdown_path),
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
        },
        "symbols": [asdict(summary) for summary in summaries],
    }


def decide_source_classification(
    *,
    expected_sessions: int,
    incomplete_sessions: int,
    missing_sessions: int,
    mismatches: int,
) -> str:
    if expected_sessions == 0:
        return "D_INCONCLUSIVE"

    issue_ratio = Decimal(incomplete_sessions + missing_sessions) / Decimal(expected_sessions)
    mismatch_ratio = Decimal(mismatches) / Decimal(expected_sessions)
    if issue_ratio == 0 and mismatch_ratio <= Decimal("0.01"):
        return "A_SUFFICIENT_PRIMARY_SOURCE"
    if issue_ratio <= Decimal("0.02") and mismatch_ratio <= Decimal("0.02"):
        return "B_USABLE_WITH_NSE_VALIDATION"
    return "C_INSUFFICIENT_FOR_BACKTESTING"


def recommended_next_action(classification: str) -> str:
    if classification.startswith("A_"):
        return "Proceed with Groww bulk daily download."
    if classification.startswith("B_"):
        return "Use Groww plus official NSE validation/fill."
    if classification.startswith("C_"):
        return "Make official NSE daily history the primary source for backtesting."
    return "Investigate NSE reference retrieval before deciding."


def infer_adjustment_status(mismatches: int) -> str:
    if mismatches == 0:
        return "RAW_OR_ALIGNED_WITH_NSE_FOR_MATCHED_DATES"
    return "UNKNOWN"


def mismatch_stats(comparisons: Sequence[DateComparison]) -> dict[str, Any]:
    mismatches = [
        comparison
        for comparison in comparisons
        if comparison.status == "BOTH_PRESENT_VALUE_MISMATCH"
    ]
    if not mismatches:
        return {
            "count": 0,
            "max_price_abs_diff": "0",
            "max_price_pct_diff": "0",
            "max_volume_abs_diff": 0,
            "max_volume_pct_diff": "0",
        }

    return {
        "count": len(mismatches),
        "max_price_abs_diff": str(max(row.price_abs_diff_max for row in mismatches)),
        "max_price_pct_diff": str(max(row.price_pct_diff_max for row in mismatches)),
        "max_volume_abs_diff": max(row.volume_abs_diff for row in mismatches),
        "max_volume_pct_diff": str(max(row.volume_pct_diff for row in mismatches)),
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    sources = report["sources"]
    storage = report["storage"]
    value_stats = report["value_mismatch_stats"]
    root_cause = report["incomplete_root_cause_breakdown"]

    symbol_lines = []
    for symbol in report["symbols"]:
        symbol_lines.append(
            "- {symbol}: NSE expected {nse_expected_sessions}, Groww valid {groww_valid_sessions}, "
            "incomplete {groww_incomplete_sessions}, missing {groww_missing_sessions}, completeness {completeness_percent}%, status {final_status}".format(
                **symbol
            )
        )

    return "\n".join(
        [
            "# Groww vs NSE Daily Data Audit",
            "",
            "Current phase: Step 02.3C Fix - Groww missing/incomplete daily row diagnosis",
            "",
            "## Purpose",
            "",
            "Diagnose whether skipped Groww daily rows are harmless placeholders, official NSE non-trading days, genuine missing trading-session data, malformed provider responses, or another provider-format issue.",
            "",
            "## Sources",
            "",
            f"- Groww source: official Groww historical candles API via `growwapi`",
            f"- NSE source: {sources.get('nse_source')}",
            f"- NSE URL template: {sources.get('nse_url_template')}",
            f"- Nifty universe context: {NIFTY500_INDEX_NAME}",
            "",
            "## Scope",
            "",
            f"- Pilot symbols: {', '.join(report['pilot_symbols'])}",
            f"- Date range: {report['date_range']['start_date']} to {report['date_range']['end_date']}",
            f"- Expected NSE sessions per symbol: {report['expected_nse_sessions_per_symbol']}",
            "",
            "## Per-Symbol Completeness",
            "",
            *symbol_lines,
            "",
            "## Root Cause Totals",
            "",
            f"- NSE expected symbol-sessions: {totals['nse_expected_symbol_sessions']}",
            f"- Groww valid sessions: {totals['groww_valid_sessions']}",
            f"- Groww incomplete sessions on NSE trading days: {totals['groww_incomplete_sessions']}",
            f"- Groww missing sessions on NSE trading days: {totals['groww_missing_sessions']}",
            f"- Non-trading-day placeholders: {totals['non_trading_placeholders']}",
            f"- Incomplete rows inspected: {root_cause['incomplete_rows']}",
            f"- Incomplete rows on official NSE trading sessions: {root_cause['nse_trading_day_rows']}",
            f"- Incomplete rows with valid NSE symbol record: {root_cause['nse_has_symbol_record_rows']}",
            f"- Incomplete weekday rows: {root_cause['weekday_rows']}",
            f"- Incomplete weekend special-session rows: {root_cause['weekend_rows']}",
            f"- Unique incomplete dates: {root_cause['unique_incomplete_dates']}",
            f"- Incomplete date range: {root_cause['first_incomplete_date']} to {root_cause['last_incomplete_date']}",
            "",
            "## Value Comparison",
            "",
            f"- Both-present near matches: {totals['both_present_match']}",
            f"- Both-present mismatches: {totals['both_present_mismatch']}",
            f"- Mismatch count: {value_stats['count']}",
            f"- Max price absolute diff: {value_stats['max_price_abs_diff']}",
            f"- Max price pct diff: {value_stats['max_price_pct_diff']}",
            f"- Max volume absolute diff: {value_stats['max_volume_abs_diff']}",
            f"- Max volume pct diff: {value_stats['max_volume_pct_diff']}",
            "",
            "## Corporate Actions",
            "",
            f"- Adjustment conclusion: {report['corporate_action_adjustment_status']}",
            "- No corporate-action adjustment was implemented or applied.",
            "",
            "## Decision",
            "",
            f"- Final classification: {report['final_classification']}",
            f"- Recommended next action: {report['recommended_next_action']}",
            "",
            "## Storage",
            "",
            f"- Row audit directory: {storage['row_audit_dir']}",
            f"- Summary CSV: {storage['summary_csv']}",
            f"- Summary JSON: {storage['summary_json']}",
            f"- NSE cache directory: {storage['nse_cache_dir']}",
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


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def incomplete_root_cause_breakdown(
    row_audits_by_symbol: dict[str, list[RowAuditRecord]],
) -> dict[str, Any]:
    incomplete_rows = [
        row
        for rows in row_audits_by_symbol.values()
        for row in rows
        if row.raw_row_classification in {"MISSING_PRICE_FIELD", "MISSING_VOLUME", "INCOMPLETE_OHLCV"}
    ]
    incomplete_dates = [
        date.fromisoformat(row.parsed_date)
        for row in incomplete_rows
        if row.parsed_date
    ]
    return {
        "incomplete_rows": len(incomplete_rows),
        "nse_trading_day_rows": sum(1 for row in incomplete_rows if row.nse_trading_day),
        "nse_has_symbol_record_rows": sum(1 for row in incomplete_rows if row.nse_has_symbol_record),
        "weekday_rows": sum(1 for item in incomplete_dates if item.weekday() < 5),
        "weekend_rows": sum(1 for item in incomplete_dates if item.weekday() >= 5),
        "unique_incomplete_dates": len(set(incomplete_dates)),
        "first_incomplete_date": min(incomplete_dates).isoformat() if incomplete_dates else "",
        "last_incomplete_date": max(incomplete_dates).isoformat() if incomplete_dates else "",
    }


def parse_groww_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError("invalid Groww date")


def optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "null"}:
        return None
    return Decimal(text.replace(",", ""))


def optional_int(value: Any) -> int | None:
    decimal_value = optional_decimal(value)
    if decimal_value is None:
        return None
    return int(decimal_value)


def daily_candle_from_raw(row: GrowwRawDailyRow) -> DailyCandle:
    if not row.has_valid_ohlcv or row.parsed_date is None:
        raise ValueError("Groww row is not complete")
    return DailyCandle(
        exchange="NSE",
        trading_symbol=row.symbol,
        trading_date=row.parsed_date,
        open=row.open or Decimal("0"),
        high=row.high or Decimal("0"),
        low=row.low or Decimal("0"),
        close=row.close or Decimal("0"),
        volume=row.volume or 0,
        source="groww",
    )


def prototype_gap_fill(
    *,
    symbol: str,
    groww_rows: Sequence[GrowwRawDailyRow],
    nse_sessions: dict[date, NSEDailySession],
) -> list[dict[str, Any]]:
    valid_groww = {
        row.parsed_date: row
        for row in groww_rows
        if row.parsed_date is not None and row.has_valid_ohlcv
    }
    merged: list[dict[str, Any]] = []

    for trading_date, session in sorted(nse_sessions.items()):
        nse_record = session.records.get(symbol)
        if not nse_record:
            continue
        groww = valid_groww.get(trading_date)
        if groww:
            merged.append(
                {
                    "trading_date": trading_date.isoformat(),
                    "open": str(groww.open),
                    "high": str(groww.high),
                    "low": str(groww.low),
                    "close": str(groww.close),
                    "volume": groww.volume,
                    "source_origin": "GROWW",
                }
            )
            continue
        merged.append(
            {
                "trading_date": trading_date.isoformat(),
                "open": str(nse_record.open),
                "high": str(nse_record.high),
                "low": str(nse_record.low),
                "close": str(nse_record.close),
                "volume": nse_record.volume,
                "source_origin": "NSE_FILL",
            }
        )
    return merged


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
