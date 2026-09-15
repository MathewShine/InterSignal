from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_g_benchmark_prehistory import (  # noqa: E402
    acquire_official_prehistory,
    build_family_g_benchmark_prehistory,
    finalize_family_g_benchmark_prehistory,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extend the same official NIFTY 500 series for Family G SMA200 "
            "prehistory and rerun structural readiness only."
        )
    )
    parser.add_argument("--retrieve", action="store_true")
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_g_benchmark_prehistory(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        if args.retrieve:
            acquire_official_prehistory(REPO_ROOT)
        result = build_family_g_benchmark_prehistory(REPO_ROOT)
    print(
        json.dumps(
            {
                "command_version": result["command_version"],
                "data_readiness": result["classifications"][
                    "FAMILY_G_DATA_READINESS"
                ],
                "architecture_result": result["classifications"][
                    "FAMILY_G_ARCHITECTURE_RESULT"
                ],
                "development_backtest_readiness": result["classifications"][
                    "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
