from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.diagnostics.strategy_diagnostic_synthesis import run_strategy_diagnostic_synthesis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize the completed Strategy Diagnostic V1 evidence without running a new strategy variant.")
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    required_ignored = (
        "backend/.env",
        "data/research/diagnostics/strategy/v1/synthesis_command_06/synthesis_payload_v1.json",
        "data/reports/strategy_diagnostic_v1_synthesis_summary.json",
        "data/reports/strategy_diagnostic_v1_synthesis_hypotheses.csv",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "SYNTHESIS_OUTPUT_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        summary = run_strategy_diagnostic_synthesis(
            repo_root=REPO_ROOT,
            tests_passed=args.tests_passed,
            frontend_build_passed=args.frontend_build_passed,
            progress=lambda message: print(f"[strategy-synthesis-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "code": "STRATEGY_SYNTHESIS_FAILED", "message": exc.__class__.__name__, "detail": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "synthesis_version": summary["synthesis_version"],
                "synthesis_profile": summary["synthesis_profile"],
                "completed_experiments_synthesized": summary["completed_experiments_synthesized"],
                "hypothesis_count": summary["hypothesis_count"],
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
    result = subprocess.run(["git", "check-ignore", path], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
