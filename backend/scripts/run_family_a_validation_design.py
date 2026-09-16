from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_a_validation_design import (  # noqa: E402
    build_family_a_validation_design,
    finalize_family_a_validation_design,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Design and seal the exact frozen Family A one-shot validation protocol "
            "without running validation or reading validation outcomes."
        )
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    parser.add_argument("--regressions", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_a_validation_design(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
            regressions=args.regressions,
        )
    else:
        result = build_family_a_validation_design(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "candidate_id": result["candidate_identity"]["candidate_id"],
                "data_readiness": result["data_readiness"][
                    "FAMILY_A_VALIDATION_DATA_READINESS"
                ],
                "one_shot_readiness": result["governance"][
                    "FAMILY_A_ONE_SHOT_VALIDATION_READINESS"
                ],
                "lifecycle": result["governance"]["current_lifecycle"],
                "validation_run_count": result["governance"][
                    "validation_run_count"
                ],
                "family_a_validation_design_hash": result[
                    "family_a_validation_design_hash"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
