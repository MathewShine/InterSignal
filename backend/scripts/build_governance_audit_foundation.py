from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.governance_audit.builder import build_governance_audit_foundation


def main() -> int:
    summary = build_governance_audit_foundation(PROJECT_ROOT)
    print(
        json.dumps(
            {
                "command_version": summary["command_version"],
                "command_profile": summary["command_profile"],
                "subjects": summary["counts"]["subjects"],
                "policies": summary["counts"]["policies"],
                "timeline_events": summary["counts"]["timeline_events"],
                "integrity_status": summary["integrity"]["status"],
                "governance_audit_foundation_hash": summary[
                    "governance_audit_foundation_hash"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
