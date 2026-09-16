from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conduct the post-research strategy program review without starting a program."
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.post_research_strategy_program_review import (
        build_post_research_strategy_program_review,
    )

    result = build_post_research_strategy_program_review(args.root)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "primary_direction": result["NEXT_PROGRAM_PRIMARY_DIRECTION"],
                "secondary_direction": result["NEXT_PROGRAM_SECONDARY_DIRECTION"],
                "program_status": result["STRATEGY_RESEARCH_PROGRAM_STATUS"],
                "strategy_v2_status": result["STRATEGY_V2_STATUS"],
                "family_h_status": result["FAMILY_H_STATUS"],
                "program_review_hash": result["post_research_program_review_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
