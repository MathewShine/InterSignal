from __future__ import annotations

import csv
import json
from datetime import date

from app.services.nifty500_corporate_action_readiness import (
    Nifty500CAReadinessConfig,
    build_manual_review_breakdown,
    build_nifty500_corporate_action_readiness,
    build_research_eligibility_intervals,
    build_symbol_readiness,
    classify_unresolved_suspects,
    load_corporate_action_events,
    load_membership_periods,
    membership_relevance,
    overall_readiness_status,
    write_nifty500_readiness_markdown,
)


def test_nifty500_relevance_classification(tmp_path):
    periods_path = tmp_path / "membership_periods.csv"
    write_membership_periods(periods_path, [("ABC", "2024-01-01", "2024-12-31", "OFFICIAL_EVENTS_PARTIAL")])
    periods = load_membership_periods(periods_path)

    assert membership_relevance("ABC", date(2024, 6, 1), periods) == "POSSIBLE_NIFTY500_MEMBER_DUE_TO_PARTIAL_HISTORY"
    assert membership_relevance("XYZ", date(2024, 6, 1), periods) == "NOT_NIFTY500_MEMBER"


def test_p0_p1_p2_p3_prioritisation(tmp_path):
    periods = load_membership_periods(
        write_membership_periods(
            tmp_path / "membership_periods.csv",
            [
                ("AAA", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL"),
                ("BBB", "2024-01-01", "2024-12-31", "OFFICIAL_EVENTS_PARTIAL"),
            ],
        )
    )
    events_by_symbol = {}

    rows = classify_unresolved_suspects(
        [
            suspect("AAA", "EQ", "2024-06-01"),
            suspect("BBB", "EQ", "2024-06-01"),
            suspect("CCC", "EQ", "2024-06-01"),
            suspect("DDD-RE", "BE", "2024-06-01"),
        ],
        membership_periods=periods,
        events_by_symbol=events_by_symbol,
    )

    priorities = {row["symbol"]: row["priority"] for row in rows}
    assert priorities["AAA"] == "P0_CRITICAL"
    assert priorities["BBB"] == "P1_HIGH"
    assert priorities["CCC"] == "P2_LOW"
    assert priorities["DDD-RE"] == "P3_IGNORE_FOR_V1"


def test_identity_transition_from_official_complex_event(tmp_path):
    periods = load_membership_periods(write_membership_periods(tmp_path / "membership_periods.csv", [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")]))
    event_path = write_ca_events(tmp_path / "corporate_action_events.csv", [ca_event("ABC", "2024-06-01", "DEMERGER")])
    events = load_corporate_action_events(event_path)
    rows = classify_unresolved_suspects(
        [suspect("ABC", "EQ", "2024-06-03")],
        membership_periods=periods,
        events_by_symbol={"ABC": events},
    )

    assert rows[0]["root_cause_classification"] == "CONFIRMED_DEMERGER"
    assert rows[0]["eligibility_status"] == "EXCLUDE_CORPORATE_ACTION_WINDOW"


def test_rights_review_handling(tmp_path):
    periods = load_membership_periods(write_membership_periods(tmp_path / "membership_periods.csv", [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")]))
    event_path = write_ca_events(tmp_path / "corporate_action_events.csv", [ca_event("ABC", "2024-06-01", "RIGHTS", review_status="ADJUSTMENT_REQUIRES_REVIEW")])
    events = load_corporate_action_events(event_path)

    rows = classify_unresolved_suspects(
        [suspect("ABC", "EQ", "2024-06-01")],
        membership_periods=periods,
        events_by_symbol={"ABC": events},
    )

    assert rows[0]["root_cause_classification"] == "CONFIRMED_RIGHTS"
    assert rows[0]["adjustment_status"] == "ADJUSTMENT_REQUIRES_REVIEW"


def test_complex_event_exclusion_metadata(tmp_path):
    periods = load_membership_periods(write_membership_periods(tmp_path / "membership_periods.csv", [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")]))
    events = load_corporate_action_events(write_ca_events(tmp_path / "corporate_action_events.csv", [ca_event("ABC", "2024-06-10", "DEMERGER")]))

    intervals = build_research_eligibility_intervals(
        membership_periods=periods,
        priority_rows=[],
        events=events,
        complex_event_window_days=5,
        unresolved_event_window_days=5,
    )

    exclusion = next(row for row in intervals if row["eligibility_status"] == "EXCLUDE_CORPORATE_ACTION_WINDOW")
    assert exclusion["start_date"] == "2024-06-05"
    assert exclusion["end_date"] == "2024-06-15"


def test_research_eligibility_intervals_for_unresolved_suspect(tmp_path):
    periods = load_membership_periods(write_membership_periods(tmp_path / "membership_periods.csv", [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")]))
    priority_rows = classify_unresolved_suspects(
        [suspect("ABC", "EQ", "2024-06-10")],
        membership_periods=periods,
        events_by_symbol={},
    )

    intervals = build_research_eligibility_intervals(
        membership_periods=periods,
        priority_rows=priority_rows,
        events=[],
        complex_event_window_days=5,
        unresolved_event_window_days=5,
    )

    assert any(row["reason_code"] == "unresolved_structural_suspect" for row in intervals)


def test_special_series_separation(tmp_path):
    adjusted_dir = tmp_path / "adjusted"
    write_adjusted_partition(adjusted_dir, "ABC", "EQ", "2024-01-01", "MANUAL_REVIEW_REQUIRED")
    write_adjusted_partition(adjusted_dir, "ABC-RE", "BE", "2024-01-01", "RAW_ONLY")
    periods = load_membership_periods(write_membership_periods(tmp_path / "membership_periods.csv", [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")]))

    breakdown = build_manual_review_breakdown(
        adjusted_daily_dir=adjusted_dir,
        membership_periods=periods,
        events_by_symbol={},
    )

    manual_group = next(row for row in breakdown if row["adjusted_status"] == "MANUAL_REVIEW_REQUIRED")
    special_group = next(row for row in breakdown if row["adjusted_status"] == "RAW_ONLY")
    assert manual_group["eq_rows"] == 1
    assert special_group["special_series_rows"] == 1


def test_symbol_level_and_final_statuses():
    fully_ready = build_symbol_readiness(
        [
            eligibility("ABC", "RESEARCH_READY"),
            eligibility("XYZ", "EXCLUDE_CORPORATE_ACTION_WINDOW"),
            eligibility("BAD", "MANUAL_REVIEW_REQUIRED"),
        ]
    )

    statuses = {row["symbol"]: row["readiness_status"] for row in fully_ready}
    assert statuses["ABC"] == "FULLY_READY"
    assert statuses["XYZ"] == "READY_WITH_EXCLUSIONS"
    assert statuses["BAD"] == "NOT_READY"
    assert overall_readiness_status(fully_ready) == "NOT_READY"
    assert overall_readiness_status([row for row in fully_ready if row["symbol"] != "BAD"]) == "READY_WITH_EXCLUSIONS"
    assert overall_readiness_status([row for row in fully_ready if row["symbol"] == "ABC"]) == "READY"


def test_build_readiness_report_does_not_mutate_raw_or_adjusted(tmp_path):
    config = Nifty500CAReadinessConfig(
        output_dir=tmp_path / "data",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
    )
    write_membership_periods(config.membership_periods_path, [("ABC", "2024-01-01", "2024-12-31", "VERIFIED_OFFICIAL")])
    write_ca_events(config.events_path, [ca_event("ABC", "2024-01-01", "RIGHTS", review_status="ADJUSTMENT_REQUIRES_REVIEW")])
    write_suspects(config.suspect_reconciliation_path, [suspect("ABC", "EQ", "2024-01-01")])
    write_adjusted_partition(config.adjusted_daily_dir, "ABC", "EQ", "2024-01-01", "MANUAL_REVIEW_REQUIRED")
    write_file(config.raw_daily_dir / "2024" / "01" / "raw.csv", "raw")
    write_file(config.normalized_daily_dir / "2024" / "01" / "nse_daily_20240101.csv", "normalized")
    before_adjusted = (config.adjusted_daily_dir / "2024" / "01" / "nse_adjusted_daily_20240101.csv").read_text(encoding="utf-8")

    report = build_nifty500_corporate_action_readiness(config=config)
    write_nifty500_readiness_markdown(report, tmp_path / "docs" / "readiness.md")

    assert (config.adjusted_daily_dir / "2024" / "01" / "nse_adjusted_daily_20240101.csv").read_text(encoding="utf-8") == before_adjusted
    assert report["integrity"]["raw_nse_unchanged"] is True
    assert report["integrity"]["adjusted_dataset_unchanged"] is True
    assert report["ready_for_review"] is True
    assert json.loads(config.eligibility_summary_path.read_text(encoding="utf-8"))["safety"]["orders_placed"] == 0


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
                "source_confidence": confidence,
                "provenance": "fixture",
            }
            for symbol, start, end, confidence in rows
        ],
        [
            "index_name",
            "symbol",
            "isin",
            "valid_from",
            "valid_to",
            "reconstruction_method",
            "source_confidence",
            "provenance",
        ],
    )
    return path


def write_ca_events(path, rows):
    write_csv(
        path,
        rows,
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


def write_suspects(path, rows):
    write_csv(
        path,
        rows,
        [
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
        ],
    )
    return path


def write_adjusted_partition(root, symbol, series, trading_date, status):
    parsed = date.fromisoformat(trading_date)
    path = root / f"{parsed:%Y}" / f"{parsed:%m}" / f"nse_adjusted_daily_{parsed:%Y%m%d}.csv"
    existing = list(csv.DictReader(path.open("r", encoding="utf-8"))) if path.exists() else []
    existing.append(
        {
            "trading_date": trading_date,
            "symbol": symbol,
            "isin": "",
            "series": series,
            "raw_open": "100",
            "raw_high": "100",
            "raw_low": "100",
            "raw_close": "100",
            "adjusted_open": "100",
            "adjusted_high": "100",
            "adjusted_low": "100",
            "adjusted_close": "100",
            "raw_volume": "1000",
            "adjusted_volume": "1000",
            "cumulative_adjustment_factor": "1",
            "adjustment_applied": "False",
            "adjustment_event_count": "0",
            "adjustment_methodology_version": "PRICE_ADJUSTED_STRUCTURAL_V1",
            "research_usability_status": status,
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
    return path


def suspect(symbol, series, suspect_date):
    return {
        "symbol": symbol,
        "series": series,
        "isin": "",
        "suspect_date": suspect_date,
        "previous_trading_date": "2024-05-31",
        "previous_close": "100",
        "current_open": "50",
        "current_close": "50",
        "raw_open_gap_percent": "-50",
        "raw_close_change_percent": "-50",
        "official_event_found": "False",
        "official_event_ids": "",
        "official_action_types": "",
        "official_ex_dates": "",
        "explanation_status": "UNRESOLVED",
        "notes": "fixture",
    }


def ca_event(symbol, ex_date, action_type, *, review_status="PARSED"):
    return {
        "event_id": f"event-{symbol}-{action_type}",
        "exchange": "NSE",
        "symbol_at_event": symbol,
        "canonical_symbol": symbol,
        "isin": "",
        "company_name": f"{symbol} Limited",
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
        "source_type": "official_nse_corporate_actions",
        "source_reference": "official",
        "source_document": "official.csv",
        "source_confidence": "VERIFIED_OFFICIAL",
        "adjustment_required": "False",
        "adjustment_method": "CONTINUITY_BREAK" if action_type == "DEMERGER" else "ADJUSTMENT_REQUIRES_REVIEW",
        "review_status": review_status,
        "notes": "fixture",
        "created_at": "now",
    }


def eligibility(symbol, status):
    return {
        "symbol": symbol,
        "isin": "",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "eligibility_status": status,
        "reason_code": "fixture",
        "source_event_id": "",
        "confidence": "HIGH",
        "notes": "fixture",
    }


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
