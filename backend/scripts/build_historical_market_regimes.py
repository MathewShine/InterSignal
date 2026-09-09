from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.regime.market_regime import (  # noqa: E402
    MarketRegimeEngineConfig,
    build_historical_market_regimes,
    write_historical_market_regime_markdown,
)
from app.services.daily_feature_engine import json_safe  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = MarketRegimeEngineConfig(
        data_dir=args.data_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        full_generation=not args.pilot_only,
    )
    try:
        report = build_historical_market_regimes(
            config=config,
            progress=lambda message: print(f"[market-regime] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "MARKET_REGIME_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_historical_market_regime_markdown(report, REPO_ROOT / "docs" / "historical-market-regime-engine.md")
    print(json.dumps(json_safe(compact_console_report(report)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build MARKET_REGIME_V1 historical DAILY_EOD regime snapshots.")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 30))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    return parser


def backend_env_is_ignored() -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def compact_console_report(report: dict[str, Any]) -> dict[str, Any]:
    generation = report["generation"]
    distribution = report["daily_distribution"]["regime_state_counts"]
    confidence = report["daily_distribution"]["confidence_counts"]
    return {
        "status": "COMPLETED" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "regime_version": report["methodology"]["regime_version"],
        "config_hash": report["methodology"]["config_hash"],
        "historical_start_date": generation["historical_start_date"],
        "historical_end_date": generation["historical_end_date"],
        "full_generation_completed": generation["full_generation_completed"],
        "total_regime_rows": generation["total_regime_rows"],
        "regime_state_counts": distribution,
        "confidence_counts": confidence,
        "available_weight_distribution": report["daily_distribution"]["available_weight_distribution"],
        "score_distribution": report["daily_distribution"]["normalized_score_distribution"],
        "component_availability": report["component_availability"],
        "pilot": report["pilot"],
        "score_continuity": report["score_continuity"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
