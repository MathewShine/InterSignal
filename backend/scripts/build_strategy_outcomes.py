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
from app.strategy.outcomes.outcome_baseline import (  # noqa: E402
    CURRENT_STRATEGY_OUTCOME_PROFILE,
    CURRENT_STRATEGY_OUTCOME_VERSION,
    get_current_strategy_outcome_baseline,
)
from app.strategy.outcomes.outcome_config import StrategyOutcomeConfig  # noqa: E402
from app.strategy.outcomes.outcome_engine import (  # noqa: E402
    StrategyOutcomeEngineConfig,
    build_strategy_outcomes,
    write_outcome_markdown,
)

__test__ = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build future-separated STRATEGY_OUTCOME_V1 labels for frozen Strategy V1 scores."
    )
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--outcome-version", default=CURRENT_STRATEGY_OUTCOME_VERSION)
    parser.add_argument("--outcome-profile", default=CURRENT_STRATEGY_OUTCOME_PROFILE)
    args = parser.parse_args()
    current_baseline = get_current_strategy_outcome_baseline(args.data_dir)
    outcome_config = StrategyOutcomeConfig(
        outcome_version=args.outcome_version,
        outcome_profile=args.outcome_profile,
    )
    config = StrategyOutcomeEngineConfig(
        data_dir=args.data_dir,
        outcome_config=outcome_config,
        full_generation=not args.pilot_only,
    )
    if (
        outcome_config.outcome_version != current_baseline.version
        or outcome_config.outcome_profile != current_baseline.profile
        or outcome_config.config_hash() != current_baseline.config_hash
        or config.output_dataset_path != current_baseline.dataset_path
    ):
        print(json.dumps({"status": "FAILED", "code": "CURRENT_OUTCOME_BASELINE_RESOLUTION_MISMATCH"}, indent=2))
        return 1
    required_ignored = (
        "backend/.env",
        relative_repo_path(config.output_dataset_path),
        relative_repo_path(config.report_path("summary.json")),
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        report = build_strategy_outcomes(
            config=config,
            progress=lambda message: print(f"[strategy-outcome-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "STRATEGY_OUTCOME_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    write_outcome_markdown(report, REPO_ROOT / "docs" / "strategy-v1-historical-outcomes.md")
    print(json.dumps(json_safe(compact_report(report)), indent=2))
    return 0 if report["ready_for_review"] else 3


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
    generation = report["generation"]
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "VERIFICATION_INCOMPLETE",
        "outcome": report["outcome"],
        "frozen_score": report["frozen_score"],
        "active_risk": report["active_risk"],
        "cohorts": report["cohorts"],
        "total_outcome_rows": generation["total_outcome_rows"],
        "entry_eligible_source_rows": generation["entry_eligible_source_rows"],
        "valid_hypothetical_entry_count": generation["valid_hypothetical_entry_count"],
        "invalid_hypothetical_entry_count": generation["invalid_hypothetical_entry_count"],
        "pilot_passed": report["pilot"]["passed"],
        "sanity": report["sanity"],
        "regression": report["regression"]["checks"],
        "artifacts": report["artifacts"],
        "runtime_seconds": report["runtime_seconds"],
        "safety": report["safety"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
