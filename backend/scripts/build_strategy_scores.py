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

from app.risk.risk_config import resolve_current_risk_structure_dataset  # noqa: E402
from app.services.daily_feature_engine import json_safe  # noqa: E402
from app.strategy.scoring.score_baseline import get_current_scoring_baseline  # noqa: E402
from app.strategy.scoring.strategy_scorer import (  # noqa: E402
    StrategyScoreEngineConfig,
    build_strategy_scores,
    write_strategy_score_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    current_baseline = get_current_scoring_baseline(args.data_dir)
    config = StrategyScoreEngineConfig(data_dir=args.data_dir, full_generation=not args.pilot_only)
    if (
        config.score_config.score_version != current_baseline.version
        or config.score_config.score_profile != current_baseline.profile
        or config.score_config.config_hash() != current_baseline.config_hash
        or config.output_dataset_path != current_baseline.dataset_path
    ):
        print(json.dumps({"status": "FAILED", "code": "CURRENT_SCORE_BASELINE_RESOLUTION_MISMATCH"}, indent=2))
        return 1
    required_ignored = (
        "backend/.env",
        relative_repo_path(resolve_current_risk_structure_dataset(args.data_dir)),
        relative_repo_path(config.output_dataset_path),
        relative_repo_path(config.summary_path),
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        report = build_strategy_scores(
            config=config,
            progress=lambda message: print(f"[strategy-score-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "STRATEGY_SCORE_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_strategy_score_markdown(report, REPO_ROOT / "docs" / "strategy-v1-final-scoring.md")
    print(json.dumps(json_safe(compact_report(report)), indent=2))
    return 0 if report["pilot"]["passed"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic STRATEGY_SCORE_V1 daily-EOD swing scores.")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    return parser


def relative_repo_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "ready_for_review": report["ready_for_review"],
        "score": report["score"],
        "risk_input": report["risk_input"],
        "pilot": report["pilot"],
        "generation": report["generation"],
        "funnel": report["funnel"],
        "score_distribution": report["score_distribution"],
        "coverage": report["coverage"],
        "max_reachability": report["max_reachability"],
        "invariants": report["invariants"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
