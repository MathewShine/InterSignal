from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.providers.groww import GrowwAuthService, GrowwCredentials  # noqa: E402
from app.providers.groww.exceptions import (  # noqa: E402
    GrowwAuthenticationError,
    GrowwProviderError,
    GrowwProviderNotConfiguredError,
)
from app.services.nifty500_acquisition import (  # noqa: E402
    AcquisitionConfig,
    NIFTY500_SOURCE_URL,
    PILOT_SYMBOLS,
    download_nifty500_source,
    default_start_date,
    latest_safe_end_date,
    map_constituents_to_groww,
    normalize_nifty500_constituents,
    select_mappings,
    select_pilot_mappings,
    write_mapping_csv,
    write_reference_files,
    write_reports,
    acquire_daily_history,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = AcquisitionConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        resume=args.resume,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
        request_delay_seconds=args.request_delay,
        max_retries=args.max_retries,
        retry_base_seconds=args.retry_base,
        timeout_seconds=args.timeout,
    )

    try:
        report = asyncio.run(run(args, config))
    except GrowwProviderNotConfiguredError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code}, indent=2))
        return 1
    except GrowwAuthenticationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 2
    except GrowwProviderError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "code": "NIFTY500_ACQUISITION_FAILED", "message": exc.__class__.__name__},
                indent=2,
            )
        )
        return 2

    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire Nifty 500 daily Groww history into local research-data files."
    )
    parser.add_argument("--start-date", type=lambda value: __import__("datetime").date.fromisoformat(value), default=default_start_date())
    parser.add_argument("--end-date", type=lambda value: __import__("datetime").date.fromisoformat(value), default=latest_safe_end_date())
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--symbol", action="append", help="Acquire one NSE symbol; repeat for multiple symbols.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--run-full", action="store_true", help="Run pilot first, then all mapped Nifty 500 symbols if the pilot passes.")
    parser.add_argument("--request-delay", type=float, default=0.5)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-base", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


async def run(args: argparse.Namespace, config: AcquisitionConfig) -> dict[str, Any]:
    raw_csv, source_metadata = download_nifty500_source(
        url=NIFTY500_SOURCE_URL,
        timeout_seconds=config.timeout_seconds,
    )
    constituents = normalize_nifty500_constituents(
        raw_csv,
        source_date=source_metadata["source_date"],
        source_url=source_metadata["source_url"],
    )
    write_reference_files(
        raw_csv=raw_csv,
        constituents=constituents,
        metadata=source_metadata,
        reference_dir=config.reference_dir,
    )

    credentials = GrowwCredentials.from_settings(__import__("app.config.settings", fromlist=["get_settings"]).get_settings())
    auth_service = GrowwAuthService(credentials=credentials)
    if not auth_service.is_configured:
        raise GrowwProviderNotConfiguredError()

    client = auth_service.get_client()
    with redirect_stdout(StringIO()):
        instruments_frame = client.get_all_instruments()
    instruments = instruments_frame.to_dict("records")
    mappings = map_constituents_to_groww(constituents, instruments)
    write_mapping_csv(config.reference_dir / "nifty500_groww_mapping.csv", mappings)

    full_acquisition_run = False
    pilot_mappings = select_pilot_mappings(mappings)
    selected_mappings = select_run_mappings(args, mappings, pilot_mappings)
    pilot_symbols = [mapping.nse_symbol for mapping in pilot_mappings]

    if args.run_full and not args.symbol and args.max_symbols is None:
        pilot_summaries = await acquire_daily_history(
            pilot_mappings,
            config=config,
            auth_service=auth_service,
            progress=lambda message: print(message, flush=True),
        )
        if any(summary.fetch_status in {"FAILED", "UNMAPPED"} for summary in pilot_summaries):
            return write_reports(
                summaries=pilot_summaries,
                mappings=mappings,
                constituents=constituents,
                config=config,
                source_metadata=source_metadata,
                full_acquisition_run=False,
                pilot_symbols=pilot_symbols,
                markdown_path=REPO_ROOT / "docs" / "nifty500-daily-data-acquisition.md",
            )
        selected_mappings = mappings
        full_acquisition_run = True

    summaries = await acquire_daily_history(
        selected_mappings,
        config=config,
        auth_service=auth_service,
        progress=lambda message: print(message, flush=True),
    )

    return write_reports(
        summaries=summaries,
        mappings=mappings,
        constituents=constituents,
        config=config,
        source_metadata=source_metadata,
        full_acquisition_run=full_acquisition_run,
        pilot_symbols=pilot_symbols,
        markdown_path=REPO_ROOT / "docs" / "nifty500-daily-data-acquisition.md",
    )


def select_run_mappings(
    args: argparse.Namespace,
    mappings,
    pilot_mappings,
):
    if args.symbol:
        return select_mappings(mappings, symbols=args.symbol)
    if args.max_symbols is not None:
        return select_mappings(mappings, max_symbols=args.max_symbols)
    return pilot_mappings


def backend_env_is_ignored() -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def compact_console_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "constituent_count": report["constituent_count"],
        "mapping_counts": report["mapping_counts"],
        "fetch_counts": report["fetch_counts"],
        "full_acquisition_run": report["full_acquisition_run"],
        "target_date_range": report["target_date_range"],
        "overall_coverage": report["overall_coverage"],
        "storage": report["storage"],
        "safety": report["safety"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
