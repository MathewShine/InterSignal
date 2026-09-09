from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.strategy.momentum_candidate_audit import (  # noqa: E402
    MomentumCandidateAuditConfig,
    build_momentum_candidate_audit,
    write_momentum_candidate_audit_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MOMENTUM_CANDIDATES_V1 without future outcomes.")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / "data"
    config = MomentumCandidateAuditConfig(data_dir=data_dir, start_date=args.start_date, end_date=args.end_date)
    env_check = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if env_check.returncode != 0:
        raise SystemExit("backend/.env is not ignored by Git; aborting audit safety check.")

    report = build_momentum_candidate_audit(
        config=config,
        progress=lambda message: print(f"[momentum-candidate-audit] {message}", flush=True),
    )
    write_momentum_candidate_audit_markdown(report, PROJECT_ROOT / "docs" / "momentum-candidate-audit.md")
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "phase": report["phase"],
                "command": report["command"],
                "ready_for_review": report["ready_for_review"],
                "audit_version": report["audit"]["audit_version"],
                "candidate_dataset_unchanged": report["baseline"]["candidate_dataset_unchanged"],
                "feature_dataset_unchanged": report["baseline"]["feature_dataset_unchanged"],
                "funnel_sanity_status": report["funnel_sanity"]["status"],
                "parameter_stability": report["sensitivity"]["parameter_stability_assessment"],
                "processing": report["processing"],
                "outputs": report["outputs"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
