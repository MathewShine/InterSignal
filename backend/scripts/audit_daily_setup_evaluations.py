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

from app.strategy.daily_setup_audit import (  # noqa: E402
    DailySetupAuditConfig,
    build_daily_setup_audit,
    write_daily_setup_audit_markdown,
)

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    config = DailySetupAuditConfig(data_dir=args.data_dir, start_date=args.start_date, end_date=args.end_date)
    try:
        report = build_daily_setup_audit(
            config=config,
            progress=lambda message: print(f"[daily-setup-audit] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "DAILY_SETUP_AUDIT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    write_daily_setup_audit_markdown(report, REPO_ROOT / "docs" / "daily-setup-audit.md")
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit DAILY_SETUP_EVALUATION_V1 setup funnel behavior without outcome data.")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
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
    funnel = report["funnel"]
    return {
        "status": "COMPLETED" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "audit_version": report["audit"]["audit_version"],
        "setup_version": report["audit"]["setup_version"],
        "setup_config_hash": report["audit"]["setup_config_hash"],
        "candidate_version": report["audit"]["candidate_version"],
        "candidate_config_hash": report["audit"]["candidate_config_hash"],
        "feature_version": report["audit"]["feature_version"],
        "candidate_rows": funnel["candidate_rows"],
        "setup_eligible": funnel["setup_eligible"],
        "setup_rejected": funnel["setup_rejected"],
        "overall_pass_rate_pct": funnel["overall_pass_rate_pct"],
        "quality_counts": funnel["quality_counts"],
        "emerging_pass_rate_pct": funnel["emerging_pass_rate_pct"],
        "confirmed_pass_rate_pct": funnel["confirmed_pass_rate_pct"],
        "candle_poor_pct": report["candle_quality"]["poor_pct"],
        "structural_stability": report["structural_stability"],
        "funnel_sanity": report["funnel_sanity"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
