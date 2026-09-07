from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.etree import ElementTree


@dataclass(frozen=True, slots=True)
class NSEDailyRecord:
    trading_date: date
    symbol: str
    series: str
    isin: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_file: str
    source_format: str
    traded_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NSEDailySession:
    trading_date: date
    is_trading_session: bool
    records: dict[str, NSEDailyRecord]
    source_file: str = ""
    source_format: str = ""
    error: str = ""


class NSEDailyReferenceProvider:
    legacy_url_template = (
        "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
    )
    udiff_url_template = (
        "https://nsearchives.nseindia.com/content/cm/"
        "BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
    )

    def __init__(
        self,
        *,
        cache_dir: str | Path,
        timeout_seconds: int = 30,
        request_delay_seconds: float = 0.1,
        force_refresh: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.force_refresh = force_refresh

    def get_sessions(
        self,
        *,
        start: date,
        end: date,
        symbols: Sequence[str],
        progress_every: int = 100,
    ) -> dict[date, NSEDailySession]:
        sessions: dict[date, NSEDailySession] = {}
        calendar_dates = list(dates_in_range(start, end))
        wanted_symbols = {symbol.strip().upper() for symbol in symbols}

        for index, trading_date in enumerate(calendar_dates, start=1):
            sessions[trading_date] = self.get_session(
                trading_date,
                symbols=wanted_symbols,
            )
            if progress_every and index % progress_every == 0:
                print(f"NSE daily files checked: {index}/{len(calendar_dates)}", flush=True)

        return sessions

    def get_session(
        self,
        trading_date: date,
        *,
        symbols: Iterable[str],
    ) -> NSEDailySession:
        source = self.get_or_download_daily_file(trading_date)
        if source is None:
            return NSEDailySession(
                trading_date=trading_date,
                is_trading_session=False,
                records={},
                error="NSE daily file unavailable",
            )

        records = parse_nse_daily_reference_file(source)
        date_records = [
            record for record in records if record.trading_date == trading_date
        ]
        filtered = {
            record.symbol: record
            for record in date_records
            if record.symbol in symbols and record.series == "EQ"
        }
        return NSEDailySession(
            trading_date=trading_date,
            is_trading_session=bool(date_records),
            records=filtered,
            source_file=str(source),
            source_format=date_records[0].source_format if date_records else "",
        )

    def get_or_download_daily_file(self, trading_date: date) -> Path | None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        missing_marker = self.cache_dir / f"{trading_date.isoformat()}.missing"
        if missing_marker.exists() and not self.force_refresh:
            return None

        for candidate in self._cache_candidates(trading_date):
            if candidate.exists() and not self.force_refresh:
                return candidate

        for source_format, url, output_path in self._download_candidates(trading_date):
            try:
                content = self._download(url)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                continue
            except (urllib.error.URLError, TimeoutError, OSError):
                continue

            output_path.write_bytes(content)
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            return output_path

        missing_marker.write_text("missing", encoding="utf-8")
        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)
        return None

    def _download(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/csv,application/zip,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read()

    def _cache_candidates(self, trading_date: date) -> list[Path]:
        ddmmyyyy = trading_date.strftime("%d%m%Y")
        yyyymmdd = trading_date.strftime("%Y%m%d")
        return [
            self.cache_dir / f"sec_bhavdata_full_{ddmmyyyy}.csv",
            self.cache_dir / f"BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip",
        ]

    def _download_candidates(self, trading_date: date) -> list[tuple[str, str, Path]]:
        ddmmyyyy = trading_date.strftime("%d%m%Y")
        yyyymmdd = trading_date.strftime("%Y%m%d")
        return [
            (
                "legacy_sec_bhavdata_full",
                self.legacy_url_template.format(ddmmyyyy=ddmmyyyy),
                self.cache_dir / f"sec_bhavdata_full_{ddmmyyyy}.csv",
            ),
            (
                "udiff_common_bhavcopy",
                self.udiff_url_template.format(yyyymmdd=yyyymmdd),
                self.cache_dir / f"BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip",
            ),
        ]


def parse_nse_daily_reference_file(path: str | Path) -> list[NSEDailyRecord]:
    source_path = Path(path)
    raw_bytes = source_path.read_bytes()
    if source_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            csv_members = [
                member
                for member in archive.namelist()
                if member.lower().endswith(".csv") and not member.endswith("/")
            ]
            if not csv_members:
                return []
            raw_csv = archive.read(csv_members[0]).decode("utf-8-sig", errors="replace")
        return parse_nse_daily_reference_csv(
            raw_csv,
            source_file=str(source_path),
            source_format="udiff_common_bhavcopy",
        )

    if raw_bytes.startswith(b"PK"):
        raw_csv = xlsx_bytes_to_csv(raw_bytes)
    else:
        raw_csv = raw_bytes.decode("utf-8-sig", errors="replace")
    return parse_nse_daily_reference_csv(
        raw_csv,
        source_file=str(source_path),
        source_format="legacy_sec_bhavdata_full",
    )


def parse_nse_daily_reference_csv(
    raw_csv: str,
    *,
    source_file: str = "",
    source_format: str = "",
) -> list[NSEDailyRecord]:
    reader = csv.DictReader(io.StringIO(raw_csv.lstrip("\ufeff")))
    fieldnames = {clean_header(name) for name in (reader.fieldnames or [])}

    if {"SYMBOL", "SERIES", "DATE1", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"} <= fieldnames:
        return parse_legacy_rows(reader, source_file=source_file)
    if {"TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"} <= fieldnames:
        return parse_udiff_rows(reader, source_file=source_file)
    raise ValueError("Unsupported NSE daily reference format")


def parse_legacy_rows(
    reader: csv.DictReader,
    *,
    source_file: str,
) -> list[NSEDailyRecord]:
    records: list[NSEDailyRecord] = []
    for raw_row in reader:
        row = normalize_keys(raw_row)
        try:
            records.append(
                NSEDailyRecord(
                    trading_date=datetime.strptime(clean_value(row.get("DATE1")), "%d-%b-%Y").date(),
                    symbol=clean_value(row.get("SYMBOL")).upper(),
                    series=clean_value(row.get("SERIES")).upper(),
                    isin="",
                    open=parse_decimal(row.get("OPEN_PRICE")),
                    high=parse_decimal(row.get("HIGH_PRICE")),
                    low=parse_decimal(row.get("LOW_PRICE")),
                    close=parse_decimal(row.get("CLOSE_PRICE")),
                    volume=parse_int(row.get("TTL_TRD_QNTY")),
                    traded_value=parse_optional_decimal(
                        row.get("TURNOVER_LACS")
                        or row.get("TURNOVER")
                        or row.get("VALUE")
                    ),
                    source_file=source_file,
                    source_format="legacy_sec_bhavdata_full",
                )
            )
        except (ValueError, ArithmeticError):
            continue
    return records


def parse_udiff_rows(
    reader: csv.DictReader,
    *,
    source_file: str,
) -> list[NSEDailyRecord]:
    records: list[NSEDailyRecord] = []
    for raw_row in reader:
        row = normalize_keys(raw_row)
        if clean_value(row.get("FinInstrmTp")).upper() not in {"", "STK"}:
            continue
        try:
            records.append(
                NSEDailyRecord(
                    trading_date=date.fromisoformat(clean_value(row.get("TradDt"))),
                    symbol=clean_value(row.get("TckrSymb")).upper(),
                    series=clean_value(row.get("SctySrs")).upper(),
                    isin=clean_value(row.get("ISIN")).upper(),
                    open=parse_decimal(row.get("OpnPric")),
                    high=parse_decimal(row.get("HghPric")),
                    low=parse_decimal(row.get("LwPric")),
                    close=parse_decimal(row.get("ClsPric")),
                    volume=parse_int(row.get("TtlTradgVol")),
                    traded_value=parse_optional_decimal(
                        row.get("TtlTrfVal")
                        or row.get("TtlTradgVal")
                        or row.get("TtlTradgVal")
                    ),
                    source_file=source_file,
                    source_format="udiff_common_bhavcopy",
                )
            )
        except (ValueError, ArithmeticError):
            continue
    return records


def dates_in_range(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def normalize_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {clean_header(key): value for key, value in row.items()}


def clean_header(value: str | None) -> str:
    return (value or "").strip()


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_decimal(value: Any) -> Decimal:
    return Decimal(clean_value(value).replace(",", ""))


def parse_int(value: Any) -> int:
    return int(parse_decimal(value))


def parse_optional_decimal(value: Any) -> Decimal | None:
    cleaned = clean_value(value).replace(",", "")
    if not cleaned:
        return None
    return Decimal(cleaned)


def xlsx_bytes_to_csv(raw_bytes: bytes) -> str:
    rows = xlsx_rows(raw_bytes)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def xlsx_rows(raw_bytes: bytes) -> list[list[str]]:
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        shared_strings = read_shared_strings(archive, namespace)
        sheet_names = [
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        ]
        if not sheet_names:
            return []
        sheet = ElementTree.fromstring(archive.read(sheet_names[0]))

    rows: list[list[str]] = []
    for row in sheet.findall(".//a:sheetData/a:row", namespace):
        values: list[str] = []
        for cell in row.findall("a:c", namespace):
            column_index = column_index_from_cell_ref(cell.attrib.get("r", ""))
            while len(values) < column_index:
                values.append("")
            values.append(read_cell_value(cell, shared_strings, namespace))
        rows.append(values)
    return rows


def read_shared_strings(archive: zipfile.ZipFile, namespace: dict[str, str]) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("a:si", namespace):
        text_parts = [
            element.text or ""
            for element in item.iter()
            if element.tag.endswith("}t")
        ]
        strings.append("".join(text_parts))
    return strings


def read_cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
    namespace: dict[str, str],
) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [
            element.text or ""
            for element in cell.findall(".//a:t", namespace)
        ]
        return "".join(parts)

    value = cell.find("a:v", namespace)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        index = int(value.text)
        return shared_strings[index] if index < len(shared_strings) else ""
    return value.text


def column_index_from_cell_ref(cell_ref: str) -> int:
    letters = "".join(character for character in cell_ref if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + (ord(character.upper()) - ord("A") + 1)
    return max(index - 1, 0)
