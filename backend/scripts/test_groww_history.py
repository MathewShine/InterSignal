from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
__test__ = False

from app.models.ingestion import ASIA_KOLKATA, ImportSummary  # noqa: E402
from app.providers.groww import (  # noqa: E402
    GrowwHistoricalDataError,
    GrowwHistoricalProvider,
    GrowwHistoricalProviderConfig,
    GrowwProviderError,
    GrowwProviderNotConfiguredError,
)
from app.services.historical_ingestion import HistoricalIngestionService  # noqa: E402


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = asyncio.run(run_diagnostic(args))
    except GrowwProviderNotConfiguredError as exc:
        result = {
            "status": "FAILED",
            "code": exc.code,
            "message": "Groww credentials are not configured in backend/.env.",
            "read_only": True,
            "orders_placed": False,
            "persistence_enabled": False,
            "remote_migrations_applied": False,
        }
        print(json.dumps(result, indent=2))
        return 1
    except (GrowwHistoricalDataError, GrowwProviderError) as exc:
        result = {
            "status": "FAILED",
            "code": exc.code,
            "message": str(exc),
            "read_only": True,
            "orders_placed": False,
            "persistence_enabled": False,
            "remote_migrations_applied": False,
        }
        print(json.dumps(result, indent=2))
        return 2
    except Exception as exc:
        result = {
            "status": "FAILED",
            "code": "GROWW_DIAGNOSTIC_FAILED",
            "message": exc.__class__.__name__,
            "read_only": True,
            "orders_placed": False,
            "persistence_enabled": False,
            "remote_migrations_applied": False,
        }
        print(json.dumps(result, indent=2))
        return 2

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASSED" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Groww historical data diagnostic for one NSE cash equity"
    )
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--exchange", default="NSE")
    parser.add_argument("--segment", default="CASH")
    parser.add_argument("--groww-symbol")
    parser.add_argument("--daily-start", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--daily-end", type=date.fromisoformat, default=date(2025, 3, 31))
    parser.add_argument("--intraday-date", type=date.fromisoformat, default=previous_weekday())
    return parser


async def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    trading_symbol = args.symbol.strip().upper()
    exchange = args.exchange.strip().upper()
    segment = args.segment.strip().upper()
    groww_symbol = args.groww_symbol or f"{exchange}-{trading_symbol}"
    settings_config = GrowwHistoricalProviderConfig.from_settings()
    provider = GrowwHistoricalProvider(
        GrowwHistoricalProviderConfig(
            totp_token=settings_config.totp_token,
            totp_secret=settings_config.totp_secret,
            exchange=exchange,
            segment=segment,
            trading_symbol=trading_symbol,
            groww_symbol=groww_symbol,
        )
    )
    service = HistoricalIngestionService()

    daily_summary = await service.ingest_daily_candles(
        provider,
        start=args.daily_start,
        end=args.daily_end,
        dry_run=True,
    )

    intraday_start = datetime.combine(args.intraday_date, time(9, 15), tzinfo=ASIA_KOLKATA)
    intraday_end = datetime.combine(args.intraday_date, time(15, 30), tzinfo=ASIA_KOLKATA)
    intraday_summary = await service.ingest_intraday_candles(
        provider,
        interval="5m",
        start=intraday_start,
        end=intraday_end,
        dry_run=True,
    )

    passed = (
        daily_summary.errors_count == 0
        and intraday_summary.errors_count == 0
        and daily_summary.rows_valid > 0
        and intraday_summary.rows_valid > 0
    )

    return {
        "status": "PASSED" if passed else "FAILED",
        "diagnostic": "groww_history_read_only",
        "symbol": trading_symbol,
        "groww_symbol": groww_symbol,
        "exchange": exchange,
        "segment": segment,
        "read_only": True,
        "orders_placed": False,
        "persistence_enabled": False,
        "remote_migrations_applied": False,
        "daily": compact_summary(daily_summary),
        "intraday_5m": compact_summary(intraday_summary),
        "supported_intervals": provider.get_provider_metadata()["supported_intervals"],
        "interval_limits_days": provider.get_provider_metadata()["interval_limits_days"],
    }


def compact_summary(summary: ImportSummary) -> dict[str, Any]:
    return {
        "status": summary.status,
        "dry_run": summary.dry_run,
        "rows_read": summary.rows_read,
        "rows_valid": summary.rows_valid,
        "rows_rejected": summary.rows_rejected,
        "warnings_count": summary.warnings_count,
        "errors_count": summary.errors_count,
        "source_reference": summary.source_reference,
        "skipped_incomplete_rows": summary.metadata.get("skipped_incomplete_rows", 0),
        "first_candle": summary.metadata.get("first_candle"),
        "last_candle": summary.metadata.get("last_candle"),
        "errors": [
            {
                "code": error.code,
                "message": error.message,
                "row_reference": error.row_reference,
            }
            for error in summary.errors[:5]
        ],
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "row_reference": warning.row_reference,
            }
            for warning in summary.warnings[:5]
        ],
    }


def previous_weekday(reference_date: date | None = None) -> date:
    value = reference_date or date.today()
    value = value - timedelta(days=1)
    while value.weekday() >= 5:
        value = value - timedelta(days=1)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
