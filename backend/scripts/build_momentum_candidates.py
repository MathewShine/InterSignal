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

from app.strategy.momentum_candidates import (  # noqa: E402
    MomentumCandidateEngineConfig,
    build_momentum_candidate_engine,
    write_momentum_candidate_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = MomentumCandidateEngineConfig(
        data_dir=args.data_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        full_generation=not args.pilot_only,
    )
    try:
        report = build_momentum_candidate_engine(
            config=config,
            progress=lambda message: print(f"[momentum-candidates] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "MOMENTUM_CANDIDATE_ENGINE_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_momentum_candidate_markdown(report, REPO_ROOT / "docs" / "momentum-candidate-engine.md")
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build MOMENTUM_CANDIDATES_V1 snapshots from DAILY_FEATURES_V1.")
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
        "candidate_version": report["candidate_engine"]["candidate_version"],
        "candidate_config_hash": report["candidate_engine"]["candidate_config_hash"],
        "full_generation_completed": generation["full_generation_completed"],
        "total_evaluated_rows": generation["total_evaluated_rows"],
        "emerging_count": generation["emerging_count"],
        "confirmed_count": generation["confirmed_count"],
        "rejected_count": generation["rejected_count"],
        "unavailable_count": generation["unavailable_count"],
        "both_eligible_count": generation["both_eligible_count"],
        "candidate_count_distribution": generation["candidate_count_distribution"],
        "major_rejection_reasons": generation["major_rejection_reasons"],
        "pilot": report["pilot"],
        "integrity": report["integrity"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
