from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.repositories import (  # noqa: E402
    SupabaseDailyCandleRepository,
    SupabaseInstrumentRepository,
    SupabaseIntradayCandleRepository,
)
from app.db.supabase import SupabaseClientFactory  # noqa: E402
from app.providers.historical import (  # noqa: E402
    CSVColumnMapping,
    CsvHistoricalDataProvider,
    GrowwHistoricalProvider,
    NSEFileProvider,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
)
from app.providers.groww import GrowwProviderError  # noqa: E402
from app.services.historical_ingestion import HistoricalIngestionService  # noqa: E402


CSV_MAPPING_PRESETS = {
    "sample-instruments": CSVColumnMapping(
        symbol="SYMBOL",
        exchange="EXCHANGE",
        company_name="COMPANY",
        isin="ISIN",
        sector="SECTOR",
        industry="INDUSTRY",
        instrument_type="TYPE",
        nifty500_member="NIFTY500",
        provider_symbol="PROVIDER_SYMBOL",
    ),
    "sample-daily": CSVColumnMapping(
        symbol="SYMBOL",
        date="DATE",
        open="OPEN",
        high="HIGH",
        low="LOW",
        close="CLOSE",
        adjusted_close="ADJ_CLOSE",
        volume="VOLUME",
        traded_value="TRADED_VALUE",
    ),
    "sample-intraday": CSVColumnMapping(
        symbol="SYMBOL",
        timestamp="TIMESTAMP",
        interval="INTERVAL",
        open="OPEN",
        high="HIGH",
        low="LOW",
        close="CLOSE",
        volume="VOLUME",
        traded_value="TRADED_VALUE",
        vwap="VWAP",
    ),
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        summary = asyncio.run(run_import(args))
    except (GrowwProviderError, ProviderNotConfiguredError, ProviderNotImplementedError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 1

    print(summary.model_dump_json(indent=2))
    if summary.dry_run:
        return 0
    return 0 if summary.errors_count == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InterSignal historical data ingestion")
    parser.add_argument("--provider", choices=["csv", "nse-file", "groww"], required=True)
    parser.add_argument("--file", type=Path, help="Local CSV or ZIP file path")
    parser.add_argument("--mode", choices=["instruments", "daily", "intraday"], required=True)
    parser.add_argument("--source", default="research_import")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--mapping-preset", choices=sorted(CSV_MAPPING_PRESETS))
    parser.add_argument("--mapping-json", type=Path)
    parser.add_argument("--nse-file-format", default="daily_bhavcopy")
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def run_import(args: argparse.Namespace):
    provider = build_provider(args)
    service = build_service(dry_run=args.dry_run)

    if args.mode == "instruments":
        return await service.ingest_instruments(provider, dry_run=args.dry_run)
    if args.mode == "daily":
        return await service.ingest_daily_candles(provider, dry_run=args.dry_run)
    if args.mode == "intraday":
        return await service.ingest_intraday_candles(
            provider,
            interval=args.interval,
            dry_run=args.dry_run,
        )
    raise ValueError(f"Unsupported mode: {args.mode}")


def build_provider(args: argparse.Namespace):
    if args.provider == "groww":
        return GrowwHistoricalProvider()

    if args.file is None:
        raise ValueError("--file is required for local file providers")

    if args.provider == "nse-file":
        return NSEFileProvider(
            file_path=args.file,
            file_format=args.nse_file_format,
            source=args.source,
            delimiter=args.delimiter,
        )

    mapping = load_csv_mapping(args)
    return CsvHistoricalDataProvider(
        file_path=args.file,
        mapping=mapping,
        source=args.source,
        delimiter=args.delimiter,
        default_interval=args.interval if args.mode == "intraday" else None,
    )


def load_csv_mapping(args: argparse.Namespace) -> CSVColumnMapping:
    if args.mapping_json:
        data: dict[str, Any] = json.loads(args.mapping_json.read_text(encoding="utf-8"))
        return CSVColumnMapping(**data)

    if args.mapping_preset:
        return CSV_MAPPING_PRESETS[args.mapping_preset]

    raise ValueError("CSV provider requires --mapping-preset or --mapping-json")


def build_service(*, dry_run: bool) -> HistoricalIngestionService:
    if dry_run:
        return HistoricalIngestionService()

    factory = SupabaseClientFactory()
    return HistoricalIngestionService(
        instrument_repository=SupabaseInstrumentRepository(factory),
        daily_candle_repository=SupabaseDailyCandleRepository(factory),
        intraday_candle_repository=SupabaseIntradayCandleRepository(factory),
    )


if __name__ == "__main__":
    raise SystemExit(main())
