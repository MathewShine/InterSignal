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

from app.strategy.emerging_volume_semantics_audit import (  # noqa: E402
    EmergingVolumeSemanticsAuditConfig,
    build_emerging_volume_semantics_audit,
    write_emerging_volume_semantics_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Emerging RVOL semantics without outcome data.")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()

    env_check = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if env_check.returncode != 0:
        raise SystemExit("backend/.env is not ignored by Git; aborting audit safety check.")

    config = EmergingVolumeSemanticsAuditConfig(
        data_dir=PROJECT_ROOT / "data",
        start_date=args.start_date,
        end_date=args.end_date,
    )
    report = build_emerging_volume_semantics_audit(
        config=config,
        progress=lambda message: print(f"[emerging-volume-semantics] {message}", flush=True),
    )
    write_emerging_volume_semantics_markdown(report, PROJECT_ROOT / "docs" / "emerging-volume-semantics-audit.md")
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "phase": report["phase"],
                "command": report["command"],
                "ready_for_review": report["ready_for_review"],
                "audit_version": report["audit"]["audit_version"],
                "rvol20_role": report["semantics"]["rvol20_role"],
                "semantic_consistency": report["semantic_consistency"],
                "candidate_dataset_unchanged": report["baseline"]["candidate_dataset_unchanged"],
                "feature_dataset_unchanged": report["baseline"]["feature_dataset_unchanged"],
                "processing": report["processing"],
                "outputs": report["outputs"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
