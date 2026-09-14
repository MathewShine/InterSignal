from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_a_momentum import (  # noqa: E402
    build_family_a_architecture,
    finalize_family_a_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the preregistered Family A momentum architecture without performance evaluation."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-tests", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    parser.add_argument("--frontend-build", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_a_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_a_architecture(REPO_ROOT)
    print(
        json.dumps(
            {
                "family_version": result["family_version"],
                "family_config_hash": result["family_config_hash"],
                "experiment_ids": result["experiment_ids"],
                "data_readiness": result["classifications"]["FAMILY_A_DATA_READINESS"],
                "architecture_result": result["classifications"]["FAMILY_A_ARCHITECTURE_RESULT"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
