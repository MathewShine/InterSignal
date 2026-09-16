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
            "Verify the code-only Family A CA lookback remediation without "
            "running validation or calculating performance."
        )
    )
    parser.add_argument("--root", type=Path, default=_project_root())
    args = parser.parse_args()

    backend = args.root.resolve() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.research.strategy.family_a_ca_lookback_remediation import (
        run_ca_lookback_remediation_verification,
    )

    result = run_ca_lookback_remediation_verification(args.root)
    print(
        json.dumps(
            {
                "command_version": result["summary"]["command_version"],
                "remediation_result": result["summary"]["readiness"][
                    "FAMILY_A_CA_REMEDIATION_RESULT"
                ],
                "technical_readiness": result["summary"]["readiness"][
                    "POST_OUTCOME_REMEDIATED_VALIDATION_TECHNICAL_READINESS"
                ],
                "governance_status": result["summary"]["readiness"][
                    "REPLACEMENT_VALIDATION_GOVERNANCE_STATUS"
                ],
                "manifest_hash": result["manifest"][
                    "family_a_ca_lookback_remediation_manifest_hash"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
