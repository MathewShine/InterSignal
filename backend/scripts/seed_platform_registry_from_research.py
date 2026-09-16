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
            "Seed the local immutable platform registry with references to frozen "
            "A-G research artifacts."
        )
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.platform.seeding import build_platform_foundation

    result = build_platform_foundation(args.root)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "command_profile": result["command_profile"],
                "strategies_seeded": result["counts"]["strategies"],
                "evidence_seeded": result["counts"]["evidence"],
                "production_candidate_count": result["counts"][
                    "production_candidate_count"
                ],
                "validated_production_strategy_count": result["counts"][
                    "validated_production_strategy_count"
                ],
                "platform_foundation_hash": result["platform_foundation_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
