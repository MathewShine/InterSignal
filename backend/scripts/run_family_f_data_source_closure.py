from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_f_data_source_closure import (  # noqa: E402
    build_family_f_data_source_closure,
    finalize_family_f_data_source_closure,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze Family F pending authorized historical catalyst-data access; "
            "no acquisition, strategy, or performance research is performed."
        )
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_f_data_source_closure(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_f_data_source_closure(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "research_status": result["statuses"]["FAMILY_F_RESEARCH_STATUS"],
                "performance_status": result["statuses"][
                    "FAMILY_F_PERFORMANCE_STATUS"
                ],
                "family_f_closure_hash": result["family_f_closure_hash"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
