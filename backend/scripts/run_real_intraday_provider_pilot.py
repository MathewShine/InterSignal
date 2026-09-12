from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.provider_pilot import build_real_intraday_provider_pilot


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded real intraday provider pilot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch-real", action="store_true", help="Perform the preregistered seven-request Groww pilot")
    mode.add_argument("--reuse-existing", action="store_true", help="Rebuild reports from accepted immutable raw payloads without network access")
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    report = build_real_intraday_provider_pilot(
        repo_root=REPO_ROOT,
        fetch_real=args.fetch_real,
        reuse_existing=args.reuse_existing,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[real-intraday-pilot] {message}"),
    )
    print(
        json.dumps(
            {
                "pilot_version": report["pilot_version"],
                "provider": report["selected_provider"],
                "selection_result": report["pilot_provider_selection_result"],
                "runtime_status": report["runtime_status"],
                "result": report["classifications"]["REAL_INTRADAY_PILOT_RESULT"],
                "row_counts": report["row_counts"],
                "ready_for_review": report["ready_for_review"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
