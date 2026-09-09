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

from app.strategy.daily_setup_evaluator import (  # noqa: E402
    DailySetupEvaluationEngineConfig,
    build_daily_setup_evaluations,
    write_daily_setup_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = DailySetupEvaluationEngineConfig(
        data_dir=args.data_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        full_generation=not args.pilot_only,
    )
    try:
        report = build_daily_setup_evaluations(
            config=config,
            progress=lambda message: print(f"[daily-setup] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "DAILY_SETUP_EVALUATION_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_daily_setup_markdown(report, REPO_ROOT / "docs" / "daily-breakout-setup-evaluation.md")
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build DAILY_SETUP_EVALUATION_V1 from Momentum Candidate snapshots.")
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
        "setup_version": report["setup_evaluator"]["setup_version"],
        "setup_config_hash": report["setup_evaluator"]["setup_config_hash"],
        "candidate_version": report["inputs"]["candidate_version"],
        "candidate_config_hash": report["inputs"]["candidate_config_hash"],
        "feature_version": report["inputs"]["feature_version"],
        "full_generation_completed": generation["full_generation_completed"],
        "candidate_rows_evaluated": generation["candidate_rows_evaluated"],
        "setup_eligible_count": generation["setup_eligible_count"],
        "setup_rejected_count": generation["setup_rejected_count"],
        "quality_counts": generation["quality_counts"],
        "emerging_setup_pass_rate_pct": generation["emerging_setup_pass_rate_pct"],
        "confirmed_setup_pass_rate_pct": generation["confirmed_setup_pass_rate_pct"],
        "per_day_setup_eligible_distribution": generation["per_day_setup_eligible_distribution"],
        "major_rejection_reasons": generation["major_rejection_reasons"],
        "pilot": report["pilot"],
        "integrity": {
            "daily_features_v1_unchanged": report["integrity"]["daily_features_v1_unchanged"],
            "momentum_candidates_v1_unchanged": report["integrity"]["momentum_candidates_v1_unchanged"],
            "candidate_config_hash_unchanged": report["integrity"]["candidate_config_hash_unchanged"],
            "adjusted_dataset_unchanged": report["integrity"]["adjusted_dataset_unchanged"],
        },
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
