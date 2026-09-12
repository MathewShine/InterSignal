from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.backtesting.costs.cost_engine import build_transaction_cost_research  # noqa: E402

__test__ = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply pre-registered transaction-cost overlays to the frozen portfolio baseline."
    )
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    costed_trades_ignore_path = Path(
        "data", "research", "backtests", "swing", "portfolio", "v1_costed",
        "portfolio_trades_costed_v1.csv.gz",
    ).as_posix()
    required_ignored = (
        "backend/.env",
        "data/research/costs/v1/registry/cost_model_config_v1.json",
        costed_trades_ignore_path,
        "data/reports/transaction_cost_v1_summary.json",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(
            json.dumps(
                {"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing},
                indent=2,
            )
        )
        return 1
    try:
        report = build_transaction_cost_research(
            repo_root=REPO_ROOT,
            tests_passed=args.tests_passed,
            frontend_build_passed=args.frontend_build_passed,
            progress=lambda message: print(f"[transaction-cost-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "TRANSACTION_COST_RESEARCH_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps(compact_report(report), indent=2, default=str))
    return 0 if report["ready_for_review"] else 3


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
    scenarios = []
    for source in report["scenarios"]:
        row = dict(source)
        cash = dict(row["cash_feasibility"])
        cash.pop("violations", None)
        row["cash_feasibility"] = cash
        scenarios.append(row)
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "VERIFICATION_INCOMPLETE",
        "cost_model_version": report["cost_model_version"],
        "cost_profile": report["cost_profile"],
        "cost_config_hash": report["cost_config_hash"],
        "classifications": report["classifications"],
        "zero_cost_reproduction": report["zero_cost_reproduction"],
        "scenarios": scenarios,
        "reconciliation": report["reconciliation"],
        "runtime_seconds": report["runtime_seconds"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
