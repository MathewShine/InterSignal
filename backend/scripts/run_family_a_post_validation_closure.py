from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Close Family A and the A-G discovery cycle without performance execution."
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.family_a_post_validation_closure import (
        build_family_a_post_validation_closure,
    )

    result = build_family_a_post_validation_closure(args.root)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "family_a_candidate_status": result["candidate_final_status"],
                "family_a_strategy_v2_candidacy": result[
                    "family_a_strategy_v2_candidacy"
                ],
                "a_to_g_final_status": result["a_to_g_final_status"],
                "next_planned_phase": result["next_phase_planning"][
                    "NEXT_PLANNED_PHASE"
                ],
                "closure_hash": result["family_a_post_validation_closure_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
