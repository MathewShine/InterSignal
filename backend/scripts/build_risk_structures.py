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

from app.risk.risk_structurer import (  # noqa: E402
    RiskStructureEngineConfig,
    build_risk_structures,
)
from app.risk.risk_config import (  # noqa: E402
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_VERSION,
    RiskStructureConfig,
    normalize_risk_structure_version,
    resolve_risk_structure_dataset,
)
from app.risk.risk_structure_v1_1 import (  # noqa: E402
    RiskStructureV11EngineConfig,
    build_risk_structures_v1_1,
    write_risk_structure_v11_markdown,
)
from app.services.daily_feature_engine import json_safe  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not git_ignored("backend/.env"):
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1
    version = normalize_risk_structure_version(args.version)
    dataset_path = resolve_risk_structure_dataset(args.data_dir, version)
    try:
        ignored_path = dataset_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        ignored_path = dataset_path.as_posix()
    if not git_ignored(ignored_path):
        print(json.dumps({"status": "FAILED", "code": "RISK_STRUCTURE_DATASET_NOT_IGNORED"}, indent=2))
        return 1

    try:
        if version == RISK_STRUCTURE_VERSION:
            report = build_risk_structures(
                config=RiskStructureEngineConfig(
                    data_dir=args.data_dir,
                    risk_config=RiskStructureConfig(),
                    full_generation=not args.pilot_only,
                ),
                progress=lambda message: print(f"[risk-structure-v1-historical] {message}", flush=True),
            )
        else:
            report = build_risk_structures_v1_1(
                config=RiskStructureV11EngineConfig(data_dir=args.data_dir, full_generation=not args.pilot_only),
                progress=lambda message: print(f"[risk-structure-current] {message}", flush=True),
            )
            write_risk_structure_v11_markdown(report, REPO_ROOT / "docs" / "strategy-v1-risk-structure-v1-1.md")
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "RISK_STRUCTURE_BUILD_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    print(json.dumps(json_safe(compact_console_report(report, version=version)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the current risk structure baseline; use --version v1 for historical reproduction.")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument(
        "--version",
        choices=("current", "v1", "v1_1"),
        default="current",
        help=f"Risk methodology to build (default: current -> {CURRENT_RISK_STRUCTURE_VERSION}).",
    )
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


def compact_console_report(report: dict[str, Any], *, version: str) -> dict[str, Any]:
    if version == CURRENT_RISK_STRUCTURE_VERSION:
        return {
            "status": "READY_FOR_REVIEW" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
            "phase": report["phase"],
            "command": report["command"],
            "ready_for_review": report["ready_for_review"],
            "risk": report["risk"],
            "results": report["results"],
            "generation": report["generation"],
            "regression": report["regression"],
            "safety": report["safety"],
            "outputs": report["outputs"],
        }
    generation = report["generation"]
    return {
        "status": "COMPLETED" if report["ready_for_review"] else "COMPLETED_WITH_LIMITATIONS",
        "phase": report["phase"],
        "command": report["command"],
        "ready_for_review": report["ready_for_review"],
        "risk_version": report["risk"]["risk_version"],
        "risk_config_hash": report["risk"]["risk_config_hash"],
        "risk_availability": report["risk"]["risk_availability"],
        "decision_use": report["risk"]["decision_use"],
        "input_versions": report["inputs"]["versions"],
        "input_hashes_before": report["inputs"]["hashes_before"],
        "input_hashes_after": report["inputs"]["hashes_after"],
        "full_generation_completed": generation["full_generation_completed"],
        "total_rows_risk_evaluated": generation["total_rows_risk_evaluated"],
        "valid_stop_count": generation["valid_stop_count"],
        "valid_stop_rate_pct": generation["valid_stop_rate_pct"],
        "rr_1_5_count": generation["rr_1_5_count"],
        "rr_2_0_count": generation["rr_2_0_count"],
        "capital_valid_count": generation["capital_valid_count"],
        "ready_for_final_scoring_count": generation["ready_for_final_scoring_count"],
        "risk_rejected_count": generation["risk_rejected_count"],
        "risk_readiness_counts": generation["risk_readiness_counts"],
        "pilot": report["pilot"],
        "regression": report["regression"],
        "safety": report["safety"],
        "processing": report["processing"],
        "outputs": report["outputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
