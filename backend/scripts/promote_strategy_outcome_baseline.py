from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.strategy.outcomes.outcome_baseline import (  # noqa: E402
    build_outcome_baseline_promotion_report,
    write_outcome_baseline_promotion_markdown,
    write_outcome_baseline_promotion_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and freeze the current historical outcome baseline.")
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()

    if not git_ignored("data/reports/strategy_outcome_baseline_promotion.json"):
        print(json.dumps({"status": "FAILED", "code": "PROMOTION_REPORT_NOT_IGNORED"}, indent=2))
        return 1

    report = build_outcome_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
    )
    report_path = REPO_ROOT / "data/reports/strategy_outcome_baseline_promotion.json"
    document_path = REPO_ROOT / "docs/strategy-outcome-baseline-promotion.md"
    write_outcome_baseline_promotion_report(report_path, report)
    write_outcome_baseline_promotion_markdown(document_path, report)
    print(
        json.dumps(
            {
                "promotion_status": report["promotion_status"],
                "step_status": report["step_status"],
                "ready_for_review": report["ready_for_review"],
                "report": str(report_path),
                "document": str(document_path),
            },
            indent=2,
        )
    )
    return 0 if report["ready_for_review"] else 1


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
