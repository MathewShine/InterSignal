from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_b_attribution_audit import (  # noqa: E402
    build_family_b_attribution_audit,
    finalize_family_b_attribution_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen Family B development attribution audit."
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
        result = finalize_family_b_attribution_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_b_attribution_audit(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "B001_CONTROL_EQUIVALENCE_RESULT": result["B001"][
                    "B001_CONTROL_EQUIVALENCE_RESULT"
                ],
                "B001_DISTINCT_FILTER_EVIDENCE": result["B001"][
                    "B001_DISTINCT_FILTER_EVIDENCE"
                ],
                "B002_TREND_FILTER_EVIDENCE": result["B002"][
                    "B002_TREND_FILTER_EVIDENCE"
                ],
                "B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION": result["B002"][
                    "B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"
                ],
                "FAMILY_B_VALIDATION_DESIGN_READINESS": result["decision"][
                    "FAMILY_B_VALIDATION_DESIGN_READINESS"
                ],
                "family_b_attribution_audit_hash": result[
                    "family_b_attribution_audit_hash"
                ],
                "validation_accessed": result["governance"]["validation_accessed"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
