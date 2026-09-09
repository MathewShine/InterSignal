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
from app.strategy.entry_evaluation_audit import (  # noqa: E402
    EntryEvaluationAuditConfig,
    build_entry_evaluation_audit,
    write_entry_evaluation_audit_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not git_ignored("backend/.env"):
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1
    if not git_ignored("data/research/audits/entry_evaluation/v1/probe.csv"):
        print(json.dumps({"status": "FAILED", "code": "ENTRY_AUDIT_ARTIFACTS_NOT_IGNORED"}, indent=2))
        return 1

    config = EntryEvaluationAuditConfig(data_dir=args.data_dir)
    try:
        report = build_entry_evaluation_audit(
            config=config,
            progress=lambda message: print(f"[entry-audit] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "ENTRY_EVALUATION_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_entry_evaluation_audit_markdown(report, REPO_ROOT / "docs" / "strategy-v1-entry-evaluation-audit.md")
    print(json.dumps(json_safe(compact_console_report(report)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit ENTRY_EVALUATION_V1 structural selectivity without outcomes.")
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


def compact_console_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "COMPLETED" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "audit_version": report["audit_version"],
        "entry_verification": report["entry_verification"],
        "baseline_unchanged": report["baseline_unchanged"],
        "funnel": report["funnel"],
        "cohorts": report["cohorts"]["cohorts"],
        "regime_setup_eligible_progression": report["regime_selectivity"]["setup_eligible_progression"],
        "exceptional_longs": report["exceptional_longs"],
        "penalty_invariants": {
            "active_blocking_rows": report["penalties"]["active_blocking_rows"],
            "not_ready_rows": report["penalties"]["not_ready_rows"],
            "blocking_minus_not_ready": report["penalties"]["blocking_minus_not_ready"],
            "blocking_by_readiness": report["penalties"]["blocking_by_readiness"],
            "critical_invariant_violations": report["penalties"]["critical_invariant_violations"],
            "gate_readiness_violations": report["penalties"]["gate_readiness_violations"],
        },
        "results": report["results"],
        "sensitivity": report["sensitivity"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
