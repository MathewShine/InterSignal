from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_c_c001_attribution_audit import (  # noqa: E402
    build_family_c_c001_attribution_audit,
    finalize_family_c_c001_attribution_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen DEVELOPMENT-only Family C C001 attribution audit."
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
        result = finalize_family_c_c001_attribution_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_c_c001_attribution_audit(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "signal_quality": result["signal_cohort"][
                    "C001_SIGNAL_QUALITY_ATTRIBUTION"
                ],
                "capacity_selection": result["capacity"][
                    "C001_CAPACITY_SELECTION_QUALITY"
                ],
                "capacity_materiality": result["capacity"][
                    "C001_CAPACITY_EFFECT_MATERIALITY"
                ],
                "advantage_attribution": result["attribution"][
                    "C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"
                ],
                "next_stage": result["attribution"]["FAMILY_C_C001_NEXT_STAGE"],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
