from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nifty500_membership import query_nifty500_members  # noqa: E402

__test__ = False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = query_nifty500_members(
        as_of_date=args.date,
        history_dir=args.history_dir,
        verbose=args.verbose,
    )
    print(
        json.dumps(
            {
                "as_of_date": result.as_of_date.isoformat(),
                "member_count": result.member_count,
                "membership_status": result.membership_status,
                "source_confidence": result.source_confidence,
                "earliest_reconstructable_date": (
                    result.earliest_reconstructable_date.isoformat()
                    if result.earliest_reconstructable_date
                    else ""
                ),
                "latest_reconstructable_date": (
                    result.latest_reconstructable_date.isoformat()
                    if result.latest_reconstructable_date
                    else ""
                ),
                "reconstructed_from_official_events": result.reconstructed_from_official_events,
                "provenance_summary": result.provenance_summary,
                "symbols": list(result.symbols) if args.verbose else list(result.symbols[:10]),
                "symbols_truncated": not args.verbose and result.member_count > 10,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query point-in-time Nifty 500 membership with coverage metadata."
    )
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--history-dir", type=Path, default=REPO_ROOT / "data" / "reference" / "nifty500" / "history")
    parser.add_argument("--verbose", action="store_true", help="Print all matching symbols instead of a compact preview.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
