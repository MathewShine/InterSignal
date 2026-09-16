from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Authorize and execute the single, separately classified Family A "
            "post-outcome remediated evaluation."
        )
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.family_a_post_outcome_remediated_validation import (
        execute_post_outcome_remediated_validation,
    )

    result = execute_post_outcome_remediated_validation(args.root)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "evidence_class": result["EVIDENCE_CLASS"],
                "classification": result["POST_OUTCOME_REMEDIATED_RESULT"],
                "generalization_indication": result[
                    "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"
                ],
                "strategy_v2_review_status": result[
                    "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"
                ],
                "result_hash": result["family_a_post_outcome_result_hash"],
                "manifest_hash": result["manifest_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
