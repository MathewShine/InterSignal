from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only Family A post-validation CA eligibility audit."
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()

    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.family_a_post_validation_ca_audit import (
        run_post_validation_ca_audit,
    )

    result = run_post_validation_ca_audit(args.root)
    print(
        json.dumps(
            {
                "command_version": result["summary"]["command_version"],
                "root_cause": result["summary"]["root_cause"][
                    "FAMILY_A_CA_VALIDATION_ROOT_CAUSE"
                ],
                "manifest_hash": result["manifest"][
                    "family_a_post_validation_ca_audit_manifest_hash"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
