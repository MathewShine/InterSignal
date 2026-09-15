from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.strategy.family_g_regime_volatility import (  # noqa: E402
    build_family_g_architecture,
    finalize_family_g_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze and structurally verify Family G's quarterly NIFTY 500 "
            "SMA200 participation gate without running strategy performance."
        )
    )
    parser.add_argument("--finalize-review-only", action="store_true")
    parser.add_argument("--backend-targeted-tests", default="NOT_RUN")
    parser.add_argument("--backend-full-tests", default="NOT_RUN")
    parser.add_argument("--frontend-build", default="NOT_RUN")
    args = parser.parse_args()
    if args.finalize_review_only:
        result = finalize_family_g_review(
            REPO_ROOT,
            backend_targeted_tests=args.backend_targeted_tests,
            backend_full_tests=args.backend_full_tests,
            frontend_build=args.frontend_build,
        )
    else:
        result = build_family_g_architecture(REPO_ROOT)
    print(
        json.dumps(
            {
                "family_version": result["family_version"],
                "family_g_config_hash": result["family_g_config_hash"],
                "data_readiness": result["classifications"][
                    "FAMILY_G_DATA_READINESS"
                ],
                "architecture_result": result["classifications"][
                    "FAMILY_G_ARCHITECTURE_RESULT"
                ],
                "ready_for_review": result["verification"]["ready_for_review"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
