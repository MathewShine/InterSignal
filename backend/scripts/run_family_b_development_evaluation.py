from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_b_development_evaluation import (  # noqa: E402
    build_family_b_development_evaluation,
    finalize_family_b_development_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen Family B development-only evaluation."
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
        result = finalize_family_b_development_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_b_development_evaluation(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "MOM_B_001_DEVELOPMENT_RESULT": result["classifications"][
                    "MOM_B_001_DEVELOPMENT_RESULT"
                ],
                "MOM_B_002_DEVELOPMENT_RESULT": result["classifications"][
                    "MOM_B_002_DEVELOPMENT_RESULT"
                ],
                "FAMILY_B_DEVELOPMENT_RESULT": result["classifications"][
                    "FAMILY_B_DEVELOPMENT_RESULT"
                ],
                "FAMILY_B_NEXT_RESEARCH_STAGE": result["classifications"][
                    "FAMILY_B_NEXT_RESEARCH_STAGE"
                ],
                "result_hashes": result["result_hashes"],
                "development_registry_hash": result["development_registry_hash"],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
