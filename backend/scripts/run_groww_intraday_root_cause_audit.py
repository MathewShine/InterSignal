from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.root_cause_audit import build_groww_intraday_root_cause_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit existing Command 05 Groww reconciliation and retrieval evidence without provider calls"
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    report = build_groww_intraday_root_cause_audit(
        repo_root=REPO_ROOT,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[groww-audit-05a] {message}", flush=True),
    )
    print(
        json.dumps(
            {
                "audit_version": report["audit_version"],
                "profile": report["profile"],
                "classifications": report["classifications"],
                "comparable_sessions": report["reconciliation"]["comparable_sessions"],
                "material_price_mismatches": report["reconciliation"]["material_price_mismatches"],
                "provider_requests_made": report["governance"]["provider_requests_made"],
                "ready_for_review": report["ready_for_review"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
