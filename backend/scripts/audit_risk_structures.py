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

from app.risk.risk_structure_audit import (  # noqa: E402
    RiskStructureAuditConfig,
    build_risk_structure_audit,
    write_strategy_v1_risk_structure_audit_markdown,
)
from app.services.daily_feature_engine import json_safe  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not git_ignored("backend/.env"):
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1
    if not git_ignored("data/research/audits/risk_structure/v1/risk_structure_stop_candidate_inventory.csv.gz"):
        print(json.dumps({"status": "FAILED", "code": "RISK_STRUCTURE_AUDIT_ARTIFACTS_NOT_IGNORED"}, indent=2))
        return 1

    config = RiskStructureAuditConfig(data_dir=args.data_dir)
    try:
        report = build_risk_structure_audit(
            config=config,
            progress=lambda message: print(f"[risk-structure-audit] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "RISK_STRUCTURE_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_strategy_v1_risk_structure_audit_markdown(report, REPO_ROOT / "docs" / "strategy-v1-risk-structure-audit.md")
    print(json.dumps(json_safe(compact_console_report(report)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit RISK_STRUCTURE_V1 structure without outcome data.")
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
        "risk": report["risk"],
        "baseline_distribution": report["stop_audit"]["baseline_distribution"],
        "why_recent_swing_low_5_wins": report["stop_implementation"]["why_recent_swing_low_5_wins"],
        "target_audit": report["target_audit"],
        "capital_audit": report["capital_audit"],
        "decision": report["decision"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

