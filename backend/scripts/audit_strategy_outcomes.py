from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.daily_feature_engine import json_safe  # noqa: E402
from app.strategy.outcomes.outcome_audit import (  # noqa: E402
    StrategyOutcomeAuditConfig,
    build_strategy_outcome_audit,
    write_outcome_audit_markdown,
)

__test__ = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit STRATEGY_OUTCOME_V1 without changing its frozen methodology."
    )
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    args = parser.parse_args()
    config = StrategyOutcomeAuditConfig(data_dir=args.data_dir)
    required_ignored = (
        "backend/.env",
        relative_repo_path(config.summary_path),
        relative_repo_path(config.report_path("forward_safety")),
        relative_repo_path(config.bulk_dir / "forward_safety_detail.csv.gz"),
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1
    try:
        report = build_strategy_outcome_audit(
            config=config,
            progress=lambda message: print(f"[strategy-outcome-audit-v1] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "STRATEGY_OUTCOME_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2
    write_outcome_audit_markdown(
        report,
        REPO_ROOT / "docs" / "strategy-v1-historical-outcomes-audit.md",
    )
    print(json.dumps(json_safe(compact_report(report)), indent=2))
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


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "VERIFICATION_INCOMPLETE",
        "audit_version": report["audit_version"],
        "baseline": report["baseline"],
        "population": report["population"],
        "classifications": report["classifications"],
        "regression": report["regression"],
        "safety": report["safety"],
        "artifacts": report["artifacts"],
        "runtime_seconds": report["runtime_seconds"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
