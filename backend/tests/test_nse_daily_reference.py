import zipfile
from datetime import date
from pathlib import Path

from app.providers.nse.daily_reference import (
    NSEDailyReferenceProvider,
    parse_nse_daily_reference_csv,
    parse_nse_daily_reference_file,
)


LEGACY = """SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY
RELIANCE, EQ, 07-Sep-2026, 100, 101, 105, 99, 104, 104, 102, 12345
TCS, BE, 07-Sep-2026, 100, 101, 105, 99, 104, 104, 102, 12345
"""

UDIFF = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol
2026-09-07,2026-09-07,CM,NSE,STK,1,INE002A01018,RELIANCE,EQ,Reliance,101,105,99,104,12345
"""


def test_parse_legacy_nse_daily_csv():
    records = parse_nse_daily_reference_csv(
        LEGACY,
        source_file="fixture.csv",
        source_format="legacy_sec_bhavdata_full",
    )

    assert len(records) == 2
    assert records[0].symbol == "RELIANCE"
    assert records[0].trading_date == date(2026, 9, 7)
    assert records[0].volume == 12345
    assert records[1].symbol == "TCS"
    assert records[1].series == "BE"


def test_parse_udiff_zip_file(tmp_path):
    path = tmp_path / "udiff.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("BhavCopy.csv", UDIFF)

    records = parse_nse_daily_reference_file(path)

    assert len(records) == 1
    assert records[0].isin == "INE002A01018"
    assert records[0].source_format == "udiff_common_bhavcopy"


def test_parse_xlsx_bytes_served_from_csv_url(tmp_path):
    path = tmp_path / "sec_bhavdata_full_08082022.csv"
    write_minimal_xlsx(path)

    records = parse_nse_daily_reference_file(path)

    assert len(records) == 1
    assert records[0].symbol == "RELIANCE"
    assert records[0].close == 104


def test_trading_calendar_derives_from_available_nse_files(tmp_path):
    cache_dir = tmp_path / "raw"
    cache_dir.mkdir()
    (cache_dir / "sec_bhavdata_full_07092026.csv").write_text(LEGACY, encoding="utf-8")
    (cache_dir / "08092026.missing").write_text("missing", encoding="utf-8")
    provider = NSEDailyReferenceProvider(cache_dir=cache_dir, request_delay_seconds=0)

    sessions = provider.get_sessions(
        start=date(2026, 9, 7),
        end=date(2026, 9, 8),
        symbols=["RELIANCE"],
        progress_every=0,
    )

    assert sessions[date(2026, 9, 7)].is_trading_session is True
    assert sessions[date(2026, 9, 8)].is_trading_session is False


def test_trading_calendar_checks_weekend_special_sessions(tmp_path):
    cache_dir = tmp_path / "raw"
    cache_dir.mkdir()
    (cache_dir / "sec_bhavdata_full_01022025.csv").write_text(
        LEGACY.replace("07-Sep-2026", "01-Feb-2025"),
        encoding="utf-8",
    )
    provider = NSEDailyReferenceProvider(cache_dir=cache_dir, request_delay_seconds=0)

    sessions = provider.get_sessions(
        start=date(2025, 2, 1),
        end=date(2025, 2, 1),
        symbols=["RELIANCE"],
        progress_every=0,
    )

    assert date(2025, 2, 1).weekday() == 5
    assert sessions[date(2025, 2, 1)].is_trading_session is True


def test_trading_calendar_rejects_payload_with_wrong_internal_trade_date(tmp_path):
    cache_dir = tmp_path / "raw"
    cache_dir.mkdir()
    (cache_dir / "sec_bhavdata_full_02022025.csv").write_text(
        LEGACY.replace("07-Sep-2026", "01-Feb-2025"),
        encoding="utf-8",
    )
    provider = NSEDailyReferenceProvider(cache_dir=cache_dir, request_delay_seconds=0)

    sessions = provider.get_sessions(
        start=date(2025, 2, 2),
        end=date(2025, 2, 2),
        symbols=["RELIANCE"],
        progress_every=0,
    )

    assert sessions[date(2025, 2, 2)].is_trading_session is False


def write_minimal_xlsx(path: Path) -> None:
    shared_strings = [
        "SYMBOL",
        "SERIES",
        "DATE1",
        "OPEN_PRICE",
        "HIGH_PRICE",
        "LOW_PRICE",
        "CLOSE_PRICE",
        "TTL_TRD_QNTY",
        "RELIANCE",
        "EQ",
        "08-Aug-2022",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "")
        archive.writestr(
            "xl/sharedStrings.xml",
            "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            + "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
            + "</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
<row r="1">
<c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c><c r="G1" t="s"><v>6</v></c><c r="H1" t="s"><v>7</v></c>
</row>
<row r="2">
<c r="A2" t="s"><v>8</v></c><c r="B2" t="s"><v>9</v></c><c r="C2" t="s"><v>10</v></c><c r="D2"><v>101</v></c><c r="E2"><v>105</v></c><c r="F2"><v>99</v></c><c r="G2"><v>104</v></c><c r="H2"><v>12345</v></c>
</row>
</sheetData>
</worksheet>""",
        )
