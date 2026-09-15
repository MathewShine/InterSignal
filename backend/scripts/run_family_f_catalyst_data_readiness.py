from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_f_catalyst_data_readiness import (  # noqa: E402
    build_family_f_data_readiness,
    finalize_family_f_data_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Family F historical catalyst data readiness without strategy research."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_f_data_readiness(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_f_data_readiness(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "family_status": result["family_status"],
                "data_readiness": result["FAMILY_F_DATA_READINESS"],
                "preregistration_readiness": result[
                    "FAMILY_F_PREREGISTRATION_READINESS"
                ],
                "family_f_data_readiness_hash": result[
                    "family_f_data_readiness_hash"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
