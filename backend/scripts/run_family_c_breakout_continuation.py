from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_c_breakout_continuation import (  # noqa: E402
    build_family_c_architecture,
    finalize_family_c_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preregister and structurally validate Family C without performance evaluation."
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
        result = finalize_family_c_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_c_architecture(REPO_ROOT)
    print(
        json.dumps(
            {
                "family_version": result["family_version"],
                "family_status": result["family_status"],
                "data_readiness": result["classifications"][
                    "FAMILY_C_DATA_READINESS"
                ],
                "architecture_result": result["classifications"][
                    "FAMILY_C_ARCHITECTURE_RESULT"
                ],
                "performance_run": result["governance"][
                    "development_performance_run"
                ],
                "validation_accessed": result["governance"][
                    "validation_accessed"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
