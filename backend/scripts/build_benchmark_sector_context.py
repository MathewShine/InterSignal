from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.providers.indices import (  # noqa: E402
    BENCHMARK_CONTEXT_VERSION,
    BENCHMARK_INDEXES,
    INDUSTRY_TO_SECTOR_INDEX_ID,
    PRIMARY_BENCHMARK_ID,
    SECTOR_CONTEXT_VERSION,
    SUPPORTED_SECTOR_INDEX_NAMES,
    IndexDailyRecord,
    IndexDefinition,
    NSEOfficialIndexHistoryProvider,
    canonical_index_id,
)
from app.services.daily_feature_engine import (  # noqa: E402
    load_trading_sessions,
    parse_date,
    read_csv,
    write_csv,
    write_json,
)

__test__ = False

BENCHMARK_DAILY_FIELDS = [
    "trading_date",
    "benchmark_id",
    "index_name",
    "open",
    "high",
    "low",
    "close",
    "source",
    "source_reference",
    "source_date",
    "methodology",
    "benchmark_context_version",
]

SECTOR_INDEX_DAILY_FIELDS = [
    "trading_date",
    "sector_index_id",
    "index_name",
    "close",
    "source",
    "source_reference",
    "coverage_start",
    "coverage_end",
    "methodology",
    "sector_context_version",
]

SECTOR_INVENTORY_FIELDS = [
    "sector_index_id",
    "index_name",
    "category",
    "source_reference",
    "configured",
    "discovered_live",
    "usable",
    "available_sessions",
    "coverage_percent",
]

SECTOR_MAPPING_FIELDS = [
    "symbol",
    "isin",
    "sector_name",
    "sector_index_id",
    "valid_from",
    "valid_to",
    "mapping_source",
    "mapping_status",
    "confidence",
    "notes",
]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not backend_env_is_ignored():
        print(json.dumps({"status": "FAILED", "code": "BACKEND_ENV_NOT_IGNORED"}, indent=2))
        return 1

    started = time.perf_counter()
    config = ContextBuilderConfig(data_dir=args.data_dir, start_date=args.start_date, end_date=args.end_date)
    try:
        report = build_benchmark_sector_context(
            config=config,
            force_refresh=args.force_refresh,
            progress=lambda message: print(f"[index-context] {message}", flush=True),
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "BENCHMARK_SECTOR_CONTEXT_FAILED",
                    "message": exc.__class__.__name__,
                    "detail": str(exc),
                },
                indent=2,
            )
        )
        return 2

    report["processing"]["duration_seconds"] = round(time.perf_counter() - started, 3)
    write_json(config.benchmark_context_summary_path, report["benchmark_context"])
    write_json(config.sector_context_summary_path, report["sector_context"])
    write_benchmark_sector_markdown(report, REPO_ROOT / "docs" / "benchmark-and-sector-context.md")
    print(json.dumps(compact_console_report(report), indent=2))
    return 0


class ContextBuilderConfig:
    def __init__(self, *, data_dir: Path, start_date: date, end_date: date) -> None:
        self.data_dir = data_dir
        self.start_date = start_date
        self.end_date = end_date

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "raw"

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "reference" / "nse" / "indices" / "normalized"

    @property
    def benchmark_daily_path(self) -> Path:
        return self.normalized_dir / "benchmark_daily.csv"

    @property
    def sector_index_daily_path(self) -> Path:
        return self.normalized_dir / "sector_index_daily.csv"

    @property
    def sector_inventory_path(self) -> Path:
        return self.normalized_dir / "sector_index_inventory.csv"

    @property
    def sector_mapping_path(self) -> Path:
        return self.normalized_dir / "stock_sector_mapping.csv"

    @property
    def calendar_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"

    @property
    def current_constituents_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "current" / "nifty500_constituents_normalized.csv"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def benchmark_context_summary_path(self) -> Path:
        return self.reports_dir / "benchmark_context_summary.json"

    @property
    def sector_context_summary_path(self) -> Path:
        return self.reports_dir / "sector_context_summary.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build official benchmark and sector context for DAILY_FEATURES_V1.")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 9, 7))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 9, 7))
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--force-refresh", action="store_true")
    return parser


def build_benchmark_sector_context(
    *,
    config: ContextBuilderConfig,
    force_refresh: bool,
    progress: Any | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    trading_sessions = load_trading_sessions(config.calendar_path, config.start_date, config.end_date)
    if progress:
        progress("Discovering official NSE index inventory")
    provider = NSEOfficialIndexHistoryProvider(raw_dir=config.raw_dir, force_refresh=force_refresh)
    try:
        discovered = provider.discover_index_definitions()
        definitions = build_index_definitions(discovered)

        if progress:
            progress("Acquiring official NIFTY 50 and NIFTY 500 history")
        benchmark_records = fetch_records(provider, definitions["benchmarks"], config.start_date, config.end_date, progress)
        write_benchmark_daily(config.benchmark_daily_path, benchmark_records)
        benchmark_summary = build_benchmark_summary(benchmark_records, trading_sessions, config)

        if progress:
            progress("Acquiring official sector index histories")
        sector_records = fetch_records(provider, definitions["sectors"], config.start_date, config.end_date, progress)
        write_sector_daily(config.sector_index_daily_path, sector_records)
        sector_summary = build_sector_summary(sector_records, definitions["sectors"], trading_sessions, config)

        mapping_rows = build_stock_sector_mapping(config.current_constituents_path)
        write_csv(config.sector_mapping_path, mapping_rows, SECTOR_MAPPING_FIELDS)
        mapping_status_counts = Counter(row["mapping_status"] for row in mapping_rows)
        sector_inventory_rows = build_sector_inventory_rows(definitions["sectors"], sector_summary)
        write_csv(config.sector_inventory_path, sector_inventory_rows, SECTOR_INVENTORY_FIELDS)

        benchmark_context = {
            "version": BENCHMARK_CONTEXT_VERSION,
            "generated_at": generated_at,
            "official_sources": {
                "index_history": NSEOfficialIndexHistoryProvider.source_reference,
                "index_history_endpoint": NSEOfficialIndexHistoryProvider.index_history_endpoint,
                "index_inventory_endpoint": NSEOfficialIndexHistoryProvider.index_inventory_endpoint,
            },
            "target_start_date": config.start_date.isoformat(),
            "target_end_date": config.end_date.isoformat(),
            "primary_benchmark_id": PRIMARY_BENCHMARK_ID,
            "benchmarks": benchmark_summary,
            "normalized_path": str(config.benchmark_daily_path),
            "raw_cache_dir": str(config.raw_dir),
        }
        sector_context = {
            "version": SECTOR_CONTEXT_VERSION,
            "generated_at": generated_at,
            "official_sources": {
                "sector_inventory": NSEOfficialIndexHistoryProvider.inventory_source_reference,
                "sector_index_history": NSEOfficialIndexHistoryProvider.source_reference,
                "current_nifty500_constituents": "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
                "public_archive_limitation": "https://www.niftyindices.com/offerings/data-subscription",
            },
            "target_start_date": config.start_date.isoformat(),
            "target_end_date": config.end_date.isoformat(),
            "sector_indices": sector_summary,
            "mapping_status_counts": dict(mapping_status_counts),
            "mapping_policy": {
                "allowed_statuses": ["POINT_IN_TIME_VERIFIED", "INFERRED_WITH_EVIDENCE"],
                "current_only_policy": "Retained for diagnostics only; not projected backward into historical sector-relative features.",
            },
            "normalized_path": str(config.sector_index_daily_path),
            "mapping_path": str(config.sector_mapping_path),
            "inventory_path": str(config.sector_inventory_path),
        }
        return {
            "phase": "Step 02.4",
            "command": "Command 02",
            "generated_at": generated_at,
            "benchmark_context": benchmark_context,
            "sector_context": sector_context,
            "outputs": {
                "benchmark_daily": str(config.benchmark_daily_path),
                "sector_index_daily": str(config.sector_index_daily_path),
                "sector_mapping": str(config.sector_mapping_path),
                "sector_inventory": str(config.sector_inventory_path),
                "benchmark_summary": str(config.benchmark_context_summary_path),
                "sector_summary": str(config.sector_context_summary_path),
                "markdown": "docs/benchmark-and-sector-context.md",
            },
            "processing": {
                "duration_seconds": 0,
                "storage_size_bytes": sum(file_size(path) for path in (
                    config.benchmark_daily_path,
                    config.sector_index_daily_path,
                    config.sector_mapping_path,
                    config.sector_inventory_path,
                )),
            },
            "safety": {
                "orders_placed": 0,
                "remote_migrations_applied": 0,
                "supabase_bulk_records_persisted": 0,
            },
        }
    finally:
        provider.close()


def build_index_definitions(discovered: Sequence[IndexDefinition]) -> dict[str, list[IndexDefinition]]:
    discovered_by_name = {row.index_name.upper(): row for row in discovered}
    benchmark_definitions = [
        IndexDefinition(
            index_id=index_id,
            index_name=index_name,
            category="BROAD MARKET INDICES",
            role="PRIMARY_BENCHMARK" if index_id == PRIMARY_BENCHMARK_ID else "SECONDARY_BENCHMARK",
            source_reference=discovered_by_name.get(index_name.upper(), IndexDefinition(index_id, index_name, "")).source_reference,
        )
        for index_id, index_name in BENCHMARK_INDEXES.items()
    ]

    sector_names = {name.upper(): name for name in SUPPORTED_SECTOR_INDEX_NAMES}
    for row in discovered:
        if row.category.upper() == "SECTORAL INDICES":
            sector_names[row.index_name.upper()] = row.index_name
    sector_definitions = [
        IndexDefinition(
            index_id=canonical_index_id(name),
            index_name=name,
            category="SECTORAL INDICES",
            role="SECTOR_CONTEXT",
            source_reference=discovered_by_name.get(name.upper(), IndexDefinition(canonical_index_id(name), name, "")).source_reference,
        )
        for name in sorted(sector_names.values())
    ]
    return {"benchmarks": benchmark_definitions, "sectors": sector_definitions}


def fetch_records(
    provider: NSEOfficialIndexHistoryProvider,
    definitions: Sequence[IndexDefinition],
    start_date: date,
    end_date: date,
    progress: Any | None,
) -> dict[str, list[IndexDailyRecord]]:
    records: dict[str, list[IndexDailyRecord]] = {}
    for offset, definition in enumerate(definitions, start=1):
        if progress:
            progress(f"Fetching {definition.index_name} ({offset}/{len(definitions)})")
        records[definition.index_id] = provider.fetch_index_history(
            definition=definition,
            start_date=start_date,
            end_date=end_date,
        )
    return records


def write_benchmark_daily(path: Path, records: dict[str, list[IndexDailyRecord]]) -> None:
    rows = []
    for benchmark_id, values in sorted(records.items()):
        for record in values:
            rows.append(
                {
                    "trading_date": record.trading_date,
                    "benchmark_id": benchmark_id,
                    "index_name": record.index_name,
                    "open": record.open,
                    "high": record.high,
                    "low": record.low,
                    "close": record.close,
                    "source": record.source,
                    "source_reference": record.source_reference,
                    "source_date": record.source_date,
                    "methodology": "OFFICIAL_NSE_INDEX_CLOSE_NO_FORWARD_FILL",
                    "benchmark_context_version": BENCHMARK_CONTEXT_VERSION,
                }
            )
    write_csv(path, rows, BENCHMARK_DAILY_FIELDS)


def write_sector_daily(path: Path, records: dict[str, list[IndexDailyRecord]]) -> None:
    rows = []
    for sector_index_id, values in sorted(records.items()):
        first_date = values[0].trading_date if values else None
        last_date = values[-1].trading_date if values else None
        for record in values:
            rows.append(
                {
                    "trading_date": record.trading_date,
                    "sector_index_id": sector_index_id,
                    "index_name": record.index_name,
                    "close": record.close,
                    "source": record.source,
                    "source_reference": record.source_reference,
                    "coverage_start": first_date,
                    "coverage_end": last_date,
                    "methodology": "OFFICIAL_NSE_SECTOR_INDEX_CLOSE_NO_FORWARD_FILL",
                    "sector_context_version": SECTOR_CONTEXT_VERSION,
                }
            )
    write_csv(path, rows, SECTOR_INDEX_DAILY_FIELDS)


def build_benchmark_summary(
    records: dict[str, list[IndexDailyRecord]],
    trading_sessions: Sequence[date],
    config: ContextBuilderConfig,
) -> dict[str, Any]:
    return {
        index_id: coverage_summary(values, trading_sessions, config.start_date, config.end_date)
        | {"index_name": BENCHMARK_INDEXES.get(index_id, index_id)}
        for index_id, values in records.items()
    }


def build_sector_summary(
    records: dict[str, list[IndexDailyRecord]],
    definitions: Sequence[IndexDefinition],
    trading_sessions: Sequence[date],
    config: ContextBuilderConfig,
) -> dict[str, Any]:
    definitions_by_id = {definition.index_id: definition for definition in definitions}
    summary: dict[str, Any] = {}
    for index_id in sorted(definitions_by_id):
        values = records.get(index_id, [])
        row = coverage_summary(values, trading_sessions, config.start_date, config.end_date)
        row["index_name"] = definitions_by_id[index_id].index_name
        row["usable"] = row["available_sessions"] > 0
        summary[index_id] = row
    return summary


def coverage_summary(
    values: Sequence[IndexDailyRecord],
    trading_sessions: Sequence[date],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    target_sessions = [session for session in trading_sessions if start_date <= session <= end_date]
    by_date = {record.trading_date: record for record in values}
    aligned_dates = set(target_sessions) & set(by_date)
    missing = [session for session in target_sessions if session not in by_date]
    extra = sorted(set(by_date) - set(target_sessions))
    close_values = [record.close for record in values]
    duplicate_dates = len(values) - len(by_date)
    suspicious_jumps = count_suspicious_jumps(values)
    return {
        "target_sessions": len(target_sessions),
        "available_sessions": len(aligned_dates),
        "official_rows_in_range": len(by_date),
        "missing_sessions": len(missing),
        "coverage_percent": percent(len(aligned_dates), len(target_sessions)),
        "first_date": min(by_date).isoformat() if by_date else "",
        "last_date": max(by_date).isoformat() if by_date else "",
        "duplicate_rows": duplicate_dates,
        "extra_sessions_not_in_calendar": len(extra),
        "positive_close": all(value > 0 for value in close_values),
        "suspicious_jumps": suspicious_jumps,
        "missing_session_examples": [session.isoformat() for session in missing[:10]],
        "extra_session_examples": [session.isoformat() for session in extra[:10]],
    }


def build_stock_sector_mapping(current_constituents_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(current_constituents_path):
        symbol = row.get("symbol") or row.get("trading_symbol") or ""
        isin = row.get("isin") or row.get("isin_code") or ""
        industry = row.get("industry") or row.get("sector") or ""
        sector_index_id = INDUSTRY_TO_SECTOR_INDEX_ID.get(industry, "")
        rows.append(
            {
                "symbol": symbol,
                "isin": isin,
                "sector_name": industry,
                "sector_index_id": sector_index_id,
                "valid_from": "",
                "valid_to": "",
                "mapping_source": row.get("source", "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"),
                "mapping_status": "CURRENT_ONLY" if sector_index_id else "UNAVAILABLE",
                "confidence": "CURRENT_OFFICIAL_SNAPSHOT_ONLY" if sector_index_id else "NONE",
                "notes": (
                    "Current official Nifty 500 industry metadata retained for diagnostics only; "
                    "not projected backward for historical sector-relative features."
                    if sector_index_id
                    else "No supported official sector index mapping was assigned from current metadata."
                ),
            }
        )
    return rows


def build_sector_inventory_rows(definitions: Sequence[IndexDefinition], sector_summary: dict[str, Any]) -> list[dict[str, Any]]:
    configured_ids = {canonical_index_id(name) for name in SUPPORTED_SECTOR_INDEX_NAMES}
    rows = []
    for definition in definitions:
        summary = sector_summary.get(definition.index_id, {})
        rows.append(
            {
                "sector_index_id": definition.index_id,
                "index_name": definition.index_name,
                "category": definition.category,
                "source_reference": definition.source_reference,
                "configured": definition.index_id in configured_ids,
                "discovered_live": bool(definition.source_reference),
                "usable": summary.get("usable", False),
                "available_sessions": summary.get("available_sessions", 0),
                "coverage_percent": summary.get("coverage_percent", "0"),
            }
        )
    return rows


def count_suspicious_jumps(values: Sequence[IndexDailyRecord]) -> int:
    ordered = sorted(values, key=lambda record: record.trading_date)
    count = 0
    for previous, current in zip(ordered, ordered[1:]):
        if previous.close <= 0:
            continue
        change = abs(current.close / previous.close - Decimal("1"))
        if change > Decimal("0.20"):
            count += 1
    return count


def percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0"
    return str((Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(Decimal("0.0001")))


def write_benchmark_sector_markdown(report: dict[str, Any], path: Path) -> None:
    benchmark_context = report["benchmark_context"]
    sector_context = report["sector_context"]
    benchmark_rows = benchmark_context["benchmarks"]
    sector_rows = sector_context["sector_indices"]
    lines = [
        "# Benchmark And Sector Context",
        "",
        "Current phase: Step 02.4 / Command 02 - official benchmark and sector relative-strength foundation",
        "",
        "## Status",
        "",
        f"- Benchmark context version: {benchmark_context['version']}",
        f"- Sector context version: {sector_context['version']}",
        "- Feature version decision: DAILY_FEATURES_V1 is retained; benchmark_context_version and sector_context_version record this enhancement.",
        "",
        "## Official Sources",
        "",
        f"- NSE historical index data: {benchmark_context['official_sources']['index_history']}",
        f"- NSE historical index endpoint: {benchmark_context['official_sources']['index_history_endpoint']}",
        f"- NSE live index inventory endpoint: {benchmark_context['official_sources']['index_inventory_endpoint']}",
        f"- Current Nifty 500 constituent evidence: {sector_context['official_sources']['current_nifty500_constituents']}",
        "",
        "## Timing And Formulas",
        "",
        "- Index and stock features are DAILY_EOD and become NEXT_SESSION_DECISION_INPUT for the next NSE session.",
        "- Benchmark return_Nd = index_close_T / index_close_T-N - 1, using NSE trading sessions.",
        "- Relative return = adjusted_stock_return_Nd - benchmark_or_sector_return_Nd.",
        "- Missing official index sessions are not forward-filled; affected relative-return windows stay null.",
        "- Stock-side corporate-action exclusion windows continue to block benchmark and sector relative returns.",
        "",
        "## Benchmarks",
        "",
    ]
    for index_id, row in sorted(benchmark_rows.items()):
        lines.append(
            "- "
            f"{index_id} ({row['index_name']}): {row['first_date']} to {row['last_date']}, "
            f"{row['available_sessions']}/{row['target_sessions']} sessions, "
            f"{row['missing_sessions']} missing, {row['coverage_percent']}% coverage"
        )
    lines.extend(["", "## Sector Index Coverage", ""])
    for index_id, row in sorted(sector_rows.items()):
        lines.append(
            "- "
            f"{index_id} ({row['index_name']}): {row['first_date']} to {row['last_date']}, "
            f"{row['available_sessions']}/{row['target_sessions']} sessions, "
            f"{row['missing_sessions']} missing, {row['coverage_percent']}% coverage, usable={row['usable']}"
        )
    lines.extend(
        [
            "",
            "## Stock-Sector Mapping",
            "",
            "- Mapping statuses follow POINT_IN_TIME_VERIFIED, INFERRED_WITH_EVIDENCE, CURRENT_ONLY, and UNAVAILABLE.",
            "- Current Nifty 500 industry metadata is CURRENT_ONLY and is not used for historical sector-relative calculations.",
            "- No public point-in-time sector constituent archive was available inside this command's scope; deeper archive/subscription work remains future work.",
        ]
    )
    for status, count in sorted(sector_context["mapping_status_counts"].items()):
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Benchmark daily CSV: {report['outputs']['benchmark_daily']}",
            f"- Sector index daily CSV: {report['outputs']['sector_index_daily']}",
            f"- Stock-sector mapping CSV: {report['outputs']['sector_mapping']}",
            f"- Sector inventory CSV: {report['outputs']['sector_inventory']}",
            "",
            "## Known Limitations",
            "",
            "- Sector index price history is available, but historical stock-to-sector membership remains limited to safe mapping evidence.",
            "- CURRENT_ONLY mappings deliberately produce null sector-relative fields.",
            "- No strategy scoring, backtesting, labels, live data connection, order placement, migrations, or Supabase persistence are performed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "COMPLETED",
        "phase": report["phase"],
        "command": report["command"],
        "benchmark_context_version": report["benchmark_context"]["version"],
        "sector_context_version": report["sector_context"]["version"],
        "benchmarks": report["benchmark_context"]["benchmarks"],
        "sector_indices_acquired": [
            index_id
            for index_id, row in report["sector_context"]["sector_indices"].items()
            if row["available_sessions"] > 0
        ],
        "mapping_status_counts": report["sector_context"]["mapping_status_counts"],
        "outputs": report["outputs"],
        "processing": report["processing"],
        "safety": report["safety"],
    }


def backend_env_is_ignored() -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "backend/.env"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


if __name__ == "__main__":
    raise SystemExit(main())
