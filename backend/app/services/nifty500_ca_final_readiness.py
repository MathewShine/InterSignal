from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.services.corporate_actions import fingerprint_directory
from app.services.nifty500_corporate_action_readiness import (
    CorporateActionRecord,
    MembershipPeriod,
    group_events_by_symbol,
    load_corporate_action_events,
    load_membership_periods,
    read_csv,
)
from app.services.nifty500_membership import canonical_symbol


EXCLUSION_POLICY_VERSION = "CORPORATE_ACTION_EXCLUSIONS_V1"
LOOKBACK_SCENARIOS = (0, 5, 20, 60)

FINAL_ELIGIBILITY_FIELDS = [
    "symbol",
    "isin",
    "start_date",
    "end_date",
    "eligibility_status",
    "reason_code",
    "source_event_id",
    "confidence",
    "policy_version",
    "lookback_contamination_supported",
    "notes",
]

NOT_READY_RESOLUTION_FIELDS = [
    "symbol",
    "isin",
    "historical_nifty500_start",
    "historical_nifty500_end",
    "reason_not_ready",
    "root_cause_category",
    "event_types",
    "affected_event_count",
    "affected_start_date",
    "affected_end_date",
    "current_eligibility_intervals",
    "raw_price_continuity_broken",
    "official_event_exists",
    "deterministic_adjustment_available",
    "exclusion_can_safely_solve",
    "final_symbol_status",
    "recommended_exclusion",
    "confidence",
    "notes",
]


@dataclass(frozen=True, slots=True)
class EventWindowPolicy:
    pre_days: int
    post_days: int
    status: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class ExclusionPolicy:
    version: str = EXCLUSION_POLICY_VERSION
    rights: EventWindowPolicy = EventWindowPolicy(3, 10, "EXCLUDE_CORPORATE_ACTION_WINDOW", "rights_exclusion_v1")
    special_dividend: EventWindowPolicy = EventWindowPolicy(1, 5, "EXCLUDE_CORPORATE_ACTION_WINDOW", "special_dividend_exclusion_v1")
    merger_demerger: EventWindowPolicy = EventWindowPolicy(5, 20, "EXCLUDE_CORPORATE_ACTION_WINDOW", "complex_restructuring_exclusion_v1")
    unresolved: EventWindowPolicy = EventWindowPolicy(3, 10, "EXCLUDE_SECURITY_RANGE", "unresolved_discontinuity_exclusion_v1")


@dataclass(frozen=True, slots=True)
class FinalReadinessConfig:
    output_dir: Path
    start_date: date
    end_date: date
    exclusion_policy: ExclusionPolicy = ExclusionPolicy()

    @property
    def corporate_action_dir(self) -> Path:
        return self.output_dir / "reference" / "nse" / "corporate_actions"

    @property
    def events_path(self) -> Path:
        return self.corporate_action_dir / "corporate_action_events.csv"

    @property
    def eligibility_path(self) -> Path:
        return self.corporate_action_dir / "research_eligibility.csv"

    @property
    def membership_periods_path(self) -> Path:
        return self.output_dir / "reference" / "nifty500" / "history" / "membership_periods.csv"

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
    def calendar_path(self) -> Path:
        return self.output_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"

    @property
    def previous_summary_path(self) -> Path:
        return self.output_dir / "reports" / "nifty500_research_eligibility_summary.json"

    @property
    def priority_path(self) -> Path:
        return self.output_dir / "reports" / "nifty500_corporate_action_priority.csv"

    @property
    def not_ready_resolution_path(self) -> Path:
        return self.output_dir / "reports" / "nifty500_not_ready_resolution.csv"

    @property
    def exclusion_impact_path(self) -> Path:
        return self.output_dir / "reports" / "nifty500_ca_exclusion_impact.json"


def build_final_nifty500_ca_readiness(*, config: FinalReadinessConfig) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    raw_before = fingerprint_directory(config.raw_daily_dir)
    normalized_before = fingerprint_directory(config.normalized_daily_dir)
    adjusted_before = fingerprint_directory(config.adjusted_daily_dir)

    membership_periods = load_membership_periods(config.membership_periods_path)
    corporate_events = load_corporate_action_events(config.events_path)
    old_eligibility_rows = read_csv(config.eligibility_path)
    priority_rows = read_csv(config.priority_path)
    previous_summary = json.loads(config.previous_summary_path.read_text(encoding="utf-8"))
    original_not_ready_symbols = sorted(
        row["symbol"]
        for row in previous_summary["symbol_readiness"]["rows"]
        if row["readiness_status"] == "NOT_READY"
    )

    updated_eligibility = build_final_eligibility_rows(
        old_eligibility_rows=old_eligibility_rows,
        priority_rows=priority_rows,
        events=corporate_events,
        policy=config.exclusion_policy,
    )
    resolution_rows = resolve_original_not_ready_symbols(
        original_not_ready_symbols=original_not_ready_symbols,
        membership_periods=membership_periods,
        priority_rows=priority_rows,
        old_eligibility_rows=old_eligibility_rows,
        updated_eligibility_rows=updated_eligibility,
        events=corporate_events,
    )
    symbol_readiness = final_symbol_readiness(
        previous_summary["symbol_readiness"]["rows"],
        resolution_rows,
    )
    impact = quantify_exclusion_impact(
        adjusted_daily_dir=config.adjusted_daily_dir,
        membership_periods=membership_periods,
        eligibility_rows=updated_eligibility,
        trading_sessions=load_trading_sessions(config.calendar_path),
        lookbacks=LOOKBACK_SCENARIOS,
    )

    write_csv(config.eligibility_path, updated_eligibility, FINAL_ELIGIBILITY_FIELDS)
    write_csv(config.not_ready_resolution_path, resolution_rows, NOT_READY_RESOLUTION_FIELDS)

    raw_after = fingerprint_directory(config.raw_daily_dir)
    normalized_after = fingerprint_directory(config.normalized_daily_dir)
    adjusted_after = fingerprint_directory(config.adjusted_daily_dir)
    readiness_counts = Counter(row["final_symbol_status"] for row in symbol_readiness)
    root_cause_counts = Counter(row["root_cause_category"] for row in resolution_rows)
    rights_rows = [row for row in resolution_rows if "RIGHTS" in row["root_cause_category"] or "RIGHTS" in row["event_types"]]
    special_rows = [row for row in resolution_rows if "SPECIAL_DIVIDEND" in row["root_cause_category"] or "SPECIAL_DIVIDEND" in row["event_types"]]
    merger_rows = [row for row in resolution_rows if "MERGER_DEMERGER" in row["root_cause_category"] or "DEMERGER" in row["event_types"]]
    infibeam = next((row for row in resolution_rows if row["symbol"] == "INFIBEAM"), {})
    infibeam_priority = next((row for row in priority_rows if row.get("symbol") == "INFIBEAM"), {})
    still_not_ready = sorted(row["symbol"] for row in resolution_rows if row["final_symbol_status"] == "NOT_READY")
    converted = sum(1 for row in resolution_rows if row["final_symbol_status"] == "READY_WITH_EXCLUSIONS")
    exclusion_intervals = [
        row for row in updated_eligibility if row["eligibility_status"] in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE"}
    ]

    report = {
        "phase": "Step 02.3E-Fix",
        "command": "Command 02",
        "generated_at": generated_at,
        "infibeam": {
            "symbol": "INFIBEAM",
            "suspect_date": infibeam_priority.get("suspect_date", ""),
            "classification": infibeam.get("root_cause_category", ""),
            "handling": "EXCLUDED" if infibeam else "",
            "adjusted": False,
            "official_evidence": [
                "Official NSE corporate-actions API returned no INFIBEAM row for March 2022 or all of 2022.",
                "Official NSE corporate-announcements API returned no INFIBEAM filings for March 2022 or all of 2022.",
            ],
            "notes": infibeam.get("notes", ""),
        },
        "original_not_ready_count": len(original_not_ready_symbols),
        "final_symbol_readiness": {
            "counts": dict(sorted(readiness_counts.items())),
            "rows": symbol_readiness,
            "converted_to_ready_with_exclusions": converted,
            "still_not_ready_count": len(still_not_ready),
            "still_not_ready_symbols": still_not_ready,
        },
        "root_cause_breakdown": dict(sorted(root_cause_counts.items())),
        "rights_cases": {
            "symbol_count": len(rights_rows),
            "symbols": sorted(row["symbol"] for row in rights_rows),
            "handling": "Finite exclusion windows; diagnostic TERP is deferred and not applied to PRICE_ADJUSTED_STRUCTURAL_V1.",
        },
        "special_dividend_cases": {
            "symbol_count": len(special_rows),
            "symbols": sorted(row["symbol"] for row in special_rows),
            "handling": "Finite exclusion windows; no total-return or structural price factor was created.",
        },
        "merger_demerger_cases": {
            "symbol_count": len(merger_rows),
            "symbols": sorted(row["symbol"] for row in merger_rows),
            "handling": "CONTINUITY_BREAK retained with finite exclusion windows.",
        },
        "exclusion_policy": policy_report(config.exclusion_policy),
        "exclusion_intervals": {
            "count": len(exclusion_intervals),
            "eligibility_csv": str(config.eligibility_path),
        },
        "lookback_aware_eligibility": {
            "service": "is_research_eligible(symbol, as_of_date, lookback_sessions=0, ...)",
            "supported": True,
            "policy": "A date is ineligible when the requested feature lookback window overlaps any exclusion interval.",
        },
        "observation_impact": impact,
        "overall_readiness": overall_final_readiness(readiness_counts),
        "feature_engine_may_start": overall_final_readiness(readiness_counts) in {"READY", "READY_WITH_EXCLUSIONS"},
        "methodology": {
            "new_adjustment_methodology_version": "",
            "price_adjusted_structural_v1_changed": False,
            "adjusted_dataset_changed": adjusted_before != adjusted_after,
            "exclusion_policy_version": config.exclusion_policy.version,
        },
        "integrity": {
            "raw_nse_unchanged": raw_before == raw_after,
            "normalized_raw_nse_unchanged": normalized_before == normalized_after,
            "adjusted_dataset_unchanged": adjusted_before == adjusted_after,
        },
        "outputs": {
            "not_ready_resolution_csv": str(config.not_ready_resolution_path),
            "exclusion_impact_json": str(config.exclusion_impact_path),
            "research_eligibility_csv": str(config.eligibility_path),
            "markdown": "docs/nifty500-corporate-action-final-readiness.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_calculations_executed": 0,
        },
        "ready_for_review": raw_before == raw_after and normalized_before == normalized_after and adjusted_before == adjusted_after,
    }
    write_json(config.exclusion_impact_path, report)
    return report


def build_final_eligibility_rows(
    *,
    old_eligibility_rows: Sequence[dict[str, str]],
    priority_rows: Sequence[dict[str, str]],
    events: Sequence[CorporateActionRecord],
    policy: ExclusionPolicy,
) -> list[dict[str, Any]]:
    events_by_id = {event.event_id: event for event in events}
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in old_eligibility_rows:
        if row["eligibility_status"] == "RESEARCH_READY":
            candidate = final_eligibility_row(row, row["eligibility_status"], row["reason_code"], policy.version, row.get("notes", ""))
        elif row_is_final_policy_exclusion(row, policy):
            candidate = final_eligibility_row(
                row,
                row["eligibility_status"],
                row["reason_code"],
                row.get("policy_version", policy.version),
                row.get("notes", ""),
            )
        else:
            event = events_by_id.get(row.get("source_event_id", ""))
            window = policy_for_row(row, event, policy)
            candidate = bounded_exclusion_row(row=row, event=event, window=window, policy_version=policy.version)
        key = interval_key(candidate)
        if key not in seen:
            output.append(candidate)
            seen.add(key)

    for priority_row in priority_rows:
        if priority_row.get("symbol") != "INFIBEAM":
            continue
        if priority_row.get("root_cause_classification") not in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}:
            continue
        if any(
            row["symbol"] == "INFIBEAM" and row["reason_code"] == policy.unresolved.reason_code
            for row in output
        ):
            continue
        suspect_date = date.fromisoformat(priority_row["suspect_date"])
        window = policy.unresolved
        candidate = {
            "symbol": "INFIBEAM",
            "isin": priority_row.get("isin", ""),
            "start_date": (suspect_date - timedelta(days=window.pre_days)).isoformat(),
            "end_date": (suspect_date + timedelta(days=window.post_days)).isoformat(),
            "eligibility_status": window.status,
            "reason_code": window.reason_code,
            "source_event_id": "",
            "confidence": priority_row.get("confidence", "MEDIUM"),
            "policy_version": policy.version,
            "lookback_contamination_supported": True,
            "notes": "INFIBEAM 2022-03-14 unresolved discontinuity: no official NSE corporate-action or announcement evidence found; finite exclusion bounds the suspect window without fabricating a factor.",
        }
        key = interval_key(candidate)
        if key not in seen:
            output.append(candidate)
            seen.add(key)
    return sorted(output, key=lambda item: (item["symbol"], item["start_date"], item["eligibility_status"], item["reason_code"]))


def row_is_final_policy_exclusion(row: dict[str, str], policy: ExclusionPolicy) -> bool:
    return (
        row.get("policy_version") == policy.version
        and row.get("eligibility_status") in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE"}
        and row.get("reason_code") in policy_reason_codes(policy)
    )


def policy_reason_codes(policy: ExclusionPolicy) -> set[str]:
    return {
        policy.rights.reason_code,
        policy.special_dividend.reason_code,
        policy.merger_demerger.reason_code,
        policy.unresolved.reason_code,
    }


def policy_for_row(row: dict[str, str], event: CorporateActionRecord | None, policy: ExclusionPolicy) -> EventWindowPolicy:
    reason = row.get("reason_code", "")
    action_type = event.action_type if event else ""
    if reason.startswith("rights") or action_type == "RIGHTS":
        return policy.rights
    if reason.startswith("special_dividend") or action_type == "SPECIAL_DIVIDEND":
        return policy.special_dividend
    if "demerger" in reason or "merger" in reason or action_type in {"DEMERGER", "MERGER", "SPINOFF", "CAPITAL_REDUCTION"}:
        return policy.merger_demerger
    if "unresolved" in reason:
        return policy.unresolved
    return policy.unresolved


def bounded_exclusion_row(
    *,
    row: dict[str, str],
    event: CorporateActionRecord | None,
    window: EventWindowPolicy,
    policy_version: str,
) -> dict[str, Any]:
    old_start = date.fromisoformat(row["start_date"])
    old_end = date.fromisoformat(row["end_date"]) if row.get("end_date") else old_start
    event_date = event.ex_date if event else old_start + (old_end - old_start) // 2
    start = event_date - timedelta(days=window.pre_days)
    end = event_date + timedelta(days=window.post_days)
    if event is None:
        start = min(start, old_start)
        end = max(end, old_end)
    return {
        "symbol": canonical_symbol(row["symbol"]),
        "isin": row.get("isin", ""),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "eligibility_status": window.status,
        "reason_code": window.reason_code,
        "source_event_id": row.get("source_event_id", ""),
        "confidence": row.get("confidence", "MEDIUM"),
        "policy_version": policy_version,
        "lookback_contamination_supported": True,
        "notes": row.get("notes", ""),
    }


def resolve_original_not_ready_symbols(
    *,
    original_not_ready_symbols: Sequence[str],
    membership_periods: Sequence[MembershipPeriod],
    priority_rows: Sequence[dict[str, str]],
    old_eligibility_rows: Sequence[dict[str, str]],
    updated_eligibility_rows: Sequence[dict[str, Any]],
    events: Sequence[CorporateActionRecord],
) -> list[dict[str, Any]]:
    events_by_id = {event.event_id: event for event in events}
    priority_by_symbol = defaultdict(list)
    for row in priority_rows:
        priority_by_symbol[canonical_symbol(row.get("symbol", ""))].append(row)
    old_by_symbol = rows_by_symbol(old_eligibility_rows)
    updated_by_symbol = rows_by_symbol(updated_eligibility_rows)
    rows: list[dict[str, Any]] = []
    for symbol in original_not_ready_symbols:
        symbol = canonical_symbol(symbol)
        old_rows = [
            row
            for row in old_by_symbol.get(symbol, [])
            if row.get("eligibility_status") in {"MANUAL_REVIEW_REQUIRED", "EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE"}
        ]
        updated_rows = [
            row
            for row in updated_by_symbol.get(symbol, [])
            if row.get("eligibility_status") in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE", "MANUAL_REVIEW_REQUIRED"}
        ]
        event_ids = sorted({row.get("source_event_id", "") for row in old_rows if row.get("source_event_id")})
        symbol_events = [events_by_id[event_id] for event_id in event_ids if event_id in events_by_id]
        root_cause = root_cause_category(symbol=symbol, rows=old_rows, events=symbol_events, priority_rows=priority_by_symbol.get(symbol, []))
        affected_start, affected_end = affected_date_range(old_rows, priority_by_symbol.get(symbol, []))
        final_status = "READY_WITH_EXCLUSIONS" if updated_rows and root_cause != "INSUFFICIENT_EVENT_DATA" else "NOT_READY"
        periods = [period for period in membership_periods if period.symbol == symbol]
        rows.append(
            {
                "symbol": symbol,
                "isin": next((period.isin for period in periods if period.isin), ""),
                "historical_nifty500_start": min((period.valid_from for period in periods), default=None),
                "historical_nifty500_end": max((period.valid_to or date.max for period in periods), default=None),
                "reason_not_ready": ";".join(sorted({row.get("reason_code", "") for row in old_rows})),
                "root_cause_category": root_cause,
                "event_types": ";".join(sorted({event.action_type for event in symbol_events})),
                "affected_event_count": len(event_ids) + sum(1 for row in priority_by_symbol.get(symbol, []) if row.get("root_cause_classification") in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}),
                "affected_start_date": affected_start,
                "affected_end_date": affected_end,
                "current_eligibility_intervals": len(old_rows),
                "raw_price_continuity_broken": raw_continuity_broken(root_cause, priority_by_symbol.get(symbol, [])),
                "official_event_exists": bool(event_ids),
                "deterministic_adjustment_available": False,
                "exclusion_can_safely_solve": final_status == "READY_WITH_EXCLUSIONS",
                "final_symbol_status": final_status,
                "recommended_exclusion": ";".join(sorted({row.get("reason_code", "") for row in updated_rows})),
                "confidence": "MEDIUM" if symbol == "INFIBEAM" else "HIGH",
                "notes": notes_for_resolution(symbol=symbol, root_cause=root_cause, priority_rows=priority_by_symbol.get(symbol, [])),
            }
        )
    return sorted(rows, key=lambda row: row["symbol"])


def final_symbol_readiness(
    previous_symbol_rows: Sequence[dict[str, Any]],
    resolution_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted = {row["symbol"]: row["final_symbol_status"] for row in resolution_rows}
    rows: list[dict[str, Any]] = []
    for row in previous_symbol_rows:
        symbol = row["symbol"]
        status = converted.get(symbol, row["readiness_status"])
        rows.append(
            {
                "symbol": symbol,
                "final_symbol_status": status,
                "previous_symbol_status": row["readiness_status"],
                "interval_count": row.get("interval_count", 0),
                "exclusion_interval_count": row.get("exclusion_interval_count", 0),
                "manual_review_interval_count": 0 if status == "READY_WITH_EXCLUSIONS" else row.get("manual_review_interval_count", 0),
            }
        )
    return sorted(rows, key=lambda item: item["symbol"])


def is_research_eligible(
    *,
    symbol: str,
    as_of_date: date,
    lookback_sessions: int = 0,
    eligibility_rows: Sequence[dict[str, Any]] | None = None,
    eligibility_path: Path | None = None,
    trading_sessions: Sequence[date] | None = None,
) -> dict[str, Any]:
    if eligibility_rows is None:
        if eligibility_path is None:
            raise ValueError("eligibility_rows or eligibility_path is required")
        eligibility_rows = read_csv(eligibility_path)
    normalized = canonical_symbol(symbol)
    window_start = lookback_start_date(as_of_date, lookback_sessions, trading_sessions or [])
    blockers = [
        row
        for row in eligibility_rows
        if canonical_symbol(str(row.get("symbol", ""))) == normalized
        and row.get("eligibility_status") in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE", "MANUAL_REVIEW_REQUIRED"}
        and intervals_overlap(
            window_start,
            as_of_date,
            date.fromisoformat(str(row["start_date"])),
            date.fromisoformat(str(row["end_date"])),
        )
    ]
    return {
        "eligible": not blockers,
        "status": "ELIGIBLE" if not blockers else "INELIGIBLE",
        "reason_codes": sorted({str(row.get("reason_code", "")) for row in blockers}),
        "blocking_events": sorted({str(row.get("source_event_id", "")) for row in blockers if row.get("source_event_id")}),
        "confidence": "HIGH" if not blockers else ",".join(sorted({str(row.get("confidence", "")) for row in blockers})),
        "lookback_start_date": window_start.isoformat(),
        "as_of_date": as_of_date.isoformat(),
    }


def quantify_exclusion_impact(
    *,
    adjusted_daily_dir: Path,
    membership_periods: Sequence[MembershipPeriod],
    eligibility_rows: Sequence[dict[str, Any]],
    trading_sessions: Sequence[date],
    lookbacks: Sequence[int],
) -> dict[str, Any]:
    membership_by_symbol = group_membership_periods(membership_periods)
    exclusion_by_symbol = group_exclusions(eligibility_rows)
    lookback_start_by_date = {
        lookback: {session: lookback_start_date(session, lookback, trading_sessions) for session in trading_sessions}
        for lookback in lookbacks
    }
    totals = {lookback: Counter() for lookback in lookbacks}
    entirely_unusable_symbols: set[str] = set()
    usable_with_exclusions: set[str] = set()
    symbols_seen: set[str] = set()
    symbol_totals: dict[str, Counter] = defaultdict(Counter)

    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None:
            continue
        for row in read_adjusted_rows(path):
            if row.get("series") != "EQ":
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            if not active_membership(symbol, trading_date, membership_by_symbol):
                continue
            symbols_seen.add(symbol)
            for lookback in lookbacks:
                start = lookback_start_by_date[lookback].get(trading_date, trading_date)
                excluded = any(
                    intervals_overlap(start, trading_date, interval[0], interval[1])
                    for interval in exclusion_by_symbol.get(symbol, [])
                )
                totals[lookback]["total"] += 1
                symbol_totals[symbol][f"total_{lookback}"] += 1
                if excluded:
                    totals[lookback]["excluded"] += 1
                    symbol_totals[symbol][f"excluded_{lookback}"] += 1
                else:
                    totals[lookback]["usable"] += 1
                    symbol_totals[symbol][f"usable_{lookback}"] += 1

    for symbol in symbols_seen:
        base_total = symbol_totals[symbol]["total_0"]
        base_usable = symbol_totals[symbol]["usable_0"]
        if base_total and base_usable == 0:
            entirely_unusable_symbols.add(symbol)
        elif symbol_totals[symbol]["excluded_0"] > 0:
            usable_with_exclusions.add(symbol)

    return {
        str(lookback): impact_row(totals[lookback])
        for lookback in lookbacks
    } | {
        "symbols": {
            "total": len(symbols_seen),
            "entirely_unusable": len(entirely_unusable_symbols),
            "usable_with_finite_exclusions": len(usable_with_exclusions),
        }
    }


def impact_row(counter: Counter[str]) -> dict[str, Any]:
    total = counter["total"]
    usable = counter["usable"]
    excluded = counter["excluded"]
    return {
        "total_observations": total,
        "usable_observations": usable,
        "excluded_observations": excluded,
        "usable_percent": str((Decimal(usable) / Decimal(total) * Decimal("100")).quantize(Decimal("0.0001"))) if total else "0",
    }


def write_final_readiness_markdown(report: dict[str, Any], path: Path) -> None:
    counts = report["final_symbol_readiness"]["counts"]
    impact = report["observation_impact"]
    lines = [
        "# Nifty 500 Corporate Action Final Readiness",
        "",
        "Current phase: Step 02.3E-Fix / Command 02 - final Nifty 500 corporate-action readiness",
        "",
        "## Final Status",
        "",
        f"- Corporate-action readiness: {report['overall_readiness']}",
        f"- Feature Engine may safely start: {report['feature_engine_may_start']}",
        "- Historical Nifty 500 membership remains PARTIAL_HISTORY and must travel as separate metadata.",
        "",
        "## INFIBEAM",
        "",
        f"- Classification: {report['infibeam']['classification']}",
        f"- Handling: {report['infibeam']['handling']}",
        f"- Adjusted: {report['infibeam']['adjusted']}",
        f"- Notes: {report['infibeam']['notes']}",
        "",
        "## Original NOT_READY Resolution",
        "",
        f"- Original NOT_READY symbols: {report['original_not_ready_count']}",
        f"- Converted to READY_WITH_EXCLUSIONS: {report['final_symbol_readiness']['converted_to_ready_with_exclusions']}",
        f"- Still NOT_READY: {report['final_symbol_readiness']['still_not_ready_count']}",
        f"- Still NOT_READY symbols: {', '.join(report['final_symbol_readiness']['still_not_ready_symbols']) if report['final_symbol_readiness']['still_not_ready_symbols'] else 'None'}",
        f"- FULLY_READY: {counts.get('FULLY_READY', 0)}",
        f"- READY_WITH_EXCLUSIONS: {counts.get('READY_WITH_EXCLUSIONS', 0)}",
        f"- NOT_READY: {counts.get('NOT_READY', 0)}",
        "",
        "## Root Causes",
        "",
    ]
    for key, value in report["root_cause_breakdown"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Event Handling",
            "",
            f"- Rights symbols: {report['rights_cases']['symbol_count']} - {report['rights_cases']['handling']}",
            f"- Special-dividend symbols: {report['special_dividend_cases']['symbol_count']} - {report['special_dividend_cases']['handling']}",
            f"- Merger/demerger symbols: {report['merger_demerger_cases']['symbol_count']} - {report['merger_demerger_cases']['handling']}",
            "",
            "## Exclusion Policy",
            "",
            f"- Version: {report['exclusion_policy']['version']}",
            f"- Exclusion intervals: {report['exclusion_intervals']['count']}",
            "- Lookback contamination is supported through `is_research_eligible(symbol, as_of_date, lookback_sessions)`.",
            "",
            "## Observation Impact",
            "",
            f"- Total historical Nifty 500 EQ observations: {impact['0']['total_observations']}",
            f"- Usable at 0-session lookback: {impact['0']['usable_observations']} ({impact['0']['usable_percent']}%)",
            f"- Excluded at 0-session lookback: {impact['0']['excluded_observations']}",
            f"- Usable at 5-session lookback: {impact['5']['usable_observations']} ({impact['5']['usable_percent']}%)",
            f"- Excluded at 5-session lookback: {impact['5']['excluded_observations']}",
            f"- Usable at 20-session lookback: {impact['20']['usable_observations']} ({impact['20']['usable_percent']}%)",
            f"- Excluded at 20-session lookback: {impact['20']['excluded_observations']}",
            f"- Usable at 60-session lookback: {impact['60']['usable_observations']} ({impact['60']['usable_percent']}%)",
            f"- Excluded at 60-session lookback: {impact['60']['excluded_observations']}",
            "",
            "## Integrity And Safety",
            "",
            f"- Raw NSE unchanged: {report['integrity']['raw_nse_unchanged']}",
            f"- Normalized RAW unchanged: {report['integrity']['normalized_raw_nse_unchanged']}",
            f"- Adjusted dataset unchanged: {report['integrity']['adjusted_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy calculations were executed.",
            "",
            "## Known Limitations",
            "",
            "- INFIBEAM remains without an official event match; it is bounded by exclusion, not adjusted.",
            "- Rights TERP diagnostics are not promoted into PRICE_ADJUSTED_STRUCTURAL_V1.",
            "- Special dividends remain exclusion metadata, not total-return adjustment.",
            "- Complex restructurings retain continuity-break treatment.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def root_cause_category(
    *,
    symbol: str,
    rows: Sequence[dict[str, str]],
    events: Sequence[CorporateActionRecord],
    priority_rows: Sequence[dict[str, str]],
) -> str:
    if symbol == "INFIBEAM":
        return "UNRESOLVED_DISCONTINUITY"
    categories: set[str] = set()
    event_types = {event.action_type for event in events}
    reason_codes = {row.get("reason_code", "") for row in rows}
    if "RIGHTS" in event_types or any("rights" in reason for reason in reason_codes):
        categories.add("RIGHTS")
    if "SPECIAL_DIVIDEND" in event_types or any("special_dividend" in reason for reason in reason_codes):
        categories.add("SPECIAL_DIVIDEND")
    if event_types & {"DEMERGER", "MERGER", "SPINOFF", "CAPITAL_REDUCTION"}:
        categories.add("MERGER_DEMERGER")
    if event_types & {"SYMBOL_CHANGE", "NAME_CHANGE"}:
        categories.add("IDENTITY_CHANGE")
    if any(row.get("root_cause_classification") in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"} for row in priority_rows):
        categories.add("UNRESOLVED_DISCONTINUITY")
    if len(categories) > 1:
        return "MULTIPLE_COMPLEX_ACTIONS"
    return next(iter(categories), "OTHER")


def affected_date_range(rows: Sequence[dict[str, str]], priority_rows: Sequence[dict[str, str]]) -> tuple[str, str]:
    starts: list[date] = []
    ends: list[date] = []
    for row in rows:
        starts.append(date.fromisoformat(row["start_date"]))
        ends.append(date.fromisoformat(row["end_date"]))
    for row in priority_rows:
        if row.get("root_cause_classification") in {"NO_OFFICIAL_EVENT_FOUND", "UNRESOLVED"}:
            suspect_date = date.fromisoformat(row["suspect_date"])
            starts.append(suspect_date)
            ends.append(suspect_date)
    if not starts:
        return "", ""
    return min(starts).isoformat(), max(ends).isoformat()


def raw_continuity_broken(root_cause: str, priority_rows: Sequence[dict[str, str]]) -> bool:
    if root_cause in {"MERGER_DEMERGER", "MULTIPLE_COMPLEX_ACTIONS", "UNRESOLVED_DISCONTINUITY"}:
        return True
    return any(abs(parse_percent(row.get("raw_close_change_percent", ""))) >= Decimal("35") for row in priority_rows)


def parse_percent(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


def notes_for_resolution(symbol: str, root_cause: str, priority_rows: Sequence[dict[str, str]]) -> str:
    if symbol == "INFIBEAM":
        return "INFIBEAM 2022-03-14 raw close gap was -51.9553%; official NSE corporate-action and announcement probes found no matching event, so no factor was created and a finite exclusion is used."
    if root_cause == "RIGHTS":
        return "Official rights event has finite dates; excluded rather than applying unversioned TERP adjustment."
    if root_cause == "SPECIAL_DIVIDEND":
        return "Official special dividend has finite dates; excluded rather than mixing total-return logic into structural adjustment."
    if root_cause == "MERGER_DEMERGER":
        return "Official complex restructuring has finite dates; continuity break is retained with exclusion metadata."
    if root_cause == "MULTIPLE_COMPLEX_ACTIONS":
        return "Multiple finite corporate-action review classes exist; exclusion metadata is used instead of a deterministic factor."
    if priority_rows:
        return priority_rows[0].get("notes", "")
    return "Finite exclusion metadata created from existing official/review intervals."


def rows_by_symbol(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[canonical_symbol(str(row.get("symbol", "")))].append(row)
    return grouped


def policy_report(policy: ExclusionPolicy) -> dict[str, Any]:
    return {
        "version": policy.version,
        "rights": policy_window_report(policy.rights),
        "special_dividend": policy_window_report(policy.special_dividend),
        "merger_demerger": policy_window_report(policy.merger_demerger),
        "unresolved": policy_window_report(policy.unresolved),
    }


def policy_window_report(window: EventWindowPolicy) -> dict[str, Any]:
    return {
        "pre_days": window.pre_days,
        "post_days": window.post_days,
        "status": window.status,
        "reason_code": window.reason_code,
    }


def overall_final_readiness(counts: Counter[str]) -> str:
    if counts.get("NOT_READY", 0):
        return "NOT_READY"
    if counts.get("READY_WITH_EXCLUSIONS", 0):
        return "READY_WITH_EXCLUSIONS"
    return "READY"


def interval_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("symbol", "")),
        str(row.get("start_date", "")),
        str(row.get("end_date", "")),
        str(row.get("eligibility_status", "")),
        str(row.get("reason_code", "")),
    )


def final_eligibility_row(
    row: dict[str, str],
    status: str,
    reason_code: str,
    policy_version: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "symbol": canonical_symbol(row["symbol"]),
        "isin": row.get("isin", ""),
        "start_date": row["start_date"],
        "end_date": row.get("end_date", ""),
        "eligibility_status": status,
        "reason_code": reason_code,
        "source_event_id": row.get("source_event_id", ""),
        "confidence": row.get("confidence", ""),
        "policy_version": policy_version,
        "lookback_contamination_supported": True,
        "notes": notes,
    }


def group_membership_periods(periods: Sequence[MembershipPeriod]) -> dict[str, list[MembershipPeriod]]:
    grouped: dict[str, list[MembershipPeriod]] = defaultdict(list)
    for period in periods:
        grouped[period.symbol].append(period)
    return grouped


def group_exclusions(rows: Sequence[dict[str, Any]]) -> dict[str, list[tuple[date, date]]]:
    grouped: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for row in rows:
        if row.get("eligibility_status") not in {"EXCLUDE_CORPORATE_ACTION_WINDOW", "EXCLUDE_SECURITY_RANGE", "MANUAL_REVIEW_REQUIRED"}:
            continue
        if not row.get("end_date"):
            continue
        grouped[canonical_symbol(str(row["symbol"]))].append(
            (date.fromisoformat(str(row["start_date"])), date.fromisoformat(str(row["end_date"])))
        )
    return grouped


def active_membership(symbol: str, as_of_date: date, grouped_periods: dict[str, list[MembershipPeriod]]) -> bool:
    return any(
        period.valid_from <= as_of_date and (period.valid_to is None or as_of_date <= period.valid_to)
        for period in grouped_periods.get(symbol, [])
    )


def lookback_start_date(as_of_date: date, lookback_sessions: int, trading_sessions: Sequence[date]) -> date:
    if lookback_sessions <= 0 or not trading_sessions:
        return as_of_date
    eligible_sessions = [session for session in trading_sessions if session <= as_of_date]
    if not eligible_sessions:
        return as_of_date
    index = max(0, len(eligible_sessions) - 1 - lookback_sessions)
    return eligible_sessions[index]


def intervals_overlap(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
    return start_a <= end_b and start_b <= end_a


def adjusted_daily_files(adjusted_daily_dir: Path) -> list[Path]:
    if not adjusted_daily_dir.exists():
        return []
    return sorted(adjusted_daily_dir.glob("*/*/nse_adjusted_daily_*.csv"))


def date_from_adjusted_path(path: Path) -> date | None:
    stem = path.stem.replace("nse_adjusted_daily_", "")
    try:
        return datetime.strptime(stem, "%Y%m%d").date()
    except ValueError:
        return None


def read_adjusted_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def load_trading_sessions(path: Path) -> list[date]:
    sessions: list[date] = []
    if not path.exists():
        return sessions
    for row in read_csv(path):
        if row.get("source_available") == "True":
            sessions.append(date.fromisoformat(row["trading_date"]))
    return sorted(sessions)


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
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return "" if value == date.max else value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value
