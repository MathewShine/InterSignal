from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nse_daily_acquisition import (  # noqa: E402
    NSEDailyAcquisitionConfig,
    acquire_nse_daily_dataset,
    build_pilot_calendar_dates,
    default_start_date,
    latest_safe_end_date,
    write_nse_daily_markdown_report,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    source_cache_dir = args.source_cache_dir
    if source_cache_dir is None:
        default_cache = REPO_ROOT / "data" / "reference" / "nse" / "daily" / "raw"
        source_cache_dir = default_cache if default_cache.exists() else None

    config = NSEDailyAcquisitionConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        run_mode="FULL" if args.run_full else "PILOT",
        resume=args.resume,
        force_refresh=args.force_refresh,
        request_delay_seconds=args.request_delay,
        max_retries=args.max_retries,
        retry_base_seconds=args.retry_base,
        timeout_seconds=args.timeout,
        max_sessions=args.max_sessions if args.run_full else None,
        source_cache_dir=source_cache_dir,
    )

    try:
        report = run(args, config)
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "code": "NSE_DAILY_ACQUISITION_FAILED", "message": exc.__class__.__name__},
                indent=2,
            )
        )
        return 2

    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire official NSE daily cash-market files into local InterSignal research datasets."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=default_start_date())
    parser.add_argument("--end-date", type=date.fromisoformat, default=latest_safe_end_date())
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--source-cache-dir", type=Path, help="Optional existing official NSE flat cache to import from.")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--run-full", action="store_true", help="Run pilot first, then scan the full date range if pilot passes.")
    parser.add_argument("--max-sessions", type=int, help="Maximum official sessions to process during a full scan.")
    parser.add_argument("--pilot-date-count", type=int, default=36, help="Number of evenly spaced calendar dates checked in pilot mode.")
    parser.add_argument("--request-delay", type=float, default=0.2)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-base", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def run(args: argparse.Namespace, config: NSEDailyAcquisitionConfig) -> dict[str, Any]:
    pilot_dates = build_pilot_calendar_dates(
        config.start_date,
        config.end_date,
        target_dates=args.pilot_date_count,
    )
    pilot_config = replace(config, run_mode="PILOT", max_sessions=None)
    pilot_report = acquire_nse_daily_dataset(
        config=pilot_config,
        calendar_dates=pilot_dates,
        progress=lambda message: print(message, flush=True),
    )

    final_report = pilot_report
    full_report = None
    if args.run_full and pilot_passed(pilot_report):
        full_config = replace(config, run_mode="FULL", max_sessions=args.max_sessions)
        full_report = acquire_nse_daily_dataset(
            config=full_config,
            progress=lambda message: print(message, flush=True),
        )
        final_report = full_report

    write_nse_daily_markdown_report(final_report, REPO_ROOT / "docs" / "nse-5year-daily-dataset.md")
    return {
        "status": "COMPLETED",
        "pilot": pilot_report,
        "full": full_report,
        "final": final_report,
    }


def pilot_passed(report: dict[str, Any]) -> bool:
    return (
        report["sessions"]["failed"] == 0
        and report["sessions"]["downloaded"] > 0
        and report["records"]["total_normalized"] > 0
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


def compact_console_report(report: dict[str, Any]) -> dict[str, Any]:
    final = report["final"]
    return {
        "status": report["status"],
        "phase": final["phase"],
        "run_mode": final["run_mode"],
        "pilot_passed": pilot_passed(report["pilot"]),
        "full_acquisition_completed": report["full"] is not None,
        "target_date_range": final["target_date_range"],
        "actual_date_range": final["actual_date_range"],
        "calendar": final["calendar"],
        "sessions": final["sessions"],
        "records": final["records"],
        "storage": final["storage"],
        "safety": final["safety"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

