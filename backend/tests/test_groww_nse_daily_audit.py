from datetime import date
from decimal import Decimal

from app.providers.nse import NSEDailyRecord, NSEDailySession
from app.services.groww_nse_daily_audit import (
    AuditConfig,
    compare_daily_values,
    compare_symbol,
    parse_groww_raw_row,
    prototype_gap_fill,
    write_audit_outputs,
)


def test_groww_row_classification_detects_non_trading_placeholder(tmp_path):
    row = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-01-26T00:00:00", None, None, None, None, None, None],
    )
    summary, row_audits, _ = compare_symbol(
        symbol="RELIANCE",
        groww_rows=[row],
        nse_sessions={},
        config=AuditConfig(output_dir=tmp_path, start_date=date(2026, 1, 26), end_date=date(2026, 1, 26)),
    )

    assert row_audits[0].raw_row_classification == "PLACEHOLDER"
    assert summary.non_trading_placeholders == 1


def test_genuine_missing_session_detection(tmp_path):
    session = NSEDailySession(
        trading_date=date(2026, 9, 7),
        is_trading_session=True,
        records={"RELIANCE": nse_record("RELIANCE", date(2026, 9, 7))},
    )

    summary, _, comparisons = compare_symbol(
        symbol="RELIANCE",
        groww_rows=[],
        nse_sessions={date(2026, 9, 7): session},
        config=AuditConfig(output_dir=tmp_path, start_date=date(2026, 9, 7), end_date=date(2026, 9, 7)),
    )

    assert summary.groww_missing_sessions == 1
    assert comparisons[0].status == "GROWW_MISSING"


def test_incomplete_trading_day_detection(tmp_path):
    row = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-09-07T00:00:00", None, 105, 99, 104, 12345, None],
    )
    session = NSEDailySession(
        trading_date=date(2026, 9, 7),
        is_trading_session=True,
        records={"RELIANCE": nse_record("RELIANCE", date(2026, 9, 7))},
    )

    summary, row_audits, comparisons = compare_symbol(
        symbol="RELIANCE",
        groww_rows=[row],
        nse_sessions={date(2026, 9, 7): session},
        config=AuditConfig(output_dir=tmp_path, start_date=date(2026, 9, 7), end_date=date(2026, 9, 7)),
    )

    assert row_audits[0].raw_row_classification == "MISSING_PRICE_FIELD"
    assert summary.groww_incomplete_sessions == 1
    assert comparisons[0].status == "GROWW_INCOMPLETE"


def test_value_tolerance_allows_near_match():
    groww = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-09-07T00:00:00", "101.01", "105.00", "99.00", "104.00", 1001, None],
    )
    comparison = compare_daily_values(
        groww,
        nse_record("RELIANCE", date(2026, 9, 7), open_="101.00", volume=1000),
    )

    assert comparison.status == "BOTH_PRESENT_MATCH"


def test_value_mismatch_is_flagged():
    groww = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-09-07T00:00:00", "110.00", "115.00", "109.00", "114.00", 1000, None],
    )
    comparison = compare_daily_values(
        groww,
        nse_record("RELIANCE", date(2026, 9, 7)),
    )

    assert comparison.status == "BOTH_PRESENT_VALUE_MISMATCH"


def test_gap_fill_provenance_for_one_symbol():
    valid_groww = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-09-07T00:00:00", "101", "105", "99", "104", 12345, None],
    )
    sessions = {
        date(2026, 9, 7): NSEDailySession(
            trading_date=date(2026, 9, 7),
            is_trading_session=True,
            records={"RELIANCE": nse_record("RELIANCE", date(2026, 9, 7))},
        ),
        date(2026, 9, 8): NSEDailySession(
            trading_date=date(2026, 9, 8),
            is_trading_session=True,
            records={"RELIANCE": nse_record("RELIANCE", date(2026, 9, 8))},
        ),
    }

    merged = prototype_gap_fill(
        symbol="RELIANCE",
        groww_rows=[valid_groww],
        nse_sessions=sessions,
    )

    assert [row["source_origin"] for row in merged] == ["GROWW", "NSE_FILL"]


def test_audit_report_generation(tmp_path):
    row = parse_groww_raw_row(
        symbol="RELIANCE",
        groww_symbol="NSE-RELIANCE",
        row=["2026-09-07T00:00:00", "101", "105", "99", "104", 12345, None],
    )
    session = NSEDailySession(
        trading_date=date(2026, 9, 7),
        is_trading_session=True,
        records={"RELIANCE": nse_record("RELIANCE", date(2026, 9, 7))},
    )
    summary, row_audits, comparisons = compare_symbol(
        symbol="RELIANCE",
        groww_rows=[row],
        nse_sessions={date(2026, 9, 7): session},
        config=AuditConfig(output_dir=tmp_path, start_date=date(2026, 9, 7), end_date=date(2026, 9, 7)),
    )

    report = write_audit_outputs(
        summaries=[summary],
        row_audits_by_symbol={"RELIANCE": row_audits},
        comparisons_by_symbol={"RELIANCE": comparisons},
        config=AuditConfig(output_dir=tmp_path, start_date=date(2026, 9, 7), end_date=date(2026, 9, 7)),
        source_metadata={"nse_source": "fixture", "nse_url_template": "fixture"},
        markdown_path=tmp_path / "docs" / "audit.md",
    )

    assert (tmp_path / "reports" / "groww_nse_daily_audit_summary.csv").exists()
    assert (tmp_path / "reports" / "groww_nse_audit" / "RELIANCE_row_audit.csv").exists()
    assert report["final_classification"] == "A_SUFFICIENT_PRIMARY_SOURCE"


def nse_record(symbol, trading_date, *, open_="101.00", volume=12345):
    return NSEDailyRecord(
        trading_date=trading_date,
        symbol=symbol,
        series="EQ",
        isin="INE002A01018",
        open=Decimal(open_),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("104.00"),
        volume=volume,
        source_file="fixture",
        source_format="fixture",
    )
