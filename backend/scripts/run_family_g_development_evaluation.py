from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.research.strategy.family_g_development_evaluation import (  # noqa: E402
    build_family_g_development_evaluation,
    finalize_family_g_development_review,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen Family G DEVELOPMENT-only evaluation."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.finalize_review_only:
        result = finalize_family_g_development_review(
            ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_g_development_evaluation(ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "control_reproduction": result["control"]["reproduction"][
                    "status"
                ],
                "treatment_result": result["classifications"][
                    "REGIME_G_001_DEVELOPMENT_RESULT"
                ],
                "family_result": result["classifications"][
                    "FAMILY_G_DEVELOPMENT_RESULT"
                ],
                "next_stage": result["classifications"][
                    "FAMILY_G_NEXT_RESEARCH_STAGE"
                ],
                "ready_for_review": result["verification"][
                    "ready_for_review"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
