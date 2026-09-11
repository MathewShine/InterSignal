from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.backtesting.portfolio_audit import (  # noqa: E402
    PortfolioBacktestAuditConfig,
    build_portfolio_backtest_audit,
    write_portfolio_backtest_audit_markdown,
)


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def relative_repo_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def compact(report: dict[str, object]) -> dict[str, object]:
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "AUDIT_FAILED",
        "audit_version": report["audit_version"],
        "baseline": report["baseline"],
        "classifications": report["classifications"],
        "chronology": report["chronology"],
        "accounting": report["accounting"],
        "constraints": report["constraints"],
        "ranking_sensitivity": report["ranking"]["sensitivity_classification"],
        "runtime_seconds": report["runtime_seconds"],
        "summary_path": report["summary_path"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit the frozen PORTFOLIO_BACKTEST_V1 mechanics without modifying it."
    )
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    args = parser.parse_args()
    config = PortfolioBacktestAuditConfig(data_dir=args.data_dir)
    ignored_paths = (
        "backend/.env",
        relative_repo_path(config.report_path("summary.json")),
        relative_repo_path(config.bulk_dir / "candidate_reconstruction.csv.gz"),
    )
    missing = [path for path in ignored_paths if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        report = build_portfolio_backtest_audit(
            config,
            progress=lambda message: print(f"[portfolio-backtest-audit-v1] {message}", flush=True),
        )
        write_portfolio_backtest_audit_markdown(
            report,
            REPO_ROOT / "docs/strategy-v1-portfolio-backtest-audit.md",
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "PORTFOLIO_BACKTEST_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps(compact(report), indent=2, default=str))
    return 0 if report["ready_for_review"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
