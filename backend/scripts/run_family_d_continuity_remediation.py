from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_d_continuity_remediation import (  # noqa: E402
    run_family_d_continuity_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair frozen Family D prior20 intraday continuity")
    parser.add_argument("--plan-only", action="store_true", help="freeze the deterministic plan without network access")
    parser.add_argument("--offline-finalize", action="store_true", help="finalize from existing raw sources without network access")
    parser.add_argument("--throttle-seconds", type=float, default=1.0)
    args = parser.parse_args()
    result = run_family_d_continuity_remediation(
        REPO_ROOT,
        plan_only=args.plan_only,
        fetch=not args.offline_finalize and not args.plan_only,
        throttle_seconds=args.throttle_seconds,
        progress=lambda message: print(message, flush=True),
    )
    if args.plan_only:
        plan = result["plan"]
        print(
            json.dumps(
                {
                    "continuity_remediation_config_hash": result["config"]["continuity_remediation_config_hash"],
                    "continuity_request_plan_hash": plan["continuity_request_plan_hash"],
                    "target_session_count": plan["target_session_count"],
                    "total_required_prior_session_references": plan["total_required_prior_session_references"],
                    "unique_missing_symbol_sessions_before_remediation": plan["unique_missing_symbol_sessions_before_remediation"],
                    "request_count": plan["request_count"],
                    "earliest_requested_date": plan["earliest_requested_date"],
                    "latest_requested_date": plan["latest_requested_date"],
                    "network_requests": 0,
                },
                indent=2,
            )
        )
    else:
        print(json.dumps({key: result[key] for key in ("FAMILY_D_CONTINUITY_REMEDIATION_RESULT", "FAMILY_D_DATA_READINESS", "FAMILY_D_ARCHITECTURE_RESULT", "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
