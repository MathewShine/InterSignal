from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.research.intraday.resume_ingestion import ResumeMode, run_development_intraday_resume


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resume or verify only the frozen Command 05 DEVELOPMENT intraday request plan"
    )
    parser.add_argument("--mode", choices=[str(value) for value in ResumeMode], default=str(ResumeMode.VERIFY))
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--frontend-build-passed", action="store_true")
    args = parser.parse_args()
    report = run_development_intraday_resume(
        repo_root=REPO_ROOT,
        mode=args.mode,
        tests_passed=args.tests_passed,
        frontend_build_passed=args.frontend_build_passed,
        progress=lambda message: print(f"[development-intraday-resume-05b] {message}", flush=True),
    )
    print(
        json.dumps(
            {
                "command_version": report["command_version"],
                "profile": report["profile"],
                "mode": report["mode"],
                "classifications": report["classifications"],
                "complete_requests": report["retrieval"]["final_complete"],
                "network_attempts": report["transport"]["network_attempts"],
                "normalized_5m_rows": report["datasets"]["normalized_5m_rows"],
                "ready_for_review": report["ready_for_review"],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
