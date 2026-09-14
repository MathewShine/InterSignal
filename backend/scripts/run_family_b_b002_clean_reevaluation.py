from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_b_b002_clean_reevaluation import (  # noqa: E402
    build_b002_clean_reevaluation,
    finalize_b002_clean_reevaluation_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run frozen MOM-B-002 on remediated DEVELOPMENT history."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument(
        "--backend-tests", choices=("PASSED", "FAILED", "PENDING"), default="PENDING"
    )
    parser.add_argument(
        "--frontend-build", choices=("PASSED", "FAILED", "PENDING"), default="PENDING"
    )
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_b002_clean_reevaluation_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_b002_clean_reevaluation(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "MOM_B_002_CLEAN_REEVALUATION_RESULT": result["decisions"][
                    "MOM_B_002_CLEAN_REEVALUATION_RESULT"
                ],
                "B002_CLEAN_TREND_FILTER_EVIDENCE": result["decisions"][
                    "B002_CLEAN_TREND_FILTER_EVIDENCE"
                ],
                "B002_VALIDATION_DESIGN_READINESS": result["decisions"][
                    "B002_VALIDATION_DESIGN_READINESS"
                ],
                "hashes": {
                    "clean_control_result_hash": result["clean_control_result_hash"],
                    "clean_b002_result_hash": result["clean_b002_result_hash"],
                    "b002_clean_reevaluation_hash": result[
                        "b002_clean_reevaluation_hash"
                    ],
                },
                "verification": result["verification"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
