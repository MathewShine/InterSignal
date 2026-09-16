from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_a_one_shot_validation import (  # noqa: E402
    authorize_replacement_run,
    authorize_one_shot,
    execute_one_shot_validation,
    finalize_one_shot_validation_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Authorize, execute, or finalize review metadata for the single governed "
            "formal Family A validation run."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--authorize-only", action="store_true")
    mode.add_argument("--authorize-replacement-only", action="store_true")
    mode.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    parser.add_argument("--regressions", default="NOT_RUN")
    args = parser.parse_args()

    if args.authorize_only:
        result = authorize_one_shot(REPO_ROOT)
        output = {
            "authorization_version": result["authorization_version"],
            "authorization_hash": result[
                "family_a_validation_authorization_hash"
            ],
            "lifecycle": result["lifecycle_after"],
            "validation_run_count": result["run_count_before"],
        }
    elif args.authorize_replacement_only:
        result = authorize_replacement_run(REPO_ROOT)
        output = {
            "replacement_authorization_version": result[
                "replacement_authorization_version"
            ],
            "replacement_authorization_hash": result[
                "family_a_validation_replacement_authorization_hash"
            ],
            "lifecycle": result["lifecycle"],
            "attempt_number": result["attempt_number"],
        }
    elif args.finalize_review_only:
        result = finalize_one_shot_validation_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
            regressions=args.regressions,
        )
        output = {
            "command_version": result["command_version"],
            "validation_result": result["VALIDATION_RESULT"],
            "lifecycle": result["lifecycle"],
            "validation_run_count": result["validation_run_count"],
            "ready_for_review": result["verification"]["ready_for_review"],
        }
    else:
        result = execute_one_shot_validation(REPO_ROOT)
        output = {
            "command_version": result["command_version"],
            "validation_result": result["VALIDATION_RESULT"],
            "generalization_result": result["FAMILY_A_GENERALIZATION_RESULT"],
            "strategy_v2_advancement_status": result[
                "STRATEGY_V2_ADVANCEMENT_STATUS"
            ],
            "lifecycle": result["lifecycle"],
            "validation_run_count": result["validation_run_count"],
            "remaining_formal_runs": result["remaining_formal_runs"],
            "result_hash": result["family_a_validation_result_hash"],
            "manifest_hash": result["manifest_hash"],
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
