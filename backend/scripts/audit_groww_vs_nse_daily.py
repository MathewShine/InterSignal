from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.providers.groww import GrowwAuthService, GrowwCredentials  # noqa: E402
from app.providers.groww.exceptions import GrowwProviderError  # noqa: E402
from app.providers.nse import NSEDailyReferenceProvider  # noqa: E402
from app.services.groww_nse_daily_audit import (  # noqa: E402
    AuditConfig,
    PILOT_SYMBOLS,
    compare_symbol,
    fetch_groww_raw_daily_rows,
    prototype_gap_fill,
    write_audit_outputs,
)
from app.services.nifty500_acquisition import (  # noqa: E402
    NIFTY500_SOURCE_URL,
    download_nifty500_source,
    map_constituents_to_groww,
    normalize_nifty500_constituents,
)
from app.config.settings import get_settings  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = AuditConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        request_delay_seconds=args.request_delay,
        nse_request_delay_seconds=args.nse_request_delay,
        max_retries=args.max_retries,
        timeout_seconds=args.timeout,
    )

    try:
        report = asyncio.run(run_audit(args, config))
    except GrowwProviderError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "code": "GROWW_NSE_AUDIT_FAILED", "message": exc.__class__.__name__},
                indent=2,
            )
        )
        return 2

    print(json.dumps(compact_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit Groww daily pilot rows against official NSE daily records."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--symbol", action="append", help="Pilot symbol to audit; repeat for multiple.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--request-delay", type=float, default=0.5)
    parser.add_argument("--nse-request-delay", type=float, default=0.1)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--force-nse-refresh", action="store_true")
    parser.add_argument("--prototype-gap-fill-symbol", default="")
    return parser


async def run_audit(args: argparse.Namespace, config: AuditConfig) -> dict:
    symbols = tuple(symbol.upper() for symbol in (args.symbol or PILOT_SYMBOLS))
    raw_csv, source_metadata = download_nifty500_source(
        url=NIFTY500_SOURCE_URL,
        timeout_seconds=config.timeout_seconds,
    )
    constituents = normalize_nifty500_constituents(
        raw_csv,
        source_date=source_metadata["source_date"],
        source_url=source_metadata["source_url"],
    )

    credentials = GrowwCredentials.from_settings(get_settings())
    auth_service = GrowwAuthService(credentials=credentials)
    client = auth_service.get_client()
    with redirect_stdout(StringIO()):
        instruments = client.get_all_instruments().to_dict("records")
    mappings = map_constituents_to_groww(constituents, instruments)
    mapping_by_symbol = {mapping.nse_symbol: mapping for mapping in mappings}
    pilot_mappings = [mapping_by_symbol[symbol] for symbol in symbols if symbol in mapping_by_symbol]

    nse_provider = NSEDailyReferenceProvider(
        cache_dir=config.nse_cache_dir,
        timeout_seconds=config.timeout_seconds,
        request_delay_seconds=config.nse_request_delay_seconds,
        force_refresh=args.force_nse_refresh,
    )
    nse_sessions = nse_provider.get_sessions(
        start=config.start_date,
        end=config.end_date,
        symbols=symbols,
    )

    row_audits_by_symbol = {}
    comparisons_by_symbol = {}
    summaries = []

    for index, mapping in enumerate(pilot_mappings, start=1):
        print(f"Groww raw audit fetch: [{index}/{len(pilot_mappings)}] {mapping.nse_symbol}", flush=True)
        groww_rows = await fetch_groww_raw_daily_rows(
            mapping,
            config=config,
            auth_service=auth_service,
        )
        summary, row_audits, comparisons = compare_symbol(
            symbol=mapping.nse_symbol,
            groww_rows=groww_rows,
            nse_sessions=nse_sessions,
            config=config,
        )
        summaries.append(summary)
        row_audits_by_symbol[mapping.nse_symbol] = row_audits
        comparisons_by_symbol[mapping.nse_symbol] = comparisons

        if args.prototype_gap_fill_symbol.upper() == mapping.nse_symbol:
            rows = prototype_gap_fill(
                symbol=mapping.nse_symbol,
                groww_rows=groww_rows,
                nse_sessions=nse_sessions,
            )
            fill_path = config.audit_dir / f"{mapping.nse_symbol}_gap_fill_prototype.csv"
            from app.services.groww_nse_daily_audit import write_csv

            write_csv(
                fill_path,
                rows,
                ["trading_date", "open", "high", "low", "close", "volume", "source_origin"],
            )

    source_details = {
        "nse_source": "Official NSE daily security bhavcopy sec_bhavdata_full_DDMMYYYY.csv",
        "nse_url_template": NSEDailyReferenceProvider.legacy_url_template,
        "nifty_constituent_source": source_metadata,
        "groww_source": "Official Groww historical candles API via growwapi",
    }

    return write_audit_outputs(
        summaries=summaries,
        row_audits_by_symbol=row_audits_by_symbol,
        comparisons_by_symbol=comparisons_by_symbol,
        config=config,
        source_metadata=source_details,
        markdown_path=REPO_ROOT / "docs" / "groww-vs-nse-daily-data-audit.md",
    )


def backend_env_is_ignored() -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def compact_report(report: dict) -> dict:
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "pilot_symbols": report["pilot_symbols"],
        "date_range": report["date_range"],
        "totals": report["totals"],
        "symbol_status_counts": report["symbol_status_counts"],
        "final_classification": report["final_classification"],
        "recommended_next_action": report["recommended_next_action"],
        "storage": report["storage"],
        "safety": report["safety"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
