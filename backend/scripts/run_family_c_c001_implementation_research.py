from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_c_c001_implementation_research import (  # noqa: E402
    build_family_c_c001_implementation_research,
    finalize_family_c_c001_implementation_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preregister the one-change Family C C001 implementation experiment."
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
        result = finalize_family_c_c001_implementation_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_c_c001_implementation_research(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "experiment_id": result["preregistration"]["experiment_id"],
                "architecture_result": result["classifications"][
                    "C1_IMP_001_ARCHITECTURE_RESULT"
                ],
                "signal_set_equal": result["signal_set"]["equal"],
                "performance_run": result["performance"]["performance_run"],
                "validation_accessed": result["governance_prohibitions"][
                    "validation_accessed"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
