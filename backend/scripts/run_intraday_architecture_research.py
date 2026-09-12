from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.architecture import build_intraday_architecture_research


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build provider-neutral intraday architecture reports from synthetic test fixtures only."
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_intraday_architecture_research(
        repo_root=REPO_ROOT,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[intraday-architecture] {message}", flush=True),
    )
    compact = {
        "architecture_version": report["architecture_version"],
        "canonical_profile": report["canonical_profile"],
        "execution_ordering_version": report["execution_ordering_version"],
        "config_hash": report["config_hash"],
        "dataset_hashes": report["dataset_hashes"],
        "quality": report["quality"],
        "classifications": report["classifications"],
        "validation_state": report["temporal_integration"]["validation_state"],
        "baseline_mutation_violations": report["regression"]["baseline_mutation_violations"],
        "tests_passed": report["tests_passed"],
        "frontend_build_passed": report["frontend_build_passed"],
        "ready_for_review": report["ready_for_review"],
        "runtime_seconds": report["runtime_seconds"],
        "artifact_count": report["artifact_count"],
        "artifact_bytes": report["artifact_bytes"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
