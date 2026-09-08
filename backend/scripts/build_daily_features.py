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

from app.services.daily_feature_engine import (  # noqa: E402
    DailyFeatureEngineConfig,
    build_daily_feature_engine,
    json_safe,
    write_daily_feature_engine_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = DailyFeatureEngineConfig(
        data_dir=args.data_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        full_generation=not args.pilot_only,
    )
    try:
        report = build_daily_feature_engine(config=config, progress=lambda message: print(f"[daily-features] {message}"))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "DAILY_FEATURE_ENGINE_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_daily_feature_engine_markdown(report, REPO_ROOT / "docs" / "daily-feature-engine.md")
    print(json.dumps(json_safe(compact_console_report(report)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build leakage-safe DAILY_FEATURES_V1 snapshots for point-in-time Nifty 500 research.")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
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
    generation = report["generation"]
    return {
        "status": "COMPLETED" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "feature_version": report["feature_engine"]["feature_version"],
        "dataset_path": report["feature_engine"]["dataset_path"],
        "full_generation_completed": generation["full_generation_completed"],
        "total_potential_symbol_date_observations": generation["total_potential_symbol_date_observations"],
        "generated_feature_rows": generation["generated_feature_rows"],
        "ready_rows": generation["ready_rows"],
        "partial_or_null_rows": generation["rows_with_partial_or_null_features"],
        "corporate_action_blocked_rows": generation["corporate_action_blocked_rows"],
        "insufficient_history_rows": generation["insufficient_history_rows"],
        "membership_uncertain_rows": generation["membership_uncertain_rows"],
        "usable_percent_by_lookback": generation["usable_percent_by_lookback"],
        "benchmark": report["benchmark"],
        "sector": report["sector"],
        "pilot": report["pilot"],
        "integrity": report["integrity"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
