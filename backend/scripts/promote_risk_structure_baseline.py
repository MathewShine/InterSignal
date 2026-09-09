from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.risk.risk_baseline import build_baseline_promotion_report, write_baseline_promotion_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and report the approved risk baseline promotion.")
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()

    report = build_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
    )
    output_path = REPO_ROOT / "data" / "reports" / "risk_structure_baseline_promotion.json"
    write_baseline_promotion_report(output_path, report)
    print(
        json.dumps(
            {
                "promotion_status": report["promotion_status"],
                "ready_for_review": report["ready_for_review"],
                "output": str(output_path),
            },
            indent=2,
        )
    )
    return 0 if report["ready_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
