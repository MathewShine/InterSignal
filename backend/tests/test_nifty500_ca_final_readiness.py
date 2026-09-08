from __future__ import annotations

import csv
import json
from datetime import date

from app.services.nifty500_ca_final_readiness import (
    EXCLUSION_POLICY_VERSION,
    FinalReadinessConfig,
    build_final_eligibility_rows,
    build_final_nifty500_ca_readiness,
    is_research_eligible,
    overall_final_readiness,
    quantify_exclusion_impact,
    resolve_original_not_ready_symbols,
    write_final_readiness_markdown,
)
from app.services.nifty500_corporate_action_readiness import (
    load_corporate_action_events,
    load_membership_periods,
)


def test_infibeam_resolution_is_bounded_exclusion_without_adjustment(tmp_path):
    old_rows = [
        ready("INFIBEAM", "2021-09-30", "2024-03-27"),
        exclusion("INFIBEAM", "2022-03-09", "2022-03-19", "MANUAL_REVIEW_REQUIRED", "unresolved_structural_suspect"),
    ]
    priority_rows = [priority("INFIBEAM", "2022-03-14")]

    final_rows = build_final_eligibility_rows(
        old_eligibility_rows=old_rows,
        priority_rows=priority_rows,
        events=[],
        policy=FinalReadinessConfig(tmp_path, date(2021, 9, 7), date(2026, 9, 7)).exclusion_policy,
    )
    resolution = resolve_original_not_ready_symbols(
        original_not_ready_symbols=["INFIBEAM"],
        membership_periods=[period("INFIBEAM", "2021-09-30", "2024-03-27")],
        priority_rows=priority_rows,
        old_eligibility_rows=old_rows,
        updated_eligibility_rows=final_rows,
        events=[],
    )[0]

    assert resolution["root_cause_category"] == "UNRESOLVED_DISCONTINUITY"
    assert resolution["final_symbol_status"] == "READY_WITH_EXCLUSIONS"
    assert resolution["deterministic_adjustment_available"] is False
    assert any(row["reason_code"] == "unresolved_discontinuity_exclusion_v1" for row in final_rows)


def test_rights_exclusion_uses_event_specific_boundary(tmp_path):
    event = ca_event("ABC", "2024-06-10", "RIGHTS", "event-rights")
    final_rows = build_final_eligibility_rows(
        old_eligibility_rows=[exclusion("ABC", "2024-06-05", "2024-06-15", "MANUAL_REVIEW_REQUIRED", "rights_requires_review", "event-rights")],
        priority_rows=[],
        events=[event],
        policy=FinalReadinessConfig(tmp_path, date(2021, 9, 7), date(2026, 9, 7)).exclusion_policy,
    )

    row = final_rows[0]
    assert row["start_date"] == "2024-06-07"
    assert row["end_date"] == "2024-06-20"
    assert row["reason_code"] == "rights_exclusion_v1"


def test_special_dividend_exclusion_uses_event_specific_boundary(tmp_path):
    event = ca_event("ABC", "2024-06-10", "SPECIAL_DIVIDEND", "event-special")
    final_rows = build_final_eligibility_rows(
        old_eligibility_rows=[exclusion("ABC", "2024-06-05", "2024-06-15", "MANUAL_REVIEW_REQUIRED", "special_dividend_requires_review", "event-special")],
        priority_rows=[],
        events=[event],
        policy=FinalReadinessConfig(tmp_path, date(2021, 9, 7), date(2026, 9, 7)).exclusion_policy,
    )

    row = final_rows[0]
    assert row["start_date"] == "2024-06-09"
    assert row["end_date"] == "2024-06-15"
    assert row["reason_code"] == "special_dividend_exclusion_v1"


def test_merger_demerger_continuity_break_gets_finite_window(tmp_path):
    event = ca_event("ABC", "2024-06-10", "DEMERGER", "event-demerge")
    final_rows = build_final_eligibility_rows(
        old_eligibility_rows=[exclusion("ABC", "2024-06-05", "2024-06-15", "EXCLUDE_CORPORATE_ACTION_WINDOW", "complex_demerger", "event-demerge")],
        priority_rows=[],
        events=[event],
        policy=FinalReadinessConfig(tmp_path, date(2021, 9, 7), date(2026, 9, 7)).exclusion_policy,
    )

    row = final_rows[0]
    assert row["start_date"] == "2024-06-05"
    assert row["end_date"] == "2024-06-30"
    assert row["reason_code"] == "complex_restructuring_exclusion_v1"


def test_is_research_eligible_blocks_lookback_contamination():
    rows = [
        ready("ABC", "2024-01-01", "2024-12-31"),
        {
            **exclusion("ABC", "2024-01-10", "2024-01-12", "EXCLUDE_CORPORATE_ACTION_WINDOW", "special_dividend_exclusion_v1"),
            "policy_version": EXCLUSION_POLICY_VERSION,
        },
    ]
    sessions = [date(2024, 1, day) for day in range(8, 17)]

    assert is_research_eligible(symbol="ABC", as_of_date=date(2024, 1, 16), eligibility_rows=rows, trading_sessions=sessions)["eligible"]
    blocked = is_research_eligible(
        symbol="ABC",
        as_of_date=date(2024, 1, 16),
        lookback_sessions=5,
        eligibility_rows=rows,
        trading_sessions=sessions,
    )

    assert blocked["eligible"] is False
    assert blocked["reason_codes"] == ["special_dividend_exclusion_v1"]


def test_membership_period_intersection_in_observation_impact(tmp_path):
    adjusted_dir = tmp_path / "adjusted"
    write_adjusted(adjusted_dir, "ABC", "2024-01-01")
    write_adjusted(adjusted_dir, "ABC", "2024-01-02")
    write_adjusted(adjusted_dir, "XYZ", "2024-01-01")

    impact = quantify_exclusion_impact(
        adjusted_daily_dir=adjusted_dir,
        membership_periods=[period("ABC", "2024-01-01", "2024-01-31")],
        eligibility_rows=[ready("ABC", "2024-01-01", "2024-01-31"), exclusion("ABC", "2024-01-02", "2024-01-02", "EXCLUDE_SECURITY_RANGE", "unresolved_discontinuity_exclusion_v1")],
        trading_sessions=[date(2024, 1, 1), date(2024, 1, 2)],
        lookbacks=(0,),
    )

    assert impact["0"]["total_observations"] == 2
    assert impact["0"]["excluded_observations"] == 1
    assert impact["symbols"]["total"] == 1


def test_final_readiness_aggregation():
    assert overall_final_readiness({"FULLY_READY": 2}) == "READY"
    assert overall_final_readiness({"FULLY_READY": 2, "READY_WITH_EXCLUSIONS": 1}) == "READY_WITH_EXCLUSIONS"
    assert overall_final_readiness({"NOT_READY": 1}) == "NOT_READY"


def test_build_final_report_does_not_mutate_adjusted_dataset(tmp_path):
    config = FinalReadinessConfig(tmp_path / "data", date(2021, 9, 7), date(2026, 9, 7))
    write_membership_periods(config.membership_periods_path, [("INFIBEAM", "2021-09-30", "2024-03-27")])
    write_events(config.events_path, [])
    write_priority(config.priority_path, [priority("INFIBEAM", "2022-03-14")])
    write_eligibility(
        config.eligibility_path,
        [
            ready("INFIBEAM", "2021-09-30", "2024-03-27"),
            exclusion("INFIBEAM", "2022-03-09", "2022-03-19", "MANUAL_REVIEW_REQUIRED", "unresolved_structural_suspect"),
        ],
    )
    write_previous_summary(config.previous_summary_path, ["INFIBEAM"])
    write_adjusted(config.adjusted_daily_dir, "INFIBEAM", "2022-03-14")
    write_calendar(config.calendar_path, ["2022-03-14"])
    write_file(config.raw_daily_dir / "2022" / "03" / "raw.csv", "raw")
    write_file(config.normalized_daily_dir / "2022" / "03" / "nse_daily_20220314.csv", "normalized")
    before_adjusted = (config.adjusted_daily_dir / "2022" / "03" / "nse_adjusted_daily_20220314.csv").read_text(encoding="utf-8")

    report = build_final_nifty500_ca_readiness(config=config)
    write_final_readiness_markdown(report, tmp_path / "docs" / "final.md")

    assert report["overall_readiness"] == "READY_WITH_EXCLUSIONS"
    assert report["integrity"]["adjusted_dataset_unchanged"] is True
    assert (config.adjusted_daily_dir / "2022" / "03" / "nse_adjusted_daily_20220314.csv").read_text(encoding="utf-8") == before_adjusted
    assert json.loads(config.exclusion_impact_path.read_text(encoding="utf-8"))["safety"]["orders_placed"] == 0


def period(symbol, start, end):
    return load_membership_periods(
        write_membership_periods(PathLikeTemp.path(), [(symbol, start, end)])
    )[0]


class PathLikeTemp:
    counter = 0

    @classmethod
    def path(cls):
        cls.counter += 1
        path = __import__("tempfile").gettempdir()
        return __import__("pathlib").Path(path) / f"intersignal_period_{cls.counter}.csv"


def ready(symbol, start, end):
    return {
        "symbol": symbol,
        "isin": "",
        "start_date": start,
        "end_date": end,
        "eligibility_status": "RESEARCH_READY",
        "reason_code": "default",
        "source_event_id": "",
        "confidence": "HIGH",
        "notes": "ready",
    }


def exclusion(symbol, start, end, status, reason, event_id=""):
    return {
        "symbol": symbol,
        "isin": "",
        "start_date": start,
        "end_date": end,
        "eligibility_status": status,
        "reason_code": reason,
        "source_event_id": event_id,
        "confidence": "HIGH",
        "notes": "exclude",
    }


def priority(symbol, suspect_date):
    return {
        "symbol": symbol,
        "series": "EQ",
        "isin": "",
        "suspect_date": suspect_date,
        "previous_trading_date": "2022-03-11",
        "previous_close": "44.75",
        "current_open": "21.5",
        "current_close": "21.5",
        "raw_open_gap_percent": "-51.9553",
        "raw_close_change_percent": "-51.9553",
        "membership_on_suspect_date": "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY",
        "membership_before_suspect_date": "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY",
        "membership_after_suspect_date": "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY",
        "membership_confidence": "MEDIUM",
        "priority": "P1_HIGH",
        "root_cause_classification": "NO_OFFICIAL_EVENT_FOUND",
        "adjustment_status": "UNRESOLVED",
        "eligibility_status": "MANUAL_REVIEW_REQUIRED",
        "official_source": "",
        "confidence": "MEDIUM",
        "notes": "No official event found.",
    }


def ca_event(symbol, ex_date, action_type, event_id):
    return load_corporate_action_events(
        write_events(PathLikeTemp.path(), [(symbol, ex_date, action_type, event_id)])
    )[0]


def write_membership_periods(path, rows):
    write_csv(
        path,
        [
            {
                "index_name": "NIFTY 500",
                "symbol": symbol,
                "isin": "",
                "valid_from": start,
                "valid_to": end,
                "reconstruction_method": "fixture",
                "source_confidence": "OFFICIAL_EVENTS_PARTIAL",
                "provenance": "fixture",
            }
            for symbol, start, end in rows
        ],
        ["index_name", "symbol", "isin", "valid_from", "valid_to", "reconstruction_method", "source_confidence", "provenance"],
    )
    return path


def write_events(path, rows):
    normalized = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(row)
            continue
        symbol, ex_date, action_type, event_id = row
        normalized.append(
            {
                "event_id": event_id,
                "exchange": "NSE",
                "symbol_at_event": symbol,
                "canonical_symbol": symbol,
                "isin": "",
                "company_name": symbol,
                "action_type": action_type,
                "announcement_date": "",
                "ex_date": ex_date,
                "record_date": ex_date,
                "effective_date": ex_date,
                "ratio_numerator": "",
                "ratio_denominator": "",
                "old_face_value": "",
                "new_face_value": "",
                "cash_amount": "",
                "currency": "",
                "source_type": "official",
                "source_reference": "official",
                "source_document": "official.csv",
                "source_confidence": "VERIFIED_OFFICIAL",
                "adjustment_required": "False",
                "adjustment_method": "CONTINUITY_BREAK",
                "review_status": "CONTINUITY_BREAK",
                "notes": "fixture",
                "created_at": "now",
            }
        )
    write_csv(
        path,
        normalized,
        [
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
        ],
    )
    return path


def write_priority(path, rows):
    fields = [
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
    write_csv(path, rows, fields)


def write_eligibility(path, rows):
    write_csv(path, rows, ["symbol", "isin", "start_date", "end_date", "eligibility_status", "reason_code", "source_event_id", "confidence", "notes"])


def write_previous_summary(path, not_ready_symbols):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"symbol": symbol, "readiness_status": "NOT_READY", "interval_count": 2, "exclusion_interval_count": 0, "manual_review_interval_count": 1} for symbol in not_ready_symbols]
    path.write_text(json.dumps({"symbol_readiness": {"rows": rows}}), encoding="utf-8")


def write_adjusted(root, symbol, trading_date):
    parsed = date.fromisoformat(trading_date)
    path = root / f"{parsed:%Y}" / f"{parsed:%m}" / f"nse_adjusted_daily_{parsed:%Y%m%d}.csv"
    existing = list(csv.DictReader(path.open("r", encoding="utf-8"))) if path.exists() else []
    existing.append(
        {
            "trading_date": trading_date,
            "symbol": symbol,
            "isin": "",
            "series": "EQ",
            "raw_open": "1",
            "raw_high": "1",
            "raw_low": "1",
            "raw_close": "1",
            "adjusted_open": "1",
            "adjusted_high": "1",
            "adjusted_low": "1",
            "adjusted_close": "1",
            "raw_volume": "1",
            "adjusted_volume": "1",
            "cumulative_adjustment_factor": "1",
            "adjustment_applied": "False",
            "adjustment_event_count": "0",
            "adjustment_methodology_version": "PRICE_ADJUSTED_STRUCTURAL_V1",
            "research_usability_status": "ADJUSTED_READY",
            "source": "fixture",
            "provenance": "",
        }
    )
    write_csv(
        path,
        existing,
        [
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
        ],
    )


def write_calendar(path, dates):
    write_csv(
        path,
        [{"trading_date": item, "session_type": "NORMAL", "source_reference": "fixture", "source_available": "True", "notes": ""} for item in dates],
        ["trading_date", "session_type", "source_reference", "source_available", "notes"],
    )


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
