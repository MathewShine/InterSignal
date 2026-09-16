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
            "Freeze the InterSignal Month-1 product-platform charter without "
            "starting implementation."
        )
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()
    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.product_platform_charter import (
        build_product_platform_charter,
    )

    result = build_product_platform_charter(args.root)
    modules = result["components"]["priorities"]["modules"]
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "command_profile": result["command_profile"],
                "product_vision": result["product_vision"],
                "p0_modules": [
                    row["module"] for row in modules if row["priority"] == "P0"
                ],
                "implementation_started": result["implementation_started"],
                "product_platform_charter_hash": result[
                    "product_platform_charter_hash"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
