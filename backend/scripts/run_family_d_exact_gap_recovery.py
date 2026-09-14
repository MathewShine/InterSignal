from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_d_exact_gap_recovery import (  # noqa: E402
    run_family_d_exact_gap_recovery,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover only the frozen 217 Family D exact prior20 gaps"
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="freeze the exact population and deterministic retry plan without network access",
    )
    parser.add_argument(
        "--offline-finalize",
        action="store_true",
        help="finalize from already stored exact-retry raw responses",
    )
    parser.add_argument("--throttle-seconds", type=float, default=1.0)
    args = parser.parse_args()
    result = run_family_d_exact_gap_recovery(
        REPO_ROOT,
        plan_only=args.plan_only,
        fetch=not args.offline_finalize and not args.plan_only,
        throttle_seconds=args.throttle_seconds,
        progress=lambda message: print(message, flush=True),
    )
    if args.plan_only:
        print(
            json.dumps(
                {
                    "exact_gap_recovery_config_hash": result["config"]["exact_gap_recovery_config_hash"],
                    "exact_gap_population_hash": result["population"]["exact_gap_population_hash"],
                    "exact_gap_request_plan_hash": result["plan"]["exact_gap_request_plan_hash"],
                    "population_count": result["population"]["population_count"],
                    "request_count": result["plan"]["request_count"],
                    "population_expansion_count": result["plan"]["population_expansion_count"],
                    "network_requests": 0,
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "FAMILY_D_EXACT_GAP_RECOVERY_RESULT",
                        "FAMILY_D_DATA_READINESS",
                        "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS",
                    )
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
