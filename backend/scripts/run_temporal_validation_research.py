from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.temporal_validation.harness import build_temporal_validation_harness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the SEALED temporal development/validation research harness."
    )
    parser.add_argument("--repo-root", type=Path, default=BACKEND_ROOT.parent)
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    required_ignored = (
        "data/research/temporal_validation/v1/manifests/temporal_window_manifest_v1.json",
        "data/reports/temporal_validation_v1_summary.json",
    )
    for path in required_ignored:
        if not git_ignored(repo_root, path):
            raise SystemExit(f"Generated temporal research output is not ignored: {path}")
    if not git_ignored(repo_root, "backend/.env"):
        raise SystemExit("backend/.env must remain ignored")

    report = build_temporal_validation_harness(
        repo_root=repo_root,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[temporal-validation] {message}", flush=True),
    )
    print(json.dumps(compact_report(report), indent=2, sort_keys=True))
    return 0 if report["ready_for_review"] else 3


def git_ignored(repo_root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", relative_path],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def compact_report(report: dict[str, object]) -> dict[str, object]:
    population = report["population"]
    governance = report["validation_governance"]
    development = report["development_baseline_reference"]
    return {
        "harness_version": report["harness_version"],
        "protocol_version": report["protocol_version"],
        "harness_config_hash": report["harness_config_hash"],
        "manifest_hash": report["manifest"]["manifest_hash"],
        "windows": {
            "development": [report["config"]["development_start"], report["config"]["development_end"]],
            "validation": [report["config"]["validation_start"], report["config"]["validation_terminal_date"]],
        },
        "population": population,
        "validation_state": governance["validation_state"],
        "validation_performance_exposed": governance["validation_performance_exposed"],
        "development_baseline_reference": development,
        "classifications": report["classifications"],
        "pilot": report["pilot"],
        "no_peek": report["no_peek"],
        "reproducibility": report["reproducibility"],
        "runtime_seconds": report["runtime_seconds"],
        "storage": report["storage"],
        "ready_for_review": report["ready_for_review"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

