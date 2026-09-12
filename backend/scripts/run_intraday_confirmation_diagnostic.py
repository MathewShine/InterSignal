from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.confirmation_diagnostic import (  # noqa: E402
    run_intraday_confirmation_diagnostic,
)
from app.research.temporal_validation.config import json_ready  # noqa: E402


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the pre-registered DEVELOPMENT-only real-data Intraday "
            "Confirmation Diagnostic V1."
        )
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    required_ignored = (
        "backend/.env",
        "data/research/diagnostics/intraday/v1/confirmation_command_01/registry/intraday_confirmation_registry_v1.json",
        "data/research/diagnostics/intraday/v1/confirmation_command_01/runs/EXP-INTRACONF-001/result.json",
        "data/reports/intraday_confirmation_v1_summary.json",
        "data/reports/intraday_confirmation_v1_5m.csv",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "INTRADAY_CONFIRMATION_OUTPUT_NOT_IGNORED",
                    "paths": missing,
                },
                indent=2,
            )
        )
        return 1
    try:
        summary = run_intraday_confirmation_diagnostic(
            repo_root=REPO_ROOT,
            tests_passed=args.tests_passed,
            frontend_build_passed=args.frontend_build_passed,
            progress=lambda message: print(
                f"[intraday-confirmation-v1] {message}", flush=True
            ),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "INTRADAY_CONFIRMATION_DIAGNOSTIC_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            json_ready({
                "diagnostic_version": summary["diagnostic_version"],
                "profile": summary["profile"],
                "experiment_count": summary["pre_registration"]["experiment_count"],
                "population_hash": summary["population_freeze"][
                    "intraday_confirmation_population_hash"
                ],
                "preregistration_hash": summary["pre_registration"][
                    "intraday_confirmation_prereg_hash"
                ],
                "classifications": summary["classifications"],
                "runtime_seconds": summary["runtime_seconds"],
                "ready_for_review": summary["ready_for_review"],
            }),
            indent=2,
        )
    )
    return 0 if summary["ready_for_review"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
