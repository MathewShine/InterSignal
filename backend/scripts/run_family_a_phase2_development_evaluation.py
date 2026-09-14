from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_a_phase2_development_evaluation import (  # noqa: E402
    build_family_a_phase2_development_evaluation,
    finalize_phase2_development_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the two frozen Family A Phase 2 experiments on DEVELOPMENT only."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-tests", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    parser.add_argument("--frontend-build", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_phase2_development_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_a_phase2_development_evaluation(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "a2_001_result": result["experiments"]["A2-001"]["classifications"][
                    "A2_001_DEVELOPMENT_RESULT"
                ],
                "a2_002_result": result["experiments"]["A2-002"]["classifications"][
                    "A2_002_DEVELOPMENT_RESULT"
                ],
                "family_phase2_result": result["classifications"]["FAMILY_A_PHASE2_RESULT"],
                "next_stage": result["classifications"]["FAMILY_A_NEXT_RESEARCH_STAGE"],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
