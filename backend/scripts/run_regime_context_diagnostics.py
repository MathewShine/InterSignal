from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.diagnostics.regime_context_diagnostic import run_regime_context_diagnostics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the finite preregistered Strategy Diagnostic V1 regime-context suite."
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    required_ignored = (
        "backend/.env",
        "data/research/diagnostics/strategy/v1/regime_context_command_05/registry/regime_context_experiment_registry_v1.json",
        "data/research/diagnostics/strategy/v1/regime_context_command_05/runs/EXP-REGIME-001/result.json",
        "data/reports/strategy_diagnostic_v1_regime_context_summary.json",
        "data/reports/strategy_diagnostic_v1_regime_context_profile.csv",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REGIME_CONTEXT_OUTPUT_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        summary = run_regime_context_diagnostics(
            repo_root=REPO_ROOT,
            tests_passed=args.tests_passed,
            frontend_build_passed=args.frontend_build_passed,
            progress=lambda message: print(f"[regime-context-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "REGIME_CONTEXT_DIAGNOSTIC_FAILED",
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
                "command_version": summary["command_version"],
                "newly_registered_experiment_count": summary["newly_registered_experiment_count"],
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
