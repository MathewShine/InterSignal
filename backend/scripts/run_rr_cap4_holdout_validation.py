from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.rr_cap4_holdout_validation import (  # noqa: E402
    AUTHORIZATION_REFERENCE,
    FrozenExperimentHashMismatch,
    finalize_validation_review,
    run_one_shot_validation,
)
from app.research.temporal_validation.config import json_ready  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run or review-finalize the one-shot EXP-RRCAL-001 formal holdout validation."
    )
    parser.add_argument("--explicit-user-authorization", action="store_true")
    parser.add_argument("--authorization-reference", default=AUTHORIZATION_REFERENCE)
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    try:
        if args.finalize_review_only:
            summary = finalize_validation_review(
                repo_root=REPO_ROOT,
                tests_passed=args.tests_passed,
                frontend_build_passed=args.frontend_build_passed,
            )
        else:
            summary = run_one_shot_validation(
                repo_root=REPO_ROOT,
                explicit_user_authorized=args.explicit_user_authorization,
                authorization_reference=args.authorization_reference,
                progress=lambda message: print(f"[rr-cap4-validation-v1] {message}", flush=True),
            )
    except FrozenExperimentHashMismatch as exc:
        print(json.dumps({"status": "FAILED", "code": "FROZEN_EXPERIMENT_HASH_MISMATCH", "detail": str(exc)}, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "RR_CAP4_HOLDOUT_VALIDATION_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 3
    print(
        json.dumps(
            json_ready(
                {
                    "validation_version": summary["validation_version"],
                    "validation_record_id": summary["validation_record_id"],
                    "validated_experiment_id": summary["validated_experiment_id"],
                    "state": summary["governance"]["final_state"],
                    "validation_run_count": summary["governance"]["final_run_count"],
                    "validation_result_hash": summary["validation_result_hash"],
                    "classifications": summary["classifications"],
                    "ready_for_review": summary["ready_for_review"],
                }
            ),
            indent=2,
        )
    )
    return 0 if (not args.finalize_review_only or summary["ready_for_review"]) else 4


if __name__ == "__main__":
    raise SystemExit(main())
