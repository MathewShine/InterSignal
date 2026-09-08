from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.corporate_actions import (  # noqa: E402
    CorporateActionConfig,
    build_corporate_action_layer,
    write_corporate_actions_markdown_report,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = CorporateActionConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        force_refresh=args.force_refresh,
        timeout_seconds=args.timeout,
        request_delay_seconds=args.request_delay,
        adjusted_volume_enabled=not args.no_adjusted_volume,
    )

    try:
        report = build_corporate_action_layer(
            config=config,
            progress=lambda message: print(message, flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "CORPORATE_ACTION_LAYER_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_corporate_actions_markdown_report(
        report,
        REPO_ROOT / "docs" / "corporate-actions-and-adjusted-prices.md",
    )
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build official NSE corporate-action events and adjusted research daily prices."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--request-delay", type=float, default=0.2)
    parser.add_argument("--no-adjusted-volume", action="store_true")
    return parser


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
    adjusted = report["adjusted_dataset"]
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "ready_for_review": report["ready_for_review"],
        "date_coverage": report["date_coverage"],
        "events": {
            "total": report["events"]["total"],
            "counts_by_type": report["events"]["counts_by_type"],
            "price_adjustment_event_count": report["events"]["price_adjustment_event_count"],
            "manual_review_event_count": report["events"]["manual_review_event_count"],
            "continuity_break_event_count": report["events"]["continuity_break_event_count"],
        },
        "adjustment_factors": report["adjustment_factors"],
        "suspect_reconciliation": report["suspect_reconciliation"],
        "pilot_passed": report["pilot"]["pilot_passed"],
        "adjusted_dataset": {
            "full_processing_completed": adjusted.get("full_processing_completed"),
            "record_count": adjusted.get("record_count"),
            "adjusted_record_count": adjusted.get("adjusted_record_count"),
            "status_counts": adjusted.get("status_counts"),
            "output_path": adjusted.get("output_path"),
            "storage_size_bytes": adjusted.get("storage_size_bytes"),
        },
        "raw_integrity_unchanged": report["raw_integrity"]["unchanged"],
        "processing": report["processing"],
        "safety": report["safety"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
