from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_c_c001_implementation_development import (  # noqa: E402
    build_c1_imp_001_development_evaluation,
    finalize_c1_imp_001_development_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the one frozen DEVELOPMENT evaluation of the C1-IMP-001 "
            "compression-priority capacity ranking."
        )
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument(
        "--backend-targeted-tests",
        choices=("PASSED", "FAILED", "NOT_RUN"),
        default="NOT_RUN",
    )
    parser.add_argument(
        "--backend-full-tests",
        choices=("PASSED", "FAILED", "NOT_RUN"),
        default="NOT_RUN",
    )
    parser.add_argument(
        "--frontend-build",
        choices=("PASSED", "FAILED", "NOT_RUN"),
        default="NOT_RUN",
    )
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_c1_imp_001_development_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_c1_imp_001_development_evaluation(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "experiment_id": result["experiment_id"],
                "development_result": result["C1_IMP_001_DEVELOPMENT_RESULT"],
                "replacement_quality": result[
                    "COMPRESSION_PRIORITY_REPLACEMENT_QUALITY"
                ],
                "next_stage": result["FAMILY_C_C001_POST_IMPLEMENTATION_STAGE"],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
