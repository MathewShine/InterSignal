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

from app.risk.risk_config import resolve_current_risk_structure_dataset  # noqa: E402
from app.risk.risk_structure_v1_1 import (  # noqa: E402
    RiskStructureV11EngineConfig,
    build_risk_structures_v1_1,
    write_risk_structure_v11_markdown,
)
from app.services.daily_feature_engine import json_safe  # noqa: E402

__test__ = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and compare RISK_STRUCTURE_V1_1 without overwriting V1.")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()

    required_ignored = (
        "backend/.env",
        resolve_current_risk_structure_dataset(REPO_ROOT / "data").relative_to(REPO_ROOT).as_posix(),
        "data/reports/risk_structure_v1_1_summary.json",
    )
    missing = [path for path in required_ignored if not git_ignored(path)]
    if missing:
        print(json.dumps({"status": "FAILED", "code": "REQUIRED_PATH_NOT_IGNORED", "paths": missing}, indent=2))
        return 1

    config = RiskStructureV11EngineConfig(data_dir=args.data_dir, full_generation=not args.pilot_only)
    try:
        report = build_risk_structures_v1_1(
            config=config,
            progress=lambda message: print(f"[risk-structure-v1.1] {message}", flush=True),
        )
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "code": "RISK_STRUCTURE_V1_1_BUILD_FAILED", "message": exc.__class__.__name__, "detail": str(exc)}, indent=2))
        return 2

    write_risk_structure_v11_markdown(report, REPO_ROOT / "docs" / "strategy-v1-risk-structure-v1-1.md")
    print(json.dumps(json_safe(compact_report(report)), indent=2))
    return 0 if report["pilot"]["passed"] else 3


def git_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", path], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return result.returncode == 0


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "PILOT_COMPLETED" if report["pilot"]["passed"] else "FAILED",
        "ready_for_review": report["ready_for_review"],
        "risk": report["risk"],
        "pilot": report["pilot"],
        "comparison": report["comparison"],
        "results": report["results"],
        "target_regression": report["target_regression"],
        "capital_regression": report["capital_regression"],
        "invariant_counts": {
            "final_ready": len(report["invariants"]["final_ready_violations"]),
            "conditional_preview": len(report["invariants"]["conditional_preview_violations"]),
        },
        "generation": report["generation"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
