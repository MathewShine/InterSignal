from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.backtesting.portfolio_baseline import (  # noqa: E402
    get_current_portfolio_backtest_profile,
    get_current_portfolio_backtest_version,
    get_portfolio_backtest_baseline,
    get_portfolio_backtest_config,
)
from app.backtesting.portfolio_engine import (  # noqa: E402
    PortfolioBacktestEngineConfig,
    build_portfolio_backtest,
    write_portfolio_backtest_markdown,
)

__test__ = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one registered deterministic portfolio backtest for gross-before-costs research."
    )
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--profile", default=get_current_portfolio_backtest_profile())
    parser.add_argument("--version", default=get_current_portfolio_backtest_version())
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    try:
        backtest_config = get_portfolio_backtest_config(profile=args.profile, version=args.version)
        baseline = get_portfolio_backtest_baseline(
            args.data_dir, profile=args.profile, version=args.version
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAILED", "code": "UNREGISTERED_BACKTEST_BASELINE", "detail": str(exc)}, indent=2))
        return 1
    engine_config = PortfolioBacktestEngineConfig(
        data_dir=args.data_dir,
        backtest_config=backtest_config,
        full_generation=not args.pilot_only,
    )
    if (
        engine_config.trades_path != baseline.trades_dataset_path
        or engine_config.daily_path != baseline.daily_dataset_path
        or engine_config.skipped_path != baseline.skipped_dataset_path
    ):
        print(json.dumps({"status": "FAILED", "code": "CURRENT_PORTFOLIO_BASELINE_RESOLUTION_MISMATCH"}, indent=2))
        return 1
    required_ignored = (
        "backend/.env",
        relative_repo_path(engine_config.trades_path),
        relative_repo_path(engine_config.daily_path),
        relative_repo_path(engine_config.skipped_path),
        relative_repo_path(engine_config.report_path("summary.json")),
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        report = build_portfolio_backtest(
            config=engine_config,
            progress=lambda message: print(f"[portfolio-backtest-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "PORTFOLIO_BACKTEST_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    if not args.pilot_only:
        write_portfolio_backtest_markdown(
            report,
            REPO_ROOT / "docs/strategy-v1-portfolio-backtest-foundation.md",
        )
    print(json.dumps(compact_report(report), indent=2, default=str))
    return 0 if report["ready_for_review"] else 3


def relative_repo_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def compact_report(report: dict[str, object]) -> dict[str, object]:
    if not report.get("full_backtest_completed"):
        return {
            "status": "PILOT_PASS" if report["ready_for_review"] else "PILOT_FAILED",
            "pilot": report["pilot"],
        }
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "VERIFICATION_INCOMPLETE",
        "run_metadata": report["run_metadata"],
        "opportunity_pool": report["opportunity_pool"],
        "portfolio_metrics": report["portfolio_metrics"],
        "trade_metrics": report["trade_metrics"],
        "exit_metrics": report["exit_metrics"],
        "skip_reasons": report["skip_reasons"],
        "invariants": report["invariants"],
        "runtime_seconds": report["runtime_seconds"],
        "artifacts": report["artifacts"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
