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

from app.services.nifty500_corporate_action_readiness import (  # noqa: E402
    Nifty500CAReadinessConfig,
    build_nifty500_corporate_action_readiness,
    write_nifty500_readiness_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = Nifty500CAReadinessConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        complex_event_window_days=args.complex_event_window_days,
        unresolved_event_window_days=args.unresolved_event_window_days,
    )
    try:
        report = build_nifty500_corporate_action_readiness(
            config=config,
            progress=lambda message: print(message, flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "NIFTY500_CA_READINESS_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_nifty500_readiness_markdown(
        report,
        REPO_ROOT / "docs" / "nifty500-corporate-action-readiness.md",
    )
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prioritise corporate-action uncertainty for Nifty 500 Strategy V1 research readiness."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--complex-event-window-days", type=int, default=5)
    parser.add_argument("--unresolved-event-window-days", type=int, default=5)
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
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "ready_for_review": report["ready_for_review"],
        "overall_readiness": report["overall_readiness"],
        "unresolved_suspects": report["unresolved_suspects"],
        "manual_review": {
            "row_count": report["manual_review"]["row_count"],
            "nifty500_relevant_rows": report["manual_review"]["nifty500_relevant_rows"],
            "eq_rows": report["manual_review"]["eq_rows"],
            "special_series_rows": report["manual_review"]["special_series_rows"],
            "class_counts": report["manual_review"]["class_counts"],
        },
        "research_eligibility": report["research_eligibility"],
        "symbol_readiness": report["symbol_readiness"]["counts"],
        "critical_unresolved_symbols": report["symbol_readiness"]["critical_unresolved_symbols"],
        "methodology": report["methodology"],
        "integrity": report["integrity"],
        "safety": report["safety"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
