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

from app.services.nifty500_ca_final_readiness import (  # noqa: E402
    FinalReadinessConfig,
    build_final_nifty500_ca_readiness,
    write_final_readiness_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = FinalReadinessConfig(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    try:
        report = build_final_nifty500_ca_readiness(config=config)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "NIFTY500_CA_FINAL_READINESS_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_final_readiness_markdown(
        report,
        REPO_ROOT / "docs" / "nifty500-corporate-action-final-readiness.md",
    )
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve INFIBEAM and finalize Nifty 500 corporate-action readiness with finite exclusions."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
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
    impact = report["observation_impact"]
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "overall_readiness": report["overall_readiness"],
        "feature_engine_may_start": report["feature_engine_may_start"],
        "infibeam": report["infibeam"],
        "original_not_ready_count": report["original_not_ready_count"],
        "final_symbol_readiness": report["final_symbol_readiness"]["counts"],
        "converted_to_ready_with_exclusions": report["final_symbol_readiness"]["converted_to_ready_with_exclusions"],
        "still_not_ready_symbols": report["final_symbol_readiness"]["still_not_ready_symbols"],
        "root_cause_breakdown": report["root_cause_breakdown"],
        "exclusion_policy": report["exclusion_policy"],
        "exclusion_intervals": report["exclusion_intervals"],
        "observation_impact": {
            "0": impact["0"],
            "5": impact["5"],
            "20": impact["20"],
            "60": impact["60"],
            "symbols": impact["symbols"],
        },
        "methodology": report["methodology"],
        "integrity": report["integrity"],
        "safety": report["safety"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
