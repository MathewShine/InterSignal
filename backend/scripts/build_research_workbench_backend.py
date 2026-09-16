from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research_workbench.builder import build_research_workbench_backend


def main() -> int:
    summary = build_research_workbench_backend(PROJECT_ROOT)
    print(
        json.dumps(
            {
                "command_version": summary["command_version"],
                "command_profile": summary["command_profile"],
                "families": summary["counts"]["families"],
                "strategies": summary["counts"]["strategies"],
                "evidence": summary["counts"]["evidence"],
                "production_candidate_count": summary["counts"][
                    "production_candidate_count"
                ],
                "validated_production_strategy_count": summary["counts"][
                    "validated_production_strategy_count"
                ],
                "integrity_status": summary["integrity"]["status"],
                "research_workbench_backend_hash": summary[
                    "research_workbench_backend_hash"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
