from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.diagnostics.strategy_diagnostic import run_strategy_diagnostic_framework  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the finite, preregistered Strategy Diagnostic Framework V1 suite."
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    required_ignored = (
        "backend/.env",
        "data/research/diagnostics/strategy/v1/registry/experiment_registry_v1.json",
        "data/research/diagnostics/strategy/v1/runs/EXP-RANK-001/result.json",
        "data/reports/strategy_diagnostic_v1_summary.json",
        "data/reports/strategy_diagnostic_v1_registry.csv",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "DIAGNOSTIC_OUTPUT_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        summary = run_strategy_diagnostic_framework(
            repo_root=REPO_ROOT,
            tests_passed=args.tests_passed,
            frontend_build_passed=args.frontend_build_passed,
            progress=lambda message: print(f"[strategy-diagnostic-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "STRATEGY_DIAGNOSTIC_FRAMEWORK_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "framework_version": summary["framework_version"],
                "framework_profile": summary["framework_profile"],
                "registered_experiment_count": summary["registered_experiment_count"],
                "classifications": summary["classifications"],
                "runtime_seconds": summary["runtime_seconds"],
                "storage": summary["storage"],
                "ready_for_review": summary["ready_for_review"],
            },
            indent=2,
        )
    )
    return 0 if summary["ready_for_review"] else 3


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
