from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.development_ingestion import RunMode, run_development_intraday_ingestion


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan, ingest, resume, replay, or verify the frozen bounded DEVELOPMENT intraday dataset"
    )
    parser.add_argument(
        "--mode",
        choices=[str(value) for value in RunMode],
        default=str(RunMode.PLAN_ONLY),
        help="PLAN_ONLY never contacts the provider; other network modes use only the immutable request plan",
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    report = run_development_intraday_ingestion(
        repo_root=REPO_ROOT,
        mode=args.mode,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[development-intraday] {message}", flush=True),
    )
    if args.mode == str(RunMode.PLAN_ONLY):
        output = report
    else:
        output = {
            "command_version": report["command_version"],
            "mode": args.mode,
            "result": report["classifications"]["BOUNDED_INTRADAY_INGESTION_RESULT"],
            "coverage_result": report["classifications"]["DEVELOPMENT_INTRADAY_COVERAGE_RESULT"],
            "completed_requests": report["retrieval"]["completed_requests"],
            "normalized_5m_rows": report["rows"]["normalized_5m"],
            "opportunity_coverage_pct": report["opportunity_coverage"]["coverage_pct"],
            "ready_for_review": report["ready_for_review"],
        }
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
