from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_b_history_remediation import (  # noqa: E402
    build_family_b_history_remediation,
    finalize_family_b_history_remediation_review,
    ingest_history_extension,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Family B development daily-history remediation."
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Acquire only the approved official NSE daily/CA prehistory.",
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument(
        "--backend-tests", choices=("PASSED", "FAILED", "PENDING"), default="PENDING"
    )
    parser.add_argument(
        "--frontend-build", choices=("PASSED", "FAILED", "PENDING"), default="PENDING"
    )
    args = parser.parse_args()
    if args.ingest and args.finalize_review_only:
        parser.error("--ingest and --finalize-review-only are mutually exclusive")
    if args.ingest:
        result = ingest_history_extension(REPO_ROOT)
        display = {
            "daily_sessions": result["daily"]["sessions"],
            "daily_records": result["daily"]["records"],
            "corporate_actions": result["corporate_actions"],
        }
    elif args.finalize_review_only:
        result = finalize_family_b_history_remediation_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
        display = {
            "command_version": result["command_version"],
            "FAMILY_B_HISTORY_REMEDIATION_RESULT": result["decisions"][
                "FAMILY_B_HISTORY_REMEDIATION_RESULT"
            ],
            "FAMILY_B_B002_REEVALUATION_READINESS": result["decisions"][
                "FAMILY_B_B002_REEVALUATION_READINESS"
            ],
            "family_b_sma_readiness_hash": result["family_b_sma_readiness_hash"],
            "ready_for_review": result["verification"]["ready_for_review"],
        }
    else:
        result = build_family_b_history_remediation(REPO_ROOT)
        display = {
            "command_version": result["command_version"],
            "FAMILY_B_HISTORY_REMEDIATION_RESULT": result["decisions"][
                "FAMILY_B_HISTORY_REMEDIATION_RESULT"
            ],
            "FAMILY_B_B002_REEVALUATION_READINESS": result["decisions"][
                "FAMILY_B_B002_REEVALUATION_READINESS"
            ],
            "hashes": result["hashes"],
            "verification": result["verification"],
        }
    print(json.dumps(display, indent=2))


if __name__ == "__main__":
    main()
