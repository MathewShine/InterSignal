from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nifty500_membership import build_membership_foundation  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        coverage = build_membership_foundation(
            output_dir=args.output_dir,
            target_start_date=args.start_date,
            target_end_date=args.end_date,
            max_press_release_sources=args.max_press_release_sources,
            download_source_documents=not args.skip_document_download,
            refresh_press_release_index=args.refresh_press_release_index,
            request_delay_seconds=args.request_delay,
            timeout_seconds=args.timeout,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "code": "NIFTY500_MEMBERSHIP_BUILD_FAILED", "message": exc.__class__.__name__},
                indent=2,
            )
        )
        return 2

    print(json.dumps(compact_report(coverage), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build current and historical Nifty 500 membership foundation from official sources."
    )
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--max-press-release-sources", type=int, default=0)
    parser.add_argument("--skip-document-download", action="store_true")
    parser.add_argument("--refresh-press-release-index", action="store_true")
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def compact_report(coverage: dict) -> dict:
    return {
        "status": "COMPLETED",
        "phase": coverage["phase"],
        "current_constituent_count": coverage["current_snapshot"]["constituent_count"],
        "official_documents": coverage["official_documents"],
        "membership_events": coverage["membership_events"],
        "membership_periods": coverage["membership_periods"],
        "review_cycle_coverage": {
            "expected_cycles": coverage["review_cycle_coverage"]["expected_cycles"],
            "covered_cycles": coverage["review_cycle_coverage"]["covered_cycles"],
        },
        "manual_review": coverage["manual_review"],
        "symbol_resolution": {
            "identity_alias_count": coverage["symbol_resolution"]["identity_alias_count"],
            "unresolved_company_symbol_mappings": coverage["symbol_resolution"]["unresolved_company_symbol_mappings"],
        },
        "reconciliation": {
            "rows_with_count_differences": coverage["reconciliation"]["rows_with_count_differences"],
            "lifecycle_anomalies": len(coverage["reconciliation"]["event_application_anomalies"]),
            "updated_query_counts": coverage["reconciliation"]["updated_query_counts"],
        },
        "survivorship_bias_status": coverage["survivorship_bias_status"],
        "storage": coverage["storage"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
