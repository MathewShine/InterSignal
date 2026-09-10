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
from app.strategy.scoring.score_audit import (  # noqa: E402
    StrategyScoreAuditConfig,
    build_strategy_score_audit,
    write_strategy_score_audit_markdown,
)

__test__ = False


def main() -> int:
    args = build_parser().parse_args()
    required_ignored = (
        "backend/.env",
        "data/reports/strategy_score_v1_audit_summary.json",
        "data/research/audits/strategy_score/v1/strategy_score_audit_violations.csv.gz",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1

    config = StrategyScoreAuditConfig(data_dir=args.data_dir)
    try:
        report = build_strategy_score_audit(
            config=config,
            progress=lambda message: print(f"[strategy-score-audit] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "STRATEGY_SCORE_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_strategy_score_audit_markdown(report, REPO_ROOT / "docs" / "strategy-v1-final-scoring-audit.md")
    print(json.dumps(json_safe(compact_report(report)), indent=2))
    return 0 if report["ready_for_review"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit STRATEGY_SCORE_V1 structurally without outcome data.")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    return parser


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
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "ready_for_review": report["ready_for_review"],
        "audit_version": report["audit_version"],
        "baseline": report["baseline"],
        "invariants": report["invariants"],
        "coverage": report["coverage"],
        "modes_and_gates": report["modes_and_gates"],
        "classifications": report["classifications"],
        "pilot": report["pilot"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

