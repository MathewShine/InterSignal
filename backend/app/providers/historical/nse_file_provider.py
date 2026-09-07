from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.models.ingestion import (
    DailyCandle,
    IngestionIssue,
    InstrumentRecord,
    IntradayCandle,
    ProviderReadResult,
)
from app.providers.historical.base import (
    HistoricalDataProvider,
    ProviderNotImplementedError,
)
from app.providers.historical.csv_provider import (
    CSVColumnMapping,
    CsvHistoricalDataProvider,
)


@dataclass(frozen=True, slots=True)
class NSEFileAdapter:
    name: str
    mode: str
    mapping: CSVColumnMapping
    default_interval: str | None = None


NSE_FILE_ADAPTERS = {
    "daily_bhavcopy": NSEFileAdapter(
        name="daily_bhavcopy",
        mode="daily",
        mapping=CSVColumnMapping(
            symbol="SYMBOL",
            date="TIMESTAMP",
            open="OPEN",
            high="HIGH",
            low="LOW",
            close="CLOSE",
            volume="TOTTRDQTY",
            traded_value="TOTTRDVAL",
        ),
    ),
    "security_master": NSEFileAdapter(
        name="security_master",
        mode="instruments",
        mapping=CSVColumnMapping(
            symbol="SYMBOL",
            exchange="EXCHANGE",
            company_name="NAME_OF_COMPANY",
            isin="ISIN_NUMBER",
            instrument_type="SERIES",
        ),
    ),
}


class NSEFileProvider(HistoricalDataProvider):
    name = "nse-file"

    def __init__(
        self,
        *,
        file_path: str | Path,
        file_format: str = "daily_bhavcopy",
        source: str | None = None,
        delimiter: str = ",",
        encoding: str = "utf-8",
    ) -> None:
        if file_format not in NSE_FILE_ADAPTERS:
            supported = ", ".join(sorted(NSE_FILE_ADAPTERS))
            raise ValueError(f"unsupported NSE file format '{file_format}'. Supported: {supported}")

        self.file_path = Path(file_path)
        self.adapter = NSE_FILE_ADAPTERS[file_format]
        self.source = source or f"nse_{self.adapter.name}"
        self.delimiter = delimiter
        self.encoding = encoding

    async def list_instruments(self) -> ProviderReadResult[InstrumentRecord]:
        if self.adapter.mode != "instruments":
            return ProviderReadResult(
                records=[],
                errors=[
                    IngestionIssue(
                        severity="warning",
                        code="unsupported_file_mode",
                        message="This NSE file adapter does not contain instrument master records.",
                    )
                ],
                rows_read=0,
                source_reference=str(self.file_path),
                metadata=self.get_provider_metadata(),
            )
        return await self._with_csv_provider("instruments")

    async def get_daily_candles(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> ProviderReadResult[DailyCandle]:
        if self.adapter.mode != "daily":
            raise ProviderNotImplementedError(
                "Selected NSE file adapter does not provide daily candles."
            )
        provider = self._build_csv_provider(self._resolve_local_csv_path())
        return await provider.get_daily_candles(start=start, end=end)

    async def get_intraday_candles(
        self,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ProviderReadResult[IntradayCandle]:
        raise ProviderNotImplementedError(
            "NSE intraday file normalization is not implemented in Step 02.3A."
        )

    def supports_interval(self, interval: str) -> bool:
        return self.adapter.mode == "daily" and interval in {"1d", "day", "daily"}

    def get_provider_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "file_format": self.adapter.name,
            "source": self.source,
            "file_path": str(self.file_path),
            "local_file_only": True,
            "zip_supported": True,
        }

    async def _with_csv_provider(self, mode: str) -> ProviderReadResult:
        provider = self._build_csv_provider(self._resolve_local_csv_path())
        if mode == "instruments":
            return await provider.list_instruments()
        raise ProviderNotImplementedError(f"Unsupported NSE mode: {mode}")

    def _build_csv_provider(self, file_path: Path) -> CsvHistoricalDataProvider:
        return CsvHistoricalDataProvider(
            file_path=file_path,
            mapping=self.adapter.mapping,
            source=self.source,
            provider=self.name,
            delimiter=self.delimiter,
            encoding=self.encoding,
            default_exchange="NSE",
            default_interval=self.adapter.default_interval,
        )

    def _resolve_local_csv_path(self) -> Path:
        if self.file_path.suffix.lower() != ".zip":
            return self.file_path

        with zipfile.ZipFile(self.file_path) as archive:
            csv_members = [
                member for member in archive.namelist()
                if member.lower().endswith(".csv") and not member.endswith("/")
            ]
            if not csv_members:
                raise ValueError("NSE ZIP file does not contain a CSV member.")

            temporary_directory = tempfile.TemporaryDirectory()
            extracted_path = Path(temporary_directory.name) / Path(csv_members[0]).name
            extracted_path.write_bytes(archive.read(csv_members[0]))
            self._temporary_directory = temporary_directory
            return extracted_path

