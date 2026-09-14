from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_a_development_backtest import (  # noqa: E402
    build_family_a_development_backtests,
    finalize_development_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run exactly the three preregistered Family A development baselines."
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-tests", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    parser.add_argument("--frontend-build", choices=("PASSED", "FAILED", "PENDING"), default="PENDING")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_development_review(
            REPO_ROOT,
            backend_tests=args.backend_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_a_development_backtests(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "family_config_hash": result["family_config_hash"],
                "family_result": result["classifications"]["FAMILY_A_DEVELOPMENT_RESULT"],
                "phase2_candidate": result["classifications"]["FAMILY_A_PHASE2_AUTHORIZATION_CANDIDATE"],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
