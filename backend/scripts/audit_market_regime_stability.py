from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.regime.stability_audit import (  # noqa: E402
    MarketRegimeStabilityAuditConfig,
    build_market_regime_stability_audit,
    write_market_regime_stability_audit_markdown,
)


def main() -> int:
    data_dir = PROJECT_ROOT / "data"
    config = MarketRegimeStabilityAuditConfig(data_dir=data_dir)
    env_check = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if env_check.returncode != 0:
        raise SystemExit("backend/.env is not ignored by Git; aborting audit safety check.")

    report = build_market_regime_stability_audit(
        config=config,
        progress=lambda message: print(f"[market-regime-stability-audit] {message}", flush=True),
    )
    write_market_regime_stability_audit_markdown(report, PROJECT_ROOT / "docs" / "market-regime-stability-audit.md")
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "phase": report["phase"],
                "command": report["command"],
                "ready_for_review": report["ready_for_review"],
                "audit_version": report["audit"]["audit_version"],
                "regime_version": report["audit"]["regime_version"],
                "regime_config_hash": report["audit"]["regime_config_hash"],
                "direct_flips": report["direct_flips"]["observed_count"],
                "flip_quality_result": report["decision"]["flip_quality_result"],
                "confidence_result": report["decision"]["confidence_result"],
                "regime_stability_result": report["decision"]["regime_stability_result"],
                "baseline_decision": report["decision"]["baseline_decision"],
                "regression": report["regression"],
                "processing": report["processing"],
                "outputs": report["outputs"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
