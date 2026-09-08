from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.services.corporate_actions import (
    CONTINUITY_BREAK_ACTIONS,
    IDENTITY_ACTIONS,
    MANUAL_REVIEW_ACTIONS,
    PRICE_ADJUSTMENT_ACTIONS,
    fingerprint_directory,
)
from app.services.nifty500_membership import canonical_symbol


PRIORITY_FIELDS = [
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
    "membership_on_suspect_date",
    "membership_before_suspect_date",
    "membership_after_suspect_date",
    "membership_confidence",
    "priority",
    "root_cause_classification",
    "adjustment_status",
    "eligibility_status",
    "official_source",
    "confidence",
    "notes",
]

MANUAL_REVIEW_BREAKDOWN_FIELDS = [
    "symbol",
    "series",
    "start_date",
    "end_date",
    "row_count",
    "reason",
    "adjusted_status",
    "corporate_action_class",
    "historical_nifty500_relevance",
    "eq_rows",
    "special_series_rows",
]

RESEARCH_ELIGIBILITY_FIELDS = [
    "symbol",
    "isin",
    "start_date",
    "end_date",
    "eligibility_status",
    "reason_code",
    "source_event_id",
    "confidence",
    "notes",
]


@dataclass(frozen=True, slots=True)
class Nifty500CAReadinessConfig:
    output_dir: Path
    start_date: date
    end_date: date
    complex_event_window_days: int = 5
    unresolved_event_window_days: int = 5

    @property
    def corporate_action_dir(self) -> Path:
        return self.output_dir / "reference" / "nse" / "corporate_actions"

    @property
    def events_path(self) -> Path:
        return self.corporate_action_dir / "corporate_action_events.csv"

    @property
    def factors_path(self) -> Path:
        return self.corporate_action_dir / "adjustment_factors.csv"

    @property
    def suspect_reconciliation_path(self) -> Path:
        return self.output_dir / "reports" / "corporate_action_suspect_reconciliation.csv"

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.output_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def normalized_daily_dir(self) -> Path:
        return self.output_dir / "historical" / "daily" / "nse"

    @property
    def raw_daily_dir(self) -> Path:
        return self.output_dir / "raw" / "nse" / "daily"

    @property
    def membership_history_dir(self) -> Path:
        return self.output_dir / "reference" / "nifty500" / "history"

    @property
    def membership_periods_path(self) -> Path:
        return self.membership_history_dir / "membership_periods.csv"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def priority_csv_path(self) -> Path:
        return self.reports_dir / "nifty500_corporate_action_priority.csv"

    @property
    def priority_json_path(self) -> Path:
        return self.reports_dir / "nifty500_corporate_action_priority.json"

    @property
    def manual_review_breakdown_path(self) -> Path:
        return self.reports_dir / "nifty500_manual_review_breakdown.csv"

    @property
    def eligibility_path(self) -> Path:
        return self.corporate_action_dir / "research_eligibility.csv"

    @property
    def eligibility_summary_path(self) -> Path:
        return self.reports_dir / "nifty500_research_eligibility_summary.json"


@dataclass(frozen=True, slots=True)
class MembershipPeriod:
    symbol: str
    isin: str
    valid_from: date
    valid_to: date | None
    source_confidence: str


@dataclass(frozen=True, slots=True)
class CorporateActionRecord:
    event_id: str
    symbol: str
    isin: str
    action_type: str
    ex_date: date
    adjustment_method: str
    review_status: str
    adjustment_required: bool
    source_reference: str
    source_document: str


def build_nifty500_corporate_action_readiness(
    *,
    config: Nifty500CAReadinessConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    raw_before = fingerprint_directory(config.raw_daily_dir)
    normalized_before = fingerprint_directory(config.normalized_daily_dir)
    adjusted_before = fingerprint_directory(config.adjusted_daily_dir)

    membership_periods = load_membership_periods(config.membership_periods_path)
    corporate_events = load_corporate_action_events(config.events_path)
    events_by_symbol = group_events_by_symbol(corporate_events)
    unresolved_suspects = [
        row
        for row in read_csv(config.suspect_reconciliation_path)
        if row.get("explanation_status") == "UNRESOLVED"
    ]

    priority_rows = classify_unresolved_suspects(
        unresolved_suspects,
        membership_periods=membership_periods,
        events_by_symbol=events_by_symbol,
    )
    if progress:
        progress(f"Unresolved suspects classified: {len(priority_rows)}")

    manual_breakdown = build_manual_review_breakdown(
        adjusted_daily_dir=config.adjusted_daily_dir,
        membership_periods=membership_periods,
        events_by_symbol=events_by_symbol,
    )
    if progress:
        progress(f"Manual-review groups analyzed: {len(manual_breakdown)}")

    eligibility_rows = build_research_eligibility_intervals(
        membership_periods=membership_periods,
        priority_rows=priority_rows,
        events=corporate_events,
        complex_event_window_days=config.complex_event_window_days,
        unresolved_event_window_days=config.unresolved_event_window_days,
    )
    symbol_readiness = build_symbol_readiness(eligibility_rows)
    overall_status = overall_readiness_status(symbol_readiness)

    write_csv(config.priority_csv_path, priority_rows, PRIORITY_FIELDS)
    write_json(config.priority_json_path, {"generated_at": generated_at, "rows": priority_rows})
    write_csv(config.manual_review_breakdown_path, manual_breakdown, MANUAL_REVIEW_BREAKDOWN_FIELDS)
    write_csv(config.eligibility_path, eligibility_rows, RESEARCH_ELIGIBILITY_FIELDS)

    priority_counts = Counter(row["priority"] for row in priority_rows)
    classification_counts = Counter(row["root_cause_classification"] for row in priority_rows)
    relevance_counts = Counter(row["membership_on_suspect_date"] for row in priority_rows)
    manual_summary = summarize_manual_review(manual_breakdown)
    readiness_counts = Counter(row["readiness_status"] for row in symbol_readiness)
    eligibility_counts = Counter(row["eligibility_status"] for row in eligibility_rows)
    critical_unresolved_symbols = sorted(
        {
            row["symbol"]
            for row in priority_rows
            if row["priority"] == "P0_CRITICAL" and row["root_cause_classification"] in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}
        }
    )
    recommended_exclusions = [
        row
        for row in eligibility_rows
        if row["eligibility_status"] in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE", "MANUAL_REVIEW_REQUIRED"}
    ]

    raw_after = fingerprint_directory(config.raw_daily_dir)
    normalized_after = fingerprint_directory(config.normalized_daily_dir)
    adjusted_after = fingerprint_directory(config.adjusted_daily_dir)
    report = {
        "phase": "Step 02.3E-Fix",
        "task": "Nifty 500 corporate-action readiness prioritisation",
        "generated_at": generated_at,
        "date_coverage": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        },
        "unresolved_suspects": {
            "total": len(priority_rows),
            "priority_counts": dict(sorted(priority_counts.items())),
            "membership_relevance_counts": dict(sorted(relevance_counts.items())),
            "root_cause_counts": dict(sorted(classification_counts.items())),
            "nifty500_relevant_count": sum(
                1
                for row in priority_rows
                if row["membership_on_suspect_date"]
                in {"VERIFIED_NIFTY500_MEMBER", "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY"}
            ),
            "p0_resolved": sum(
                1
                for row in priority_rows
                if row["priority"] == "P0_CRITICAL"
                and row["root_cause_classification"] not in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}
            ),
            "p0_unresolved": sum(
                1
                for row in priority_rows
                if row["priority"] == "P0_CRITICAL" and row["root_cause_classification"] in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}
            ),
            "p1_resolved": sum(
                1
                for row in priority_rows
                if row["priority"] == "P1_HIGH"
                and row["root_cause_classification"] not in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}
            ),
            "p1_unresolved": sum(
                1
                for row in priority_rows
                if row["priority"] == "P1_HIGH" and row["root_cause_classification"] in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}
            ),
        },
        "manual_review": manual_summary,
        "research_eligibility": {
            "interval_count": len(eligibility_rows),
            "eligibility_counts": dict(sorted(eligibility_counts.items())),
            "path": str(config.eligibility_path),
        },
        "symbol_readiness": {
            "rows": symbol_readiness,
            "counts": dict(sorted(readiness_counts.items())),
            "critical_unresolved_symbols": critical_unresolved_symbols,
        },
        "overall_readiness": overall_status,
        "recommended_exclusions": recommended_exclusions,
        "methodology": {
            "new_adjustment_methodology_version": "",
            "adjusted_dataset_changed": adjusted_before != adjusted_after,
            "notes": "No PRICE_ADJUSTED_STRUCTURAL_V1 methodology change was made; this command adds eligibility metadata only.",
        },
        "integrity": {
            "raw_nse_unchanged": raw_before == raw_after,
            "normalized_raw_nse_unchanged": normalized_before == normalized_after,
            "adjusted_dataset_unchanged": adjusted_before == adjusted_after,
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
        },
        "outputs": {
            "priority_csv": str(config.priority_csv_path),
            "priority_json": str(config.priority_json_path),
            "manual_review_breakdown_csv": str(config.manual_review_breakdown_path),
            "research_eligibility_csv": str(config.eligibility_path),
            "eligibility_summary_json": str(config.eligibility_summary_path),
            "readiness_markdown": "docs/nifty500-corporate-action-readiness.md",
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_calculations_executed": 0,
        },
        "ready_for_review": raw_before == raw_after and normalized_before == normalized_after and adjusted_before == adjusted_after,
    }
    write_json(config.eligibility_summary_path, report)
    return report


def classify_unresolved_suspects(
    suspects: Sequence[dict[str, str]],
    *,
    membership_periods: Sequence[MembershipPeriod],
    events_by_symbol: dict[str, list[CorporateActionRecord]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suspect in suspects:
        symbol = canonical_symbol(suspect.get("symbol", ""))
        suspect_date = date.fromisoformat(suspect["suspect_date"])
        before_date = suspect_date - timedelta(days=1)
        after_date = suspect_date + timedelta(days=1)
        membership_on = membership_relevance(symbol, suspect_date, membership_periods)
        membership_before = membership_relevance(symbol, before_date, membership_periods)
        membership_after = membership_relevance(symbol, after_date, membership_periods)
        relevant = any(
            relevance in {"VERIFIED_NIFTY500_MEMBER", "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY"}
            for relevance in (membership_on, membership_before, membership_after)
        )
        classification, source, confidence, notes = classify_unresolved_root_cause(
            suspect=suspect,
            events=events_by_symbol.get(symbol, []),
        )
        priority = priority_for_suspect(
            suspect=suspect,
            membership_on=membership_on,
            membership_before=membership_before,
            membership_after=membership_after,
            classification=classification,
        )
        eligibility = eligibility_for_priority(priority=priority, classification=classification, relevant=relevant)
        rows.append(
            {
                "symbol": symbol,
                "series": suspect.get("series", ""),
                "isin": suspect.get("isin", ""),
                "suspect_date": suspect["suspect_date"],
                "previous_trading_date": suspect.get("previous_trading_date", ""),
                "previous_close": suspect.get("previous_close", ""),
                "current_open": suspect.get("current_open", ""),
                "current_close": suspect.get("current_close", ""),
                "raw_open_gap_percent": suspect.get("raw_open_gap_percent", ""),
                "raw_close_change_percent": suspect.get("raw_close_change_percent", ""),
                "membership_on_suspect_date": membership_on,
                "membership_before_suspect_date": membership_before,
                "membership_after_suspect_date": membership_after,
                "membership_confidence": membership_confidence(membership_on, membership_before, membership_after),
                "priority": priority,
                "root_cause_classification": classification,
                "adjustment_status": adjustment_status_for_classification(classification),
                "eligibility_status": eligibility,
                "official_source": source,
                "confidence": confidence,
                "notes": notes,
            }
        )
    return rows


def classify_unresolved_root_cause(
    *,
    suspect: dict[str, str],
    events: Sequence[CorporateActionRecord],
) -> tuple[str, str, str, str]:
    suspect_date = date.fromisoformat(suspect["suspect_date"])
    near_events = [
        event
        for event in events
        if abs((event.ex_date - suspect_date).days) <= 10
    ]
    if near_events:
        structural = [event for event in near_events if event.action_type in PRICE_ADJUSTMENT_ACTIONS]
        if structural:
            event = structural[0]
            if event.action_type == "STOCK_SPLIT":
                return "CONFIRMED_SPLIT", event.source_reference, "VERIFIED_OFFICIAL", "Official structural event found with wider date-window review."
            if event.action_type == "BONUS":
                return "CONFIRMED_BONUS", event.source_reference, "VERIFIED_OFFICIAL", "Official structural event found with wider date-window review."
            return "CONFIRMED_FACE_VALUE_CHANGE", event.source_reference, "VERIFIED_OFFICIAL", "Official structural event found with wider date-window review."
        complex_event = next((event for event in near_events if event.action_type in CONTINUITY_BREAK_ACTIONS), None)
        if complex_event:
            if complex_event.action_type == "DEMERGER":
                return "CONFIRMED_DEMERGER", complex_event.source_reference, "VERIFIED_OFFICIAL", "Official complex restructuring found near suspect date."
            if complex_event.action_type == "MERGER":
                return "CONFIRMED_MERGER", complex_event.source_reference, "VERIFIED_OFFICIAL", "Official merger/restructuring found near suspect date."
            return "IDENTITY_TRANSITION", complex_event.source_reference, "VERIFIED_OFFICIAL", "Official continuity-break event found near suspect date."
        rights_event = next((event for event in near_events if event.action_type == "RIGHTS"), None)
        if rights_event:
            return "CONFIRMED_RIGHTS", rights_event.source_reference, "VERIFIED_OFFICIAL", "Official rights issue found near suspect date; no TERP factor applied in current methodology."
        special_dividend = next((event for event in near_events if event.action_type == "SPECIAL_DIVIDEND"), None)
        if special_dividend:
            return "CONFIRMED_SPECIAL_DIVIDEND", special_dividend.source_reference, "VERIFIED_OFFICIAL", "Official special dividend found near suspect date."
        identity_event = next((event for event in near_events if event.action_type in IDENTITY_ACTIONS), None)
        if identity_event:
            return "CONFIRMED_SYMBOL_CHANGE", identity_event.source_reference, "VERIFIED_OFFICIAL", "Official identity event found near suspect date."
        return "NO_OFFICIAL_EVENT_FOUND", "", "MEDIUM", "Official corporate-action rows exist nearby, but not a supported structural/identity class."

    if suspect.get("series", "").upper() != "EQ":
        return "SERIES_TRANSITION", "", "HIGH", "Suspect is in a non-EQ series and outside Strategy V1 EQ research scope."

    previous = parse_decimal(suspect.get("previous_close", ""))
    current_open = parse_decimal(suspect.get("current_open", ""))
    current_close = parse_decimal(suspect.get("current_close", ""))
    if previous and current_open and current_close and min(current_open, current_close) <= previous <= max(current_open, current_close):
        return "NORMAL_MARKET_MOVE", "", "MEDIUM", "No official event found; previous close falls inside the current open/close range."
    return "NO_OFFICIAL_EVENT_FOUND", "", "MEDIUM", "No official event found within expanded official-source review window."


def priority_for_suspect(
    *,
    suspect: dict[str, str],
    membership_on: str,
    membership_before: str,
    membership_after: str,
    classification: str,
) -> str:
    series = suspect.get("series", "").upper()
    if series != "EQ":
        return "P3_IGNORE_FOR_V1"
    if classification in {"NORMAL_MARKET_MOVE", "SERIES_TRANSITION"}:
        return "P2_LOW"
    relevant = {
        membership_on,
        membership_before,
        membership_after,
    }
    if "VERIFIED_NIFTY500_MEMBER" in relevant:
        return "P0_CRITICAL"
    if "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY" in relevant or "UNKNOWN_IDENTITY" in relevant:
        return "P1_HIGH"
    return "P2_LOW"


def eligibility_for_priority(*, priority: str, classification: str, relevant: bool) -> str:
    if not relevant:
        return "OUTSIDE_NIFTY500_SCOPE"
    if classification in {"CONFIRMED_SPLIT", "CONFIRMED_BONUS", "CONFIRMED_FACE_VALUE_CHANGE", "NORMAL_MARKET_MOVE"}:
        return "RESEARCH_READY_WITH_WARNING"
    if classification in {"CONFIRMED_DEMERGER", "CONFIRMED_MERGER", "IDENTITY_TRANSITION"}:
        return "EXCLUDE_CORPORATE_ACTION_WINDOW"
    if classification in {"CONFIRMED_RIGHTS", "CONFIRMED_SPECIAL_DIVIDEND"}:
        return "MANUAL_REVIEW_REQUIRED"
    if priority in {"P0_CRITICAL", "P1_HIGH"}:
        return "MANUAL_REVIEW_REQUIRED"
    return "OUTSIDE_NIFTY500_SCOPE"


def adjustment_status_for_classification(classification: str) -> str:
    if classification in {"CONFIRMED_SPLIT", "CONFIRMED_BONUS", "CONFIRMED_FACE_VALUE_CHANGE"}:
        return "FACTOR_AVAILABLE"
    if classification in {"CONFIRMED_RIGHTS", "CONFIRMED_SPECIAL_DIVIDEND"}:
        return "ADJUSTMENT_REQUIRES_REVIEW"
    if classification in {"CONFIRMED_DEMERGER", "CONFIRMED_MERGER", "IDENTITY_TRANSITION"}:
        return "CONTINUITY_BREAK"
    if classification == "NORMAL_MARKET_MOVE":
        return "NO_ADJUSTMENT_NEEDED"
    return "UNRESOLVED"


def membership_relevance(
    symbol: str,
    as_of_date: date,
    membership_periods: Sequence[MembershipPeriod],
) -> str:
    normalized = canonical_symbol(symbol)
    matches = [
        period
        for period in membership_periods
        if period.symbol == normalized
        and period.valid_from <= as_of_date
        and (period.valid_to is None or as_of_date <= period.valid_to)
    ]
    if matches:
        if any(period.source_confidence == "OFFICIAL_EVENTS_PARTIAL" for period in matches):
            return "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY"
        return "VERIFIED_NIFTY500_MEMBER"
    if not normalized:
        return "UNKNOWN_IDENTITY"
    return "NOT_NIFTY500_MEMBER"


def membership_confidence(*values: str) -> str:
    if "VERIFIED_NIFTY500_MEMBER" in values:
        return "HIGH"
    if "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY" in values:
        return "MEDIUM"
    if "UNKNOWN_IDENTITY" in values:
        return "LOW"
    return "HIGH"


def build_manual_review_breakdown(
    *,
    adjusted_daily_dir: Path,
    membership_periods: Sequence[MembershipPeriod],
    events_by_symbol: dict[str, list[CorporateActionRecord]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for daily_path in adjusted_daily_files(adjusted_daily_dir):
        for row in read_adjusted_rows(daily_path):
            status = row.get("research_usability_status", "")
            if status not in {"MANUAL_REVIEW_REQUIRED", "CONTINUITY_BREAK", "RAW_ONLY"}:
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            series = row.get("series", "")
            trading_date = date.fromisoformat(row["trading_date"])
            relevance = membership_relevance(symbol, trading_date, membership_periods)
            reason, action_class = manual_review_reason(symbol=symbol, status=status, events_by_symbol=events_by_symbol)
            key = (symbol, series, status, reason)
            current = groups.setdefault(
                key,
                {
                    "symbol": symbol,
                    "series": series,
                    "start_date": trading_date,
                    "end_date": trading_date,
                    "row_count": 0,
                    "reason": reason,
                    "adjusted_status": status,
                    "corporate_action_class": action_class,
                    "historical_nifty500_relevance": relevance,
                    "eq_rows": 0,
                    "special_series_rows": 0,
                },
            )
            current["start_date"] = min(current["start_date"], trading_date)
            current["end_date"] = max(current["end_date"], trading_date)
            current["row_count"] += 1
            if series.upper() == "EQ":
                current["eq_rows"] += 1
            else:
                current["special_series_rows"] += 1
            if current["historical_nifty500_relevance"] == "NOT_NIFTY500_MEMBER" and relevance != "NOT_NIFTY500_MEMBER":
                current["historical_nifty500_relevance"] = relevance

    rows: list[dict[str, Any]] = []
    for item in groups.values():
        rows.append(
            {
                **item,
                "start_date": item["start_date"].isoformat(),
                "end_date": item["end_date"].isoformat(),
            }
        )
    return sorted(rows, key=lambda row: (row["historical_nifty500_relevance"], row["symbol"], row["series"], row["reason"]))


def manual_review_reason(
    *,
    symbol: str,
    status: str,
    events_by_symbol: dict[str, list[CorporateActionRecord]],
) -> tuple[str, str]:
    if status == "RAW_ONLY":
        return "special_series_or_non_eq", "SPECIAL_SERIES"
    action_types = {event.action_type for event in events_by_symbol.get(symbol, [])}
    if "RIGHTS" in action_types:
        return "rights_review_required", "RIGHTS"
    if "SPECIAL_DIVIDEND" in action_types:
        return "special_dividend_review_required", "SPECIAL_DIVIDEND"
    if action_types & CONTINUITY_BREAK_ACTIONS:
        return "complex_restructuring_continuity_break", "MERGER_DEMERGER"
    if action_types & MANUAL_REVIEW_ACTIONS:
        return "manual_review_event_class", "OTHER_COMPLEX"
    return "unresolved_manual_review_status", "UNRESOLVED"


def summarize_manual_review(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total_rows = sum(int(row["row_count"]) for row in rows)
    eq_rows = sum(int(row["eq_rows"]) for row in rows)
    special_rows = sum(int(row["special_series_rows"]) for row in rows)
    nifty_rows = sum(
        int(row["row_count"])
        for row in rows
        if row["historical_nifty500_relevance"] in {"VERIFIED_NIFTY500_MEMBER", "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY"}
    )
    reason_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts[row["reason"]] += int(row["row_count"])
        class_counts[row["corporate_action_class"]] += int(row["row_count"])
        status_counts[row["adjusted_status"]] += int(row["row_count"])
    return {
        "group_count": len(rows),
        "row_count": total_rows,
        "manual_review_required_rows": status_counts["MANUAL_REVIEW_REQUIRED"],
        "continuity_break_rows": status_counts["CONTINUITY_BREAK"],
        "raw_only_rows": status_counts["RAW_ONLY"],
        "nifty500_relevant_rows": nifty_rows,
        "non_nifty500_rows": total_rows - nifty_rows,
        "eq_rows": eq_rows,
        "special_series_rows": special_rows,
        "rights_rows": class_counts["RIGHTS"],
        "special_dividend_rows": class_counts["SPECIAL_DIVIDEND"],
        "merger_demerger_rows": class_counts["MERGER_DEMERGER"],
        "unresolved_rows": class_counts["UNRESOLVED"],
        "other_complex_rows": class_counts["OTHER_COMPLEX"],
        "reason_counts": dict(sorted(reason_counts.items())),
        "class_counts": dict(sorted(class_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
    }


def build_research_eligibility_intervals(
    *,
    membership_periods: Sequence[MembershipPeriod],
    priority_rows: Sequence[dict[str, Any]],
    events: Sequence[CorporateActionRecord],
    complex_event_window_days: int,
    unresolved_event_window_days: int,
) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    priority_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in priority_rows:
        priority_by_symbol[row["symbol"]].append(row)

    events_by_symbol = group_events_by_symbol(events)
    for period in membership_periods:
        intervals.append(
            {
                "symbol": period.symbol,
                "isin": period.isin,
                "start_date": period.valid_from.isoformat(),
                "end_date": period.valid_to.isoformat() if period.valid_to else "",
                "eligibility_status": "RESEARCH_READY",
                "reason_code": "nifty500_membership_period_default",
                "source_event_id": "",
                "confidence": period.source_confidence,
                "notes": "Default research eligibility for reconstructed Nifty 500 membership period.",
            }
        )
        for event in events_by_symbol.get(period.symbol, []):
            if event.action_type in CONTINUITY_BREAK_ACTIONS and date_ranges_overlap(
                period.valid_from,
                period.valid_to,
                event.ex_date - timedelta(days=complex_event_window_days),
                event.ex_date + timedelta(days=complex_event_window_days),
            ):
                intervals.append(
                    eligibility_window_row(
                        period=period,
                        event_date=event.ex_date,
                        window_days=complex_event_window_days,
                        status="EXCLUDE_CORPORATE_ACTION_WINDOW",
                        reason_code=f"complex_{event.action_type.lower()}",
                        source_event_id=event.event_id,
                        notes="Complex restructuring event; exclude configurable review window until successor/predecessor handling is approved.",
                    )
                )
            elif event.review_status in {"ADJUSTMENT_REQUIRES_REVIEW", "MANUAL_REVIEW_REQUIRED", "UNRESOLVED"} and date_ranges_overlap(
                period.valid_from,
                period.valid_to,
                event.ex_date - timedelta(days=unresolved_event_window_days),
                event.ex_date + timedelta(days=unresolved_event_window_days),
            ):
                intervals.append(
                    eligibility_window_row(
                        period=period,
                        event_date=event.ex_date,
                        window_days=unresolved_event_window_days,
                        status="MANUAL_REVIEW_REQUIRED",
                        reason_code=f"{event.action_type.lower()}_requires_review",
                        source_event_id=event.event_id,
                        notes="Official event is stored, but current methodology does not create a safe structural adjustment factor.",
                    )
                )
        for suspect in priority_by_symbol.get(period.symbol, []):
            if suspect["eligibility_status"] in {"MANUAL_REVIEW_REQUIRED", "EXCLUDE_CORPORATE_ACTION_WINDOW"}:
                suspect_date = date.fromisoformat(suspect["suspect_date"])
                if date_ranges_overlap(
                    period.valid_from,
                    period.valid_to,
                    suspect_date - timedelta(days=unresolved_event_window_days),
                    suspect_date + timedelta(days=unresolved_event_window_days),
                ):
                    intervals.append(
                        eligibility_window_row(
                            period=period,
                            event_date=suspect_date,
                            window_days=unresolved_event_window_days,
                            status=suspect["eligibility_status"],
                            reason_code="unresolved_structural_suspect",
                            source_event_id="",
                            notes=suspect["notes"],
                        )
                    )
    return sorted(intervals, key=lambda row: (row["symbol"], row["start_date"], row["eligibility_status"], row["reason_code"]))


def eligibility_window_row(
    *,
    period: MembershipPeriod,
    event_date: date,
    window_days: int,
    status: str,
    reason_code: str,
    source_event_id: str,
    notes: str,
) -> dict[str, Any]:
    start = max(period.valid_from, event_date - timedelta(days=window_days))
    end = event_date + timedelta(days=window_days)
    if period.valid_to is not None:
        end = min(end, period.valid_to)
    return {
        "symbol": period.symbol,
        "isin": period.isin,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "eligibility_status": status,
        "reason_code": reason_code,
        "source_event_id": source_event_id,
        "confidence": period.source_confidence,
        "notes": notes,
    }


def build_symbol_readiness(eligibility_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligibility_rows:
        grouped[row["symbol"]].append(row)
    rows: list[dict[str, Any]] = []
    for symbol, intervals in sorted(grouped.items()):
        statuses = {row["eligibility_status"] for row in intervals}
        if "MANUAL_REVIEW_REQUIRED" in statuses:
            readiness = "NOT_READY"
        elif statuses & {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE"}:
            readiness = "READY_WITH_EXCLUSIONS"
        else:
            readiness = "FULLY_READY"
        rows.append(
            {
                "symbol": symbol,
                "readiness_status": readiness,
                "interval_count": len(intervals),
                "exclusion_interval_count": sum(
                    1
                    for row in intervals
                    if row["eligibility_status"] in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE"}
                ),
                "manual_review_interval_count": sum(1 for row in intervals if row["eligibility_status"] == "MANUAL_REVIEW_REQUIRED"),
            }
        )
    return rows


def overall_readiness_status(symbol_rows: Sequence[dict[str, Any]]) -> str:
    readiness = {row["readiness_status"] for row in symbol_rows}
    if "NOT_READY" in readiness:
        return "NOT_READY"
    if "READY_WITH_EXCLUSIONS" in readiness:
        return "READY_WITH_EXCLUSIONS"
    return "READY"


def write_nifty500_readiness_markdown(report: dict[str, Any], path: Path) -> None:
    unresolved = report["unresolved_suspects"]
    manual = report["manual_review"]
    readiness = report["symbol_readiness"]
    eligibility = report["research_eligibility"]
    integrity = report["integrity"]
    priority_counts = unresolved["priority_counts"]
    lines = [
        "# Nifty 500 Corporate Action Readiness",
        "",
        "Current phase: Step 02.3E-Fix / Command 01 - Nifty 500 corporate-action readiness prioritisation",
        "",
        "## Recommendation",
        "",
        f"- Overall readiness: {report['overall_readiness']}",
        "- Membership survivorship status remains separate and is not upgraded by this report.",
        "- Strategy V1 can use the adjusted price layer only with the eligibility/exclusion metadata produced here.",
        "",
        "## Unresolved Suspect Priorities",
        "",
        f"- Total unresolved suspects: {unresolved['total']}",
        f"- Nifty 500-relevant unresolved suspects: {unresolved['nifty500_relevant_count']}",
        f"- P0_CRITICAL: {priority_counts.get('P0_CRITICAL', 0)}",
        f"- P1_HIGH: {priority_counts.get('P1_HIGH', 0)}",
        f"- P2_LOW: {priority_counts.get('P2_LOW', 0)}",
        f"- P3_IGNORE_FOR_V1: {priority_counts.get('P3_IGNORE_FOR_V1', 0)}",
        f"- P0 resolved/classified: {unresolved['p0_resolved']}",
        f"- P0 remaining without official resolution: {unresolved['p0_unresolved']}",
        f"- P1 resolved with official evidence: {unresolved['p1_resolved']}",
        f"- P1 remaining without official resolution: {unresolved['p1_unresolved']}",
        "",
        "## Root Causes",
        "",
    ]
    for key, value in sorted(unresolved["root_cause_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Manual Review Rows",
            "",
            f"- Manual-review/complex/special-series groups: {manual['group_count']}",
            f"- Total affected adjusted rows analyzed: {manual['row_count']}",
            f"- Nifty 500 relevant rows: {manual['nifty500_relevant_rows']}",
            f"- Non-Nifty rows: {manual['non_nifty500_rows']}",
            f"- EQ rows: {manual['eq_rows']}",
            f"- Special-series rows: {manual['special_series_rows']}",
            f"- Rights rows: {manual['rights_rows']}",
            f"- Special-dividend rows: {manual['special_dividend_rows']}",
            f"- Merger/demerger rows: {manual['merger_demerger_rows']}",
            f"- Unresolved manual-review rows: {manual['unresolved_rows']}",
            "",
            "## Research Eligibility",
            "",
            f"- Eligibility intervals created: {eligibility['interval_count']}",
            f"- Eligibility CSV: {eligibility['path']}",
        ]
    )
    for key, value in sorted(eligibility["eligibility_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Symbol-Level Readiness",
            "",
            f"- FULLY_READY: {readiness['counts'].get('FULLY_READY', 0)}",
            f"- READY_WITH_EXCLUSIONS: {readiness['counts'].get('READY_WITH_EXCLUSIONS', 0)}",
            f"- NOT_READY: {readiness['counts'].get('NOT_READY', 0)}",
            f"- Critical unresolved symbols: {', '.join(readiness['critical_unresolved_symbols']) if readiness['critical_unresolved_symbols'] else 'None'}",
            "",
            "## Integrity And Safety",
            "",
            f"- Raw NSE unchanged: {integrity['raw_nse_unchanged']}",
            f"- Normalized RAW unchanged: {integrity['normalized_raw_nse_unchanged']}",
            f"- Existing adjusted dataset unchanged: {integrity['adjusted_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy calculations were executed.",
            "",
            "## Known Limitations",
            "",
            "- The historical Nifty 500 membership layer remains PARTIAL_HISTORY.",
            "- P0/P1 official review uses currently normalized official NSE corporate-action rows; cases without matched official event remain conservative.",
            "- Rights, special dividends, mergers, and demergers remain policy-driven exclusions or manual-review metadata, not new adjustment factors.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def load_membership_periods(path: Path) -> list[MembershipPeriod]:
    rows: list[MembershipPeriod] = []
    for row in read_csv(path):
        valid_from = parse_date(row.get("valid_from", ""))
        if valid_from is None:
            continue
        rows.append(
            MembershipPeriod(
                symbol=canonical_symbol(row.get("symbol", "")),
                isin=row.get("isin", ""),
                valid_from=valid_from,
                valid_to=parse_date(row.get("valid_to", "")),
                source_confidence=row.get("source_confidence", ""),
            )
        )
    return rows


def load_corporate_action_events(path: Path) -> list[CorporateActionRecord]:
    rows: list[CorporateActionRecord] = []
    for row in read_csv(path):
        ex_date = parse_date(row.get("ex_date", ""))
        if ex_date is None:
            continue
        rows.append(
            CorporateActionRecord(
                event_id=row.get("event_id", ""),
                symbol=canonical_symbol(row.get("canonical_symbol") or row.get("symbol_at_event", "")),
                isin=row.get("isin", ""),
                action_type=row.get("action_type", ""),
                ex_date=ex_date,
                adjustment_method=row.get("adjustment_method", ""),
                review_status=row.get("review_status", ""),
                adjustment_required=str(row.get("adjustment_required", "")).lower() == "true",
                source_reference=row.get("source_reference", ""),
                source_document=row.get("source_document", ""),
            )
        )
    return rows


def group_events_by_symbol(events: Sequence[CorporateActionRecord]) -> dict[str, list[CorporateActionRecord]]:
    grouped: dict[str, list[CorporateActionRecord]] = defaultdict(list)
    for event in events:
        grouped[event.symbol].append(event)
    return grouped


def read_adjusted_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def adjusted_daily_files(adjusted_daily_dir: Path) -> list[Path]:
    if not adjusted_daily_dir.exists():
        return []
    return sorted(adjusted_daily_dir.glob("*/*/nse_adjusted_daily_*.csv"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


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


def parse_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def parse_decimal(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    return Decimal(text)


def date_ranges_overlap(start_a: date, end_a: date | None, start_b: date, end_b: date) -> bool:
    actual_end_a = end_a or date.max
    return start_a <= end_b and start_b <= actual_end_a


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
