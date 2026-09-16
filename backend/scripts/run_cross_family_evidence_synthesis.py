from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.cross_family_evidence_synthesis import (  # noqa: E402
    build_cross_family_evidence_synthesis,
    finalize_cross_family_evidence_synthesis,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synthesize frozen Strategy V1, CAP4, and Family A-G evidence without "
            "running performance or accessing validation data."
        )
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_cross_family_evidence_synthesis(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_cross_family_evidence_synthesis(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "primary_question_result": result["primary_question_result"],
                "family_a_validation_candidacy": result["candidate_selection"]
                ["FAMILY_A_VALIDATION_CANDIDACY"],
                "validation_design_readiness": result["validation_readiness"]
                ["VALIDATION_DESIGN_READINESS"],
                "cross_family_synthesis_hash": result[
                    "cross_family_synthesis_hash"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
