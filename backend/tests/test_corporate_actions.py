from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.services.corporate_actions import (
    CorporateActionConfig,
    adjusted_daily_path,
    bonus_price_factor,
    build_adjustment_factors,
    build_corporate_action_layer,
    build_pilot_adjustment_report,
    classify_action_type,
    cumulative_factor_for_date,
    event_raw_price_factor,
    fingerprint_directory,
    parse_face_value_change,
    parse_nse_corporate_actions_csv,
    parse_ratio,
    read_daily_file,
    reconcile_corporate_action_suspects,
    research_status_profile,
    research_usability_status,
    split_price_factor,
    write_adjusted_daily_dataset,
    write_corporate_actions_markdown_report,
    write_csv,
)


def test_split_ratio_parsing_from_face_value_terms():
    old_value, new_value = parse_face_value_change(
        "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share"
    )

    assert old_value == Decimal("10")
    assert new_value == Decimal("1")


def test_split_factor_calculation():
    assert split_price_factor(Decimal("10"), Decimal("2")) == Decimal("0.2")


def test_bonus_ratio_parsing():
    assert parse_ratio("Bonus 3:5") == (Decimal("3"), Decimal("5"))


def test_bonus_factor_calculation_examples():
    assert bonus_price_factor(Decimal("1"), Decimal("1")) == Decimal("0.5")
    assert bonus_price_factor(Decimal("1"), Decimal("2")) == Decimal("0.6666666666666666666666666667")
    assert bonus_price_factor(Decimal("2"), Decimal("1")) == Decimal("0.3333333333333333333333333333")
    assert bonus_price_factor(Decimal("3"), Decimal("5")) == Decimal("0.625")


def test_multiple_cumulative_factors():
    events = parse_nse_corporate_actions_csv(
        corporate_action_csv(
            [
                ["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "01-Jan-2022", "01-Jan-2022", "-", "-"],
                [
                    "ABC",
                    "ABC Limited",
                    "EQ",
                    "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share",
                    "10",
                    "01-Jan-2024",
                    "01-Jan-2024",
                    "-",
                    "-",
                ],
            ]
        ),
        source_path="official.csv",
        source_url="https://www.nseindia.com/api/corporates-corporateActions",
    )
    factors = build_adjustment_factors(events)

    factor, event_ids = cumulative_factor_for_date(factors, date(2021, 12, 31))

    assert factor == Decimal("0.25")
    assert len(event_ids) == 2


def test_ex_date_boundary_does_not_adjust_ex_date():
    events = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="https://www.nseindia.com/api/corporates-corporateActions",
    )
    factors = build_adjustment_factors(events)

    before_factor, _ = cumulative_factor_for_date(factors, date(2023, 12, 29))
    ex_factor, _ = cumulative_factor_for_date(factors, date(2024, 1, 1))
    after_factor, _ = cumulative_factor_for_date(factors, date(2024, 1, 2))

    assert before_factor == Decimal("0.5")
    assert ex_factor == Decimal("1")
    assert after_factor == Decimal("1")


def test_raw_price_immutability_and_adjusted_ohlc(tmp_path):
    normalized_dir = tmp_path / "data" / "historical" / "daily" / "nse"
    source_file = normalized_dir / "2024" / "01" / "nse_daily_20240101.csv"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        daily_csv(
            [
                ["2024-01-01", "NSE", "ABC", "EQ", "INEABC", "100", "110", "90", "100", "1000", "10", "RAW", "raw.csv", "legacy", "NORMAL_EQUITY", "RAW", "", "now"],
            ]
        ),
        encoding="utf-8",
    )
    before = source_file.read_text(encoding="utf-8")
    factor_event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "02-Jan-2024", "02-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]
    factors = build_adjustment_factors([factor_event])

    result = write_adjusted_daily_dataset(
        normalized_daily_dir=normalized_dir,
        adjusted_daily_dir=tmp_path / "data" / "research" / "adjusted" / "daily" / "nse",
        events=[factor_event],
        factors=factors,
        methodology_version="TEST_V1",
        adjusted_volume_enabled=True,
    )

    assert source_file.read_text(encoding="utf-8") == before
    adjusted_rows = list(csv.DictReader(adjusted_daily_path(tmp_path / "data" / "research" / "adjusted" / "daily" / "nse", date(2024, 1, 1)).open()))
    assert adjusted_rows[0]["raw_close"] == "100"
    assert adjusted_rows[0]["adjusted_close"] == "50"
    assert adjusted_rows[0]["adjusted_volume"] == "2000"
    assert result["record_count"] == 1


def test_ordinary_dividend_is_informational_only():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Dividend - Rs 10 Per Share", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    assert event.action_type == "DIVIDEND"
    assert event.adjustment_required is False
    assert event.adjustment_method == "INFORMATIONAL_ONLY"
    assert build_adjustment_factors([event]) == []


def test_special_dividend_requires_review():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv(
            [["ABC", "ABC Limited", "EQ", "Special Dividend - Rs 50 Per Share", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]
        ),
        source_path="official.csv",
        source_url="official",
    )[0]

    assert event.action_type == "SPECIAL_DIVIDEND"
    assert event.review_status == "MANUAL_REVIEW_REQUIRED"
    assert event.adjustment_required is False


def test_rights_issue_safe_handling():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Rights 21:20@ Premium Rs 25/-", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    assert event.action_type == "RIGHTS"
    assert event.review_status == "ADJUSTMENT_REQUIRES_REVIEW"
    assert event_raw_price_factor(event) is None


def test_merger_demerger_continuity_break():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Demerger", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    assert event.action_type == "DEMERGER"
    assert event.adjustment_method == "CONTINUITY_BREAK"
    assert event.review_status == "CONTINUITY_BREAK"


def test_symbol_and_name_change_are_identity_events():
    assert classify_action_type("Change in Name") == "NAME_CHANGE"
    assert classify_action_type("Symbol Change") == "SYMBOL_CHANGE"


def test_isin_mapping_is_used_for_canonical_instrument_id():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    replacement = replace(event, isin="INEABC")

    assert replacement.canonical_instrument_id == "INEABC"


def test_unresolved_event_handling():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    assert event.action_type == "UNKNOWN"
    assert event.review_status == "UNRESOLVED"


def test_factor_provenance_links_source_event_id():
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    factor = build_adjustment_factors([event])[0]

    assert factor.source_event_id == event.event_id
    assert factor.factor_confidence == "VERIFIED_OFFICIAL"


def test_raw_vs_adjusted_continuity_validation(tmp_path):
    normalized_dir = tmp_path / "data" / "historical" / "daily" / "nse"
    write_daily_partition(normalized_dir, date(2024, 1, 1), "ABC", close="200")
    write_daily_partition(normalized_dir, date(2024, 1, 2), "ABC", close="100")
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "02-Jan-2024", "02-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]
    factors = build_adjustment_factors([event])

    pilot = build_pilot_adjustment_report(
        normalized_daily_dir=normalized_dir,
        events=[event],
        factors=factors,
        suspect_rows=[],
        tolerance=Decimal("0.25"),
    )

    bonus_example = next(row for row in pilot["examples"] if row["pilot_type"] == "BONUS")
    assert bonus_example["raw_gap_percent"] == "-50"
    assert bonus_example["adjusted_gap_percent"] == "0"
    assert bonus_example["validation_status"] == "PASS"


def test_suspect_reconciliation_matches_official_event(tmp_path):
    normalized_dir = tmp_path / "data" / "historical" / "daily" / "nse"
    write_daily_partition(normalized_dir, date(2024, 1, 1), "ABC", close="200")
    write_daily_partition(normalized_dir, date(2024, 1, 2), "ABC", close="100", flags="CORPORATE_ACTION_SUSPECT")
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "02-Jan-2024", "02-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]

    rows = reconcile_corporate_action_suspects(
        normalized_daily_dir=normalized_dir,
        events=[event],
    )

    assert rows[0]["explanation_status"] == "CONFIRMED_CORPORATE_ACTION"
    assert rows[0]["official_event_found"] is True


def test_research_usability_statuses(tmp_path):
    event = parse_nse_corporate_actions_csv(
        corporate_action_csv([["ABC", "ABC Limited", "EQ", "Rights 1:2@ Premium Rs 5/-", "10", "01-Jan-2024", "01-Jan-2024", "-", "-"]]),
        source_path="official.csv",
        source_url="official",
    )[0]
    profile = research_status_profile([event])
    normalized_dir = tmp_path / "data" / "historical" / "daily" / "nse"
    write_daily_partition(normalized_dir, date(2024, 1, 1), "ABC")
    row = next(iter(read_daily_file(normalized_dir / "2024" / "01" / "nse_daily_20240101.csv")))

    assert research_usability_status(row=row, profile=profile["ABC"]) == "MANUAL_REVIEW_REQUIRED"


def test_report_generation_and_build_layer_with_mocked_network(monkeypatch, tmp_path):
    config = CorporateActionConfig(
        output_dir=tmp_path / "data",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        request_delay_seconds=0,
    )
    write_daily_partition(config.normalized_daily_dir, date(2024, 1, 1), "ABC", close="200")
    write_daily_partition(config.normalized_daily_dir, date(2024, 1, 2), "ABC", close="100", flags="CORPORATE_ACTION_SUSPECT")
    write_daily_partition(config.normalized_daily_dir, date(2024, 1, 1), "XYZ", close="50")
    write_daily_partition(config.normalized_daily_dir, date(2024, 1, 2), "XYZ", close="51")
    (config.raw_daily_dir / "2024" / "01").mkdir(parents=True)
    (config.raw_daily_dir / "2024" / "01" / "raw.csv").write_text("raw", encoding="utf-8")

    def fake_acquire(_config):
        return (
            corporate_action_csv([["ABC", "ABC Limited", "EQ", "Bonus 1:1", "10", "02-Jan-2024", "02-Jan-2024", "-", "-"]]).encode(),
            "official",
            200,
        )

    monkeypatch.setattr("app.services.corporate_actions.acquire_official_corporate_actions_csv", fake_acquire)

    before = fingerprint_directory(config.normalized_daily_dir)
    report = build_corporate_action_layer(config=config)
    write_corporate_actions_markdown_report(report, tmp_path / "docs" / "report.md")
    after = fingerprint_directory(config.normalized_daily_dir)

    assert before == after
    assert report["ready_for_review"] is True
    assert report["events"]["total"] == 1
    assert report["adjusted_dataset"]["record_count"] == 4
    assert (config.reference_dir / "corporate_action_events.csv").exists()
    assert (config.reports_dir / "corporate_action_summary.json").exists()
    assert json.loads((config.reports_dir / "corporate_action_summary.json").read_text())["safety"]["orders_placed"] == 0


def corporate_action_csv(rows):
    header = [
        "SYMBOL",
        "COMPANY NAME",
        "SERIES",
        "PURPOSE",
        "FACE VALUE",
        "EX-DATE",
        "RECORD DATE",
        "BOOK CLOSURE START DATE",
        "BOOK CLOSURE END DATE",
    ]
    output = [",".join(f'"{value}"' for value in header)]
    output.extend(",".join(f'"{value}"' for value in row) for row in rows)
    return "\n".join(output)


def daily_csv(rows):
    header = [
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
    output = [",".join(header)]
    output.extend(",".join(str(value) for value in row) for row in rows)
    return "\n".join(output)


def write_daily_partition(normalized_dir, trading_date, symbol, *, close="100", flags=""):
    path = normalized_dir / f"{trading_date:%Y}" / f"{trading_date:%m}" / f"nse_daily_{trading_date:%Y%m%d}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = list(csv.DictReader(path.open("r", encoding="utf-8"))) if path.exists() else []
    existing.append(
        {
            "trading_date": trading_date.isoformat(),
            "exchange": "NSE",
            "trading_symbol": symbol,
            "series": "EQ",
            "isin": "INEABC",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000,
            "traded_value": "10",
            "source": "official_nse_daily_bhavcopy",
            "source_file": "raw.csv",
            "source_format": "legacy",
            "series_classification": "NORMAL_EQUITY",
            "price_adjustment_status": "RAW",
            "quality_flags": flags,
            "normalized_at": "now",
        }
    )
    write_csv(
        path,
        existing,
        [
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
        ],
    )
