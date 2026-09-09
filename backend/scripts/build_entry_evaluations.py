from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.daily_feature_engine import json_safe  # noqa: E402
from app.strategy.entry_evaluator import (  # noqa: E402
    EntryEvaluationEngineConfig,
    build_entry_evaluations,
    write_strategy_v1_entry_evaluation_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not git_ignored("backend/.env"):
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1
    if not git_ignored("data/research/entry_evaluations/daily/v1/entry_evaluations_v1.csv.gz"):
        print(json.dumps({"status": "FAILED", "code": "ENTRY_EVALUATION_DATASET_NOT_IGNORED"}, indent=2))
        return 1

    config = EntryEvaluationEngineConfig(data_dir=args.data_dir, full_generation=not args.pilot_only)
    try:
        report = build_entry_evaluations(
            config=config,
            progress=lambda message: print(f"[entry-evaluation] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "ENTRY_EVALUATION_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_strategy_v1_entry_evaluation_markdown(report, REPO_ROOT / "docs" / "strategy-v1-entry-evaluation.md")
    print(json.dumps(json_safe(compact_console_report(report)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ENTRY_EVALUATION_V1 research entry-context rows.")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    return parser


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
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
        "entry_version": report["entry"]["entry_version"],
        "entry_config_hash": report["entry"]["entry_config_hash"],
        "entry_availability": report["entry"]["entry_availability"],
        "decision_use": report["entry"]["decision_use"],
        "input_versions": report["inputs"]["versions"],
        "input_hashes_before": report["inputs"]["hashes_before"],
        "input_hashes_after": report["inputs"]["hashes_after"],
        "full_generation_completed": generation["full_generation_completed"],
        "total_rows_evaluated": generation["total_rows_evaluated"],
        "entry_evaluation_status_counts": generation["entry_evaluation_status_counts"],
        "entry_readiness_counts": generation["entry_readiness_counts"],
        "candidate_to_setup_conversion_pct": generation["candidate_to_setup_conversion_pct"],
        "setup_to_entry_readiness_conversion_pct": generation["setup_to_entry_readiness_conversion_pct"],
        "daily_ready_for_risk_distribution": generation["daily_ready_for_risk_distribution"],
        "candidate_group_readiness": generation["candidate_group_readiness"],
        "regime_funnel": generation["regime_funnel"],
        "exceptional_long_sanity": generation["exceptional_long_sanity"],
        "pilot": report["pilot"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
