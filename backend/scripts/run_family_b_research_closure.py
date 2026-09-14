from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_b_research_closure import (  # noqa: E402
    build_family_b_research_closure,
    finalize_family_b_research_closure,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Close and freeze Family B without new performance research."
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
        result = finalize_family_b_research_closure(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_b_research_closure(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "family_status": result["statuses"]["FAMILY_B_RESEARCH_STATUS"],
                "B001_status": result["statuses"]["MOM_B_001_FINAL_STATUS"],
                "B002_status": result["statuses"]["MOM_B_002_FINAL_STATUS"],
                "closure_hash": result["closure"]["family_b_closure_hash"],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
