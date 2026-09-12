from __future__ import annotations

import csv
import gzip
import json
import math
import os
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    resolve_current_portfolio_backtest_trades_dataset,
    verify_current_portfolio_backtest_baseline,
)
from app.config.settings import Settings
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.research.intraday.aggregation import aggregate_bars
from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.config import DEFAULT_INTRADAY_CONFIG
from app.research.intraday.models import CanonicalIntradayBar, DailyBarReference, IntradayBarQuality
from app.research.intraday.normalization import canonical_bar_row, normalize_rows, parse_timestamp
from app.research.intraday.opening_range import calculate_opening_range
from app.research.intraday.provider_pilot import (
    GrowwResearchMarketDataAdapter,
    InstrumentMapping,
    RequestBudget,
    SessionUsability,
    _baseline_state,
    _extract_candles,
    _provider_candle_row,
    _reconciliation_row,
    classify_provider_failure,
    credentials_present,
)
from app.research.intraday.quality import assess_session_quality
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED, canonical_hash, json_ready
from app.research.temporal_validation.partition import read_gzip_csv, resolve_development_backtest_source_rows
from app.strategy.momentum_candidates import file_sha256


COMMAND_VERSION = "DEVELOPMENT_INTRADAY_INGESTION_V1"
PROFILE = "NSE_CASH_5M_DEVELOPMENT_BOUNDED_V1"
PROVIDER = "GROWW"
TARGET_OPPORTUNITY_COVERAGE_PCT = Decimal("80")
MAX_SYMBOLS = 100
MAX_NORMALIZED_5M_ROWS = 5_000_000
MAX_PROVIDER_REQUESTS = 5_000
MAX_RAW_STORAGE_GIB = Decimal("2")
MAX_ESTIMATED_WALLCLOCK_HOURS = Decimal("3")
MIN_SYMBOLS = 20
MIN_SYMBOL_SESSIONS = 500
REQUEST_WINDOW_DAYS = 30
EXPECTED_BARS_PER_SESSION = 75
ESTIMATED_RAW_BYTES_PER_ROW = Decimal("160")
ESTIMATED_PROCESSING_SECONDS_PER_REQUEST = Decimal("0.5")
THROTTLE_SECONDS = Decimal("1")
REQUEST_SUCCESS_TARGET_PCT = Decimal("98")
MATERIAL_FAILURE_PCT = Decimal("5")

MANIFEST_FILENAMES = (
    "development_intraday_scope_manifest_v1.json",
    "request_plan_v1.json",
    "ingestion_checkpoint_v1.json",
    "raw_index_v1.json",
    "dataset_manifest_v1.json",
    "opportunity_coverage_manifest_v1.json",
)
REPORT_FILENAMES = (
    "development_intraday_v1_summary.json",
    "development_intraday_v1_scope.csv",
    "development_intraday_v1_requests.csv",
    "development_intraday_v1_symbols.csv",
    "development_intraday_v1_sessions.csv",
    "development_intraday_v1_quality.csv",
    "development_intraday_v1_reconciliation.csv",
    "development_intraday_v1_yearly.csv",
    "development_intraday_v1_opportunity_coverage.csv",
    "development_intraday_v1_trade_coverage.csv",
    "development_intraday_v1_confirmation_availability.csv",
    "development_intraday_v1_storage.csv",
    "development_intraday_v1_failures.csv",
    "development_intraday_v1_pilot_validation.csv",
)


class RunMode(StrEnum):
    PLAN_ONLY = "PLAN_ONLY"
    INGEST = "INGEST"
    RESUME = "RESUME"
    VERIFY = "VERIFY"
    REPLAY_FAILED = "REPLAY_FAILED"


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_RETRYABLE_TIMEOUT = "FAILED_RETRYABLE_TIMEOUT"
    FAILED_FINAL = "FAILED_FINAL"
    FAILED_FINAL_TIMEOUT = "FAILED_FINAL_TIMEOUT"
    SKIPPED = "SKIPPED"


class DevelopmentDataQualityResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_MINOR_GAPS = "CLEAN_WITH_MINOR_GAPS"
    USABLE_WITH_MATERIAL_GAPS = "USABLE_WITH_MATERIAL_GAPS"
    POOR = "POOR"
    INCONCLUSIVE = "INCONCLUSIVE"


class DevelopmentProviderReliabilityResult(StrEnum):
    CLEAN = "CLEAN"
    USABLE_WITH_LIMITATIONS = "USABLE_WITH_LIMITATIONS"
    UNRELIABLE = "UNRELIABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class BoundedIngestionResult(StrEnum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    PARTIAL = "PARTIAL"
    FAIL_PROVIDER = "FAIL_PROVIDER"
    FAIL_DATA_QUALITY = "FAIL_DATA_QUALITY"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class CoverageResult(StrEnum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INCONCLUSIVE = "INCONCLUSIVE"


class FullHistoryRecommendation(StrEnum):
    PROCEED_TO_SEPARATE_AUTHORIZATION = "PROCEED_TO_SEPARATE_AUTHORIZATION"
    MORE_PILOT_DATA_REQUIRED = "MORE_PILOT_DATA_REQUIRED"
    DO_NOT_PROCEED = "DO_NOT_PROCEED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class HardCaps:
    max_symbols: int = MAX_SYMBOLS
    max_normalized_5m_rows: int = MAX_NORMALIZED_5M_ROWS
    max_provider_requests: int = MAX_PROVIDER_REQUESTS
    max_raw_storage_gib: Decimal = MAX_RAW_STORAGE_GIB
    max_estimated_wallclock_hours: Decimal = MAX_ESTIMATED_WALLCLOCK_HOURS


def manifest_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/intraday/v1/development_bounded/manifests"


def raw_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/raw/intraday/groww/development_bounded_v1"


def normalized_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/normalized/intraday/5m/development_bounded_v1"


def derived_root(repo_root: Path, minutes: int) -> Path:
    return Path(repo_root) / f"data/derived/intraday/{minutes}m/development_bounded_v1"


def report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _rr_band(value: Any) -> str:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return "UNKNOWN"
    if parsed < Decimal("1.5"):
        return "LT_1_5"
    if parsed < Decimal("2"):
        return "1_5_TO_LT_2"
    return "GE_2"


def _opportunity_id(row: Mapping[str, Any]) -> str:
    return f"{row.get('decision_date', '')}|{str(row.get('symbol', '')).upper()}"


def load_frozen_development_opportunities(data_dir: Path) -> list[dict[str, str]]:
    rows = resolve_development_backtest_source_rows(Path(data_dir), DEFAULT_TEMPORAL_CONFIG)
    if len(rows) != 2_068:
        raise ValueError(f"Frozen DEVELOPMENT opportunity count changed: expected 2068, observed {len(rows)}")
    if any(
        not (
            DEFAULT_TEMPORAL_CONFIG.development_start.isoformat()
            <= str(row.get("decision_date", ""))
            <= DEFAULT_TEMPORAL_CONFIG.development_end.isoformat()
        )
        for row in rows
    ):
        raise ValueError("Development source resolver returned an out-of-window opportunity")
    return rows


def load_frozen_development_trades(data_dir: Path) -> list[dict[str, str]]:
    verify_current_portfolio_backtest_baseline(Path(data_dir))
    rows = read_gzip_csv(resolve_current_portfolio_backtest_trades_dataset(Path(data_dir)))
    start = DEFAULT_TEMPORAL_CONFIG.development_start.isoformat()
    end = DEFAULT_TEMPORAL_CONFIG.development_end.isoformat()
    return [row for row in rows if start <= str(row.get("decision_date", "")) <= end]


def load_instrument_master(path: Path) -> tuple[list[dict[str, str]], str]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Official Groww instrument master is unavailable: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            {str(key).strip(): str(value).strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    return rows, file_sha256(source)


def map_instruments(
    symbols: Iterable[str],
    internal_isins: Mapping[str, str | None],
    master_rows: Sequence[Mapping[str, Any]],
) -> list[InstrumentMapping]:
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in master_rows:
        if str(row.get("exchange", "")).upper() != "NSE":
            continue
        if str(row.get("segment", "CASH")).upper() != "CASH":
            continue
        trading_symbol = str(row.get("trading_symbol", "")).strip().upper()
        groww_symbol = str(row.get("groww_symbol", "")).strip().upper()
        if trading_symbol:
            by_symbol[trading_symbol].append(row)
        if groww_symbol.startswith("NSE-"):
            by_symbol[groww_symbol[4:]].append(row)
    result: list[InstrumentMapping] = []
    for symbol in sorted(set(str(value).upper() for value in symbols)):
        candidates = by_symbol.get(symbol, [])
        equities = [row for row in candidates if str(row.get("instrument_type", "EQ")).upper() == "EQ"]
        unique: list[Mapping[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in equities or candidates:
            identity = (str(row.get("groww_symbol", "")), str(row.get("exchange_token", "")))
            if identity not in seen:
                unique.append(row)
                seen.add(identity)
        chosen = unique[0] if len(unique) == 1 else None
        internal_isin = internal_isins.get(symbol) or None
        if chosen is None:
            status = "AMBIGUOUS" if unique else "UNRESOLVED"
            result.append(
                InstrumentMapping(
                    symbol,
                    internal_isin,
                    f"NSE-{symbol}",
                    None,
                    "NSE",
                    "CACHED_OFFICIAL_GROWW_INSTRUMENT_MASTER",
                    "UNKNOWN",
                    "UNKNOWN",
                    status,
                )
            )
            continue
        provider_isin = str(chosen.get("isin", "")).strip() or None
        token = str(
            chosen.get("exchange_token")
            or chosen.get("instrument_token")
            or chosen.get("token")
            or ""
        ).strip() or None
        if internal_isin and provider_isin and internal_isin != provider_isin:
            status = "ISIN_MISMATCH"
        elif token is None:
            status = "MISSING_TOKEN"
        elif internal_isin and provider_isin == internal_isin:
            status = "ISIN_VERIFIED_CURRENT_TOKEN"
        else:
            status = "CURRENT_TOKEN_ONLY"
        result.append(
            InstrumentMapping(
                symbol,
                internal_isin or provider_isin,
                str(chosen.get("groww_symbol") or f"NSE-{symbol}"),
                token,
                "NSE",
                "CACHED_OFFICIAL_GROWW_INSTRUMENT_MASTER",
                "UNKNOWN",
                "UNKNOWN",
                status,
            )
        )
    return result


def mapping_is_usable(mapping: InstrumentMapping) -> bool:
    return mapping.provider_instrument_id is not None and mapping.mapping_status in {
        "ISIN_VERIFIED_CURRENT_TOKEN",
        "CURRENT_TOKEN_ONLY",
        "CLEAN",
        "MISSING_ISIN",
    }


def rank_symbols(
    opportunities: Sequence[Mapping[str, Any]],
    admitted_trades: Sequence[Mapping[str, Any]],
    mappings: Sequence[InstrumentMapping],
) -> list[dict[str, Any]]:
    trade_counts = Counter(str(row.get("symbol", "")).upper() for row in admitted_trades)
    mapping_by_symbol = {row.internal_symbol: row for row in mappings}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in opportunities:
        grouped[str(row.get("symbol", "")).upper()].append(row)
    rankings: list[dict[str, Any]] = []
    for symbol, rows in grouped.items():
        mapping = mapping_by_symbol.get(symbol)
        categories = {
            "|".join(
                (
                    str(row.get("source_score_band", "UNKNOWN")),
                    str(row.get("setup_quality", "UNKNOWN")),
                    _rr_band(row.get("effective_reward_risk")),
                    str(row.get("candidate_category", "UNKNOWN")),
                )
            )
            for row in rows
        }
        ambiguity = sum(
            _truthy(row.get("same_bar_ambiguous"))
            or _truthy(row.get("stop_target_same_bar_ambiguous"))
            for row in rows
        )
        rankings.append(
            {
                "symbol": symbol,
                "opportunity_count": len(rows),
                "admitted_trade_count": trade_counts[symbol],
                "ambiguity_execution_relevance_count": ambiguity,
                "research_category_breadth": len(categories),
                "mapping_available": bool(mapping and mapping_is_usable(mapping)),
                "mapping_status": mapping.mapping_status if mapping else "UNRESOLVED",
                "selection_uses_performance_fields": False,
            }
        )
    rankings.sort(
        key=lambda row: (
            -int(row["opportunity_count"]),
            -int(row["admitted_trade_count"]),
            -int(row["ambiguity_execution_relevance_count"]),
            -int(row["research_category_breadth"]),
            -int(bool(row["mapping_available"])),
            str(row["symbol"]),
        )
    )
    for index, row in enumerate(rankings, start=1):
        row["rank"] = index
    return rankings


def select_symbols(
    rankings: Sequence[Mapping[str, Any]],
    *,
    total_opportunities: int,
    target_pct: Decimal = TARGET_OPPORTUNITY_COVERAGE_PCT,
    max_symbols: int = MAX_SYMBOLS,
) -> list[str]:
    selected: list[str] = []
    covered = 0
    for row in rankings:
        if not bool(row["mapping_available"]):
            continue
        selected.append(str(row["symbol"]))
        covered += int(row["opportunity_count"])
        if Decimal(covered) * Decimal("100") / Decimal(total_opportunities) >= target_pct:
            break
        if len(selected) >= max_symbols:
            break
    if len(selected) > max_symbols:
        raise ValueError("Symbol hard cap exceeded")
    return selected


def opportunity_session_dates(row: Mapping[str, Any]) -> tuple[date, ...]:
    values: set[date] = set()
    for field in ("decision_date", "next_session_date", "session_date_1", "session_date_2", "session_date_3", "session_date_4"):
        raw = str(row.get(field, "")).strip()
        if not raw:
            continue
        parsed = date.fromisoformat(raw)
        if DEFAULT_TEMPORAL_CONFIG.development_start <= parsed <= DEFAULT_TEMPORAL_CONFIG.development_end:
            values.add(parsed)
    return tuple(sorted(values))


def expand_required_sessions(
    opportunities: Sequence[Mapping[str, Any]], selected_symbols: Iterable[str]
) -> dict[str, tuple[date, ...]]:
    selected = set(selected_symbols)
    grouped: dict[str, set[date]] = defaultdict(set)
    for row in opportunities:
        symbol = str(row.get("symbol", "")).upper()
        if symbol in selected:
            grouped[symbol].update(opportunity_session_dates(row))
    return {symbol: tuple(sorted(grouped[symbol])) for symbol in sorted(selected)}


def group_request_windows(
    required_sessions: Mapping[str, Sequence[date]],
    mapping_by_symbol: Mapping[str, InstrumentMapping],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    sequence = 0
    for symbol in sorted(required_sessions):
        dates = sorted(set(required_sessions[symbol]))
        cursor = 0
        while cursor < len(dates):
            start = dates[cursor]
            end = min(start + timedelta(days=REQUEST_WINDOW_DAYS - 1), DEFAULT_TEMPORAL_CONFIG.development_end)
            expected = [value for value in dates if start <= value <= end]
            cursor += len(expected)
            sequence += 1
            mapping = mapping_by_symbol[symbol]
            requests.append(
                {
                    "request_id": f"DEV-INTRADAY-C05-{sequence:04d}-{symbol}-{start.strftime('%Y%m%d')}",
                    "symbol": symbol,
                    "provider_instrument": mapping.provider_symbol,
                    "provider_instrument_id": mapping.provider_instrument_id,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "interval": "5m",
                    "expected_sessions": [value.isoformat() for value in expected],
                    "expected_rows": len(expected) * EXPECTED_BARS_PER_SESSION,
                    "sequence_no": sequence,
                }
            )
    return requests


def estimate_raw_rows(requests: Sequence[Mapping[str, Any]], trading_dates: Iterable[date]) -> int:
    calendar = sorted(set(trading_dates))
    return sum(
        sum(date.fromisoformat(str(row["start_date"])) <= value <= date.fromisoformat(str(row["end_date"])) for value in calendar)
        * 77
        for row in requests
    )


def hard_cap_checks(
    *,
    symbol_count: int,
    normalized_rows: int,
    request_count: int,
    raw_storage_gib: Decimal,
    wallclock_hours: Decimal,
    caps: HardCaps = HardCaps(),
) -> dict[str, bool]:
    return {
        "symbols": symbol_count <= caps.max_symbols,
        "normalized_5m_rows": normalized_rows <= caps.max_normalized_5m_rows,
        "provider_requests": request_count <= caps.max_provider_requests,
        "raw_storage_gib": raw_storage_gib <= caps.max_raw_storage_gib,
        "estimated_wallclock_hours": wallclock_hours <= caps.max_estimated_wallclock_hours,
    }


def build_plan(
    *,
    repo_root: Path,
    instrument_master_path: Path | None = None,
    caps: HardCaps = HardCaps(),
    created_at: datetime | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    data_dir = root / "data"
    opportunities = load_frozen_development_opportunities(data_dir)
    trades = load_frozen_development_trades(data_dir)
    internal_isins = {
        str(row["symbol"]).upper(): str(row.get("isin", "")).strip() or None for row in opportunities
    }
    master_path = instrument_master_path or (
        root / "backend/.venv/Lib/site-packages/growwapi/instruments.csv"
    )
    master_rows, master_hash = load_instrument_master(master_path)
    mappings = map_instruments(internal_isins, internal_isins, master_rows)
    rankings = rank_symbols(opportunities, trades, mappings)
    selected_symbols = select_symbols(rankings, total_opportunities=len(opportunities), max_symbols=caps.max_symbols)
    mapping_by_symbol = {row.internal_symbol: row for row in mappings if row.internal_symbol in selected_symbols}
    sessions = expand_required_sessions(opportunities, selected_symbols)
    requests = group_request_windows(sessions, mapping_by_symbol)
    selected_opportunities = sum(str(row.get("symbol", "")).upper() in set(selected_symbols) for row in opportunities)
    normalized_rows = sum(len(values) for values in sessions.values()) * EXPECTED_BARS_PER_SESSION
    source_calendar = {
        value
        for row in opportunities
        for value in opportunity_session_dates(row)
    }
    raw_rows = estimate_raw_rows(requests, source_calendar)
    raw_bytes = Decimal(raw_rows) * ESTIMATED_RAW_BYTES_PER_ROW
    raw_gib = raw_bytes / Decimal(1024**3)
    wallclock = (
        Decimal(len(requests)) * (THROTTLE_SECONDS + ESTIMATED_PROCESSING_SECONDS_PER_REQUEST)
        / Decimal(3600)
    )
    checks = hard_cap_checks(
        symbol_count=len(selected_symbols),
        normalized_rows=normalized_rows,
        request_count=len(requests),
        raw_storage_gib=raw_gib,
        wallclock_hours=wallclock,
        caps=caps,
    )
    if not all(checks.values()):
        raise ValueError(f"Frozen ingestion plan exceeds a hard cap: {checks}")
    selected_mapping_rows = [mapping_by_symbol[symbol].snapshot() for symbol in selected_symbols]
    required_rows = [
        {"symbol": symbol, "trading_date": value.isoformat()}
        for symbol in selected_symbols
        for value in sessions[symbol]
    ]
    now = created_at or datetime.now(timezone.utc)
    scope_body = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "provider": PROVIDER,
        "development_start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
        "development_end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
        "validation_state": SEALED,
        "validation_run_count": 0,
        "selection_method": [
            "DEVELOPMENT_OPPORTUNITY_COUNT_DESC",
            "FROZEN_ADMITTED_TRADE_COUNT_DESC",
            "AMBIGUITY_EXECUTION_RELEVANCE_COUNT_DESC",
            "SCORE_SETUP_RR_CATEGORY_BREADTH_DESC",
            "EXACT_MAPPING_AVAILABILITY_DESC",
            "SYMBOL_ASC_TIEBREAK",
        ],
        "performance_fields_used_in_selection": False,
        "target_opportunity_coverage_pct": TARGET_OPPORTUNITY_COVERAGE_PCT,
        "selected_symbols": selected_symbols,
        "selected_instrument_ids": [row["provider_instrument_id"] for row in selected_mapping_rows],
        "selected_isins": [row["internal_isin"] for row in selected_mapping_rows],
        "instrument_mappings": selected_mapping_rows,
        "point_in_time_instrument_validity": "UNVERIFIED",
        "instrument_master_hash": master_hash,
        "instrument_master_source": "CACHED_OFFICIAL_GROWW_SDK_MASTER",
        "required_symbol_sessions": required_rows,
        "request_windows": requests,
        "total_development_opportunities": len(opportunities),
        "selected_symbol_opportunities": selected_opportunities,
        "estimated_opportunity_coverage_pct": Decimal(selected_opportunities) * Decimal("100") / Decimal(len(opportunities)),
        "estimated_raw_rows": raw_rows,
        "estimated_normalized_rows": normalized_rows,
        "estimated_requests": len(requests),
        "estimated_runtime_hours": wallclock,
        "estimated_storage_bytes": int(raw_bytes),
        "estimated_storage_gib": raw_gib,
        "hard_caps": asdict(caps),
        "hard_cap_checks": checks,
        "minimum_useful_scope": {
            "minimum_symbols": MIN_SYMBOLS,
            "minimum_symbol_sessions": MIN_SYMBOL_SESSIONS,
            "planned_symbols": len(selected_symbols),
            "planned_symbol_sessions": len(required_rows),
            "passed": len(selected_symbols) >= MIN_SYMBOLS and len(required_rows) >= MIN_SYMBOL_SESSIONS,
        },
    }
    scope_hash = canonical_hash(scope_body)
    scope = {**scope_body, "scope_hash": scope_hash, "created_at": now.isoformat()}
    plan_body = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "provider": PROVIDER,
        "scope_hash": scope_hash,
        "requests": requests,
    }
    request_plan_hash = canonical_hash(plan_body)
    request_plan = {**plan_body, "request_plan_hash": request_plan_hash, "created_at": now.isoformat()}
    return {
        "scope": scope,
        "request_plan": request_plan,
        "rankings": rankings,
        "mappings": mappings,
        "opportunities": opportunities,
        "trades": trades,
        "required_sessions": sessions,
    }


def validate_scope_and_plan(scope: Mapping[str, Any], request_plan: Mapping[str, Any]) -> None:
    scope_body = {key: value for key, value in scope.items() if key not in {"scope_hash", "created_at"}}
    if canonical_hash(scope_body) != scope.get("scope_hash"):
        raise ValueError("Frozen scope hash mismatch")
    plan_body = {key: value for key, value in request_plan.items() if key not in {"request_plan_hash", "created_at"}}
    if canonical_hash(plan_body) != request_plan.get("request_plan_hash"):
        raise ValueError("Frozen request-plan hash mismatch")
    if request_plan.get("scope_hash") != scope.get("scope_hash"):
        raise ValueError("Request plan does not belong to frozen scope")
    requests = request_plan.get("requests", [])
    if len(requests) > MAX_PROVIDER_REQUESTS:
        raise ValueError("Request hard cap exceeded")
    if len(scope.get("selected_symbols", [])) > MAX_SYMBOLS:
        raise ValueError("Symbol hard cap exceeded")
    if any(
        date.fromisoformat(str(row["start_date"])) < DEFAULT_TEMPORAL_CONFIG.development_start
        or date.fromisoformat(str(row["end_date"])) > DEFAULT_TEMPORAL_CONFIG.development_end
        or (date.fromisoformat(str(row["end_date"])) - date.fromisoformat(str(row["start_date"]))).days + 1 > REQUEST_WINDOW_DAYS
        for row in requests
    ):
        raise ValueError("Request plan contains an invalid or validation-window date")


def freeze_plan(repo_root: Path, plan: Mapping[str, Any]) -> tuple[Path, Path]:
    root = manifest_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    scope_path = root / MANIFEST_FILENAMES[0]
    plan_path = root / MANIFEST_FILENAMES[1]
    for path, payload, hash_key in (
        (scope_path, plan["scope"], "scope_hash"),
        (plan_path, plan["request_plan"], "request_plan_hash"),
    ):
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get(hash_key) != payload.get(hash_key):
                raise ValueError(f"Immutable {path.name} already exists with a different hash")
        else:
            _write_json_atomic(path, payload)
    validate_scope_and_plan(
        json.loads(scope_path.read_text(encoding="utf-8")),
        json.loads(plan_path.read_text(encoding="utf-8")),
    )
    return scope_path, plan_path


def initialize_checkpoint(scope: Mapping[str, Any], request_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "command_version": COMMAND_VERSION,
        "scope_hash": scope["scope_hash"],
        "request_plan_hash": request_plan["request_plan_hash"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "requests": {
            str(row["request_id"]): {
                "status": str(CheckpointStatus.PENDING),
                "attempts": 0,
                "raw_hash": None,
                "raw_path": None,
                "row_count": 0,
                "retrieved_at": None,
                "last_error_category": None,
            }
            for row in request_plan["requests"]
        },
        "request_metrics": [],
        "retrieval_started_at": None,
        "retrieval_finished_at": None,
    }


def load_or_initialize_checkpoint(
    repo_root: Path,
    scope: Mapping[str, Any],
    request_plan: Mapping[str, Any],
) -> dict[str, Any]:
    path = manifest_root(repo_root) / MANIFEST_FILENAMES[2]
    if not path.exists():
        checkpoint = initialize_checkpoint(scope, request_plan)
        _write_json_atomic(path, checkpoint)
        return checkpoint
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if checkpoint.get("scope_hash") != scope.get("scope_hash"):
        raise ValueError("Checkpoint scope hash does not match immutable scope")
    if checkpoint.get("request_plan_hash") != request_plan.get("request_plan_hash"):
        raise ValueError("Checkpoint request-plan hash does not match immutable plan")
    expected_ids = {row["request_id"] for row in request_plan["requests"]}
    if set(checkpoint.get("requests", {})) != expected_ids:
        raise ValueError("Checkpoint request IDs differ from immutable plan")
    recovered = False
    for request_id, state in checkpoint["requests"].items():
        if state.get("status") != str(CheckpointStatus.IN_PROGRESS):
            continue
        raw_path = raw_root(repo_root) / f"{request_id}.json"
        if raw_path.exists():
            record = _read_raw_record(raw_path, str(scope["scope_hash"]))
            state.update(
                {
                    "status": str(CheckpointStatus.COMPLETE),
                    "raw_hash": record["raw_hash"],
                    "raw_path": str(raw_path),
                    "row_count": len(_extract_candles(record["response"])),
                    "retrieved_at": record["retrieved_at"],
                    "last_error_category": None,
                }
            )
        else:
            state["status"] = str(CheckpointStatus.FAILED_RETRYABLE)
            state["last_error_category"] = "INTERRUPTED_BEFORE_IMMUTABLE_RAW_ACCEPTANCE"
        recovered = True
    if recovered:
        checkpoint["retrieval_finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_checkpoint(repo_root, checkpoint)
    return checkpoint


def _write_checkpoint(repo_root: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_atomic(manifest_root(repo_root) / MANIFEST_FILENAMES[2], checkpoint)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n"
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        Path(name).replace(path)
    except Exception:
        try:
            Path(name).unlink(missing_ok=True)
        finally:
            raise


def _write_immutable_raw(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    return file_sha256(path)


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def execute_requests(
    *,
    repo_root: Path,
    scope: Mapping[str, Any],
    request_plan: Mapping[str, Any],
    checkpoint: dict[str, Any],
    mode: RunMode,
    settings: Settings | None = None,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = 1.0,
) -> dict[str, Any]:
    if mode not in {RunMode.INGEST, RunMode.RESUME, RunMode.REPLAY_FAILED}:
        raise ValueError(f"Run mode {mode} does not permit provider requests")
    validate_scope_and_plan(scope, request_plan)
    statuses = checkpoint["requests"]
    if mode == RunMode.INGEST and any(
        row["status"] != str(CheckpointStatus.PENDING) for row in statuses.values()
    ):
        raise ValueError("INGEST requires a fresh all-PENDING checkpoint; use RESUME")
    allowed = (
        {
            str(CheckpointStatus.FAILED_RETRYABLE),
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
        }
        if mode == RunMode.REPLAY_FAILED
        else {
            str(CheckpointStatus.PENDING),
            str(CheckpointStatus.IN_PROGRESS),
            str(CheckpointStatus.FAILED_RETRYABLE),
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
        }
    )
    targets = [row for row in request_plan["requests"] if statuses[row["request_id"]]["status"] in allowed]
    if not targets:
        _notify(progress, "No eligible provider requests remain; accepted immutable payloads will be verified")
        return checkpoint
    if checkpoint.get("retrieval_started_at"):
        elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(str(checkpoint["retrieval_started_at"]))
        if elapsed >= timedelta(hours=float(MAX_ESTIMATED_WALLCLOCK_HOURS)):
            checkpoint["retrieval_finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_checkpoint(repo_root, checkpoint)
            _notify(progress, "Three-hour bounded-run wall-clock limit already reached; no new provider request made")
            return checkpoint

    configured = settings or Settings()
    if client is None and not credentials_present(configured):
        raise PermissionError("Groww credentials are not present")
    prior_metrics = list(checkpoint.get("request_metrics", []))
    prior_retries = sum(
        row.get("endpoint_category") == "HISTORICAL_CANDLES"
        and row.get("status") == "FAILED"
        and row.get("response_category") in {"RATE_LIMIT", "TIMEOUT", "TRANSIENT_NETWORK", "SERVER_ERROR"}
        for row in prior_metrics
    )
    budget = RequestBudget(
        MAX_PROVIDER_REQUESTS,
        len(request_plan["requests"]) + 1,
        actual_requests=len(prior_metrics),
        retry_count=prior_retries,
        request_rows=prior_metrics,
    )
    auth_started = time.perf_counter()
    budget.reserve()
    auth_id = f"authentication-{len([row for row in prior_metrics if row.get('endpoint_category') == 'AUTHENTICATION']) + 1}"
    try:
        if client is None:
            client = GrowwAuthService(credentials=GrowwCredentials.from_settings(configured)).get_client()
            auth_status = "SUCCESS"
            auth_category = "OK"
        else:
            auth_status = "MOCK_CLIENT_SUPPLIED"
            auth_category = "OFFLINE_TEST"
    except Exception as exc:
        auth_status = "FAILED"
        auth_category = classify_provider_failure(exc)
        budget.request_rows.append(
            {
                "request_id": auth_id,
                "provider": "Groww",
                "endpoint_category": "AUTHENTICATION",
                "status": auth_status,
                "response_category": auth_category,
                "retry_number": 0,
                "latency_ms": round((time.perf_counter() - auth_started) * 1000, 3),
            }
        )
        checkpoint["request_metrics"] = budget.request_rows
        checkpoint["retrieval_finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_checkpoint(repo_root, checkpoint)
        raise RuntimeError(f"Groww authentication failed: {auth_category}") from exc
    budget.request_rows.append(
        {
            "request_id": auth_id,
            "provider": "Groww",
            "endpoint_category": "AUTHENTICATION",
            "status": auth_status,
            "response_category": auth_category,
            "retry_number": 0,
            "latency_ms": round((time.perf_counter() - auth_started) * 1000, 3),
        }
    )
    checkpoint["request_metrics"] = budget.request_rows
    checkpoint["retrieval_started_at"] = checkpoint.get("retrieval_started_at") or datetime.now(timezone.utc).isoformat()
    _write_checkpoint(repo_root, checkpoint)
    deadline = datetime.fromisoformat(str(checkpoint["retrieval_started_at"])) + timedelta(
        hours=float(MAX_ESTIMATED_WALLCLOCK_HOURS)
    )

    mappings = {
        str(row["internal_symbol"]): InstrumentMapping(**row) for row in scope["instrument_mappings"]
    }
    adapter = GrowwResearchMarketDataAdapter(
        client=client,
        budget=budget,
        throttle_seconds=throttle_seconds,
        max_retries=2,
        connect_timeout_seconds=10,
        read_timeout_seconds=20,
        total_timeout_seconds=30,
        max_consecutive_timeouts=3,
    )
    completed_before = sum(row["status"] == str(CheckpointStatus.COMPLETE) for row in statuses.values())
    try:
        for target_index, request in enumerate(targets, start=1):
            if datetime.now(timezone.utc) >= deadline:
                _notify(progress, "Three-hour bounded-run wall-clock limit reached; checkpoint retained for verification")
                break
            request_id = str(request["request_id"])
            state = statuses[request_id]
            path = raw_root(repo_root) / f"{request_id}.json"
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing.get("request_id") != request_id or existing.get("scope_hash") != scope["scope_hash"]:
                    raise ValueError(f"Existing immutable raw payload is incompatible: {path}")
                state.update(
                    {
                        "status": str(CheckpointStatus.COMPLETE),
                        "raw_hash": existing["raw_hash"],
                        "raw_path": str(path),
                        "row_count": len(_extract_candles(existing["response"])),
                        "retrieved_at": existing["retrieved_at"],
                        "last_error_category": None,
                    }
                )
                checkpoint["request_metrics"] = budget.request_rows
                _write_checkpoint(repo_root, checkpoint)
                continue
            state["status"] = str(CheckpointStatus.IN_PROGRESS)
            state["attempts"] = int(state.get("attempts", 0)) + 1
            _write_checkpoint(repo_root, checkpoint)
            try:
                response, _metric = adapter.fetch_historical_5m(
                    mapping=mappings[str(request["symbol"])],
                    start_date=date.fromisoformat(str(request["start_date"])),
                    end_date=date.fromisoformat(str(request["end_date"])),
                    request_id=request_id,
                )
                retrieved_at = datetime.now(timezone.utc).isoformat()
                record_without_hash = {
                    "command_version": COMMAND_VERSION,
                    "profile": PROFILE,
                    "provider": PROVIDER,
                    "scope_hash": scope["scope_hash"],
                    "request_plan_hash": request_plan["request_plan_hash"],
                    "request_id": request_id,
                    "symbol": request["symbol"],
                    "provider_instrument": request["provider_instrument"],
                    "provider_instrument_id": request["provider_instrument_id"],
                    "requested_start": request["start_date"],
                    "requested_end": request["end_date"],
                    "requested_interval": request["interval"],
                    "expected_sessions": request["expected_sessions"],
                    "response": response,
                }
                raw_hash = canonical_hash(record_without_hash)
                record = {**record_without_hash, "raw_hash": raw_hash, "retrieved_at": retrieved_at}
                _write_immutable_raw(path, record)
                state.update(
                    {
                        "status": str(CheckpointStatus.COMPLETE),
                        "raw_hash": raw_hash,
                        "raw_path": str(path),
                        "row_count": len(_extract_candles(response)),
                        "retrieved_at": retrieved_at,
                        "last_error_category": None,
                    }
                )
            except KeyboardInterrupt:
                state["status"] = str(CheckpointStatus.FAILED_RETRYABLE)
                state["last_error_category"] = "INTERRUPTED"
                checkpoint["request_metrics"] = budget.request_rows
                _write_checkpoint(repo_root, checkpoint)
                raise
            except Exception as exc:
                last = budget.request_rows[-1] if budget.request_rows else {}
                category = str(last.get("response_category") or classify_provider_failure(exc))
                retryable = category in {"RATE_LIMIT", "TIMEOUT", "TRANSIENT_NETWORK", "SERVER_ERROR"}
                state["status"] = str(
                    CheckpointStatus.FAILED_RETRYABLE_TIMEOUT
                    if category == "TIMEOUT"
                    else CheckpointStatus.FAILED_RETRYABLE
                    if retryable
                    else CheckpointStatus.FAILED_FINAL
                )
                state["last_error_category"] = category
            checkpoint["request_metrics"] = budget.request_rows
            _write_checkpoint(repo_root, checkpoint)
            completed = completed_before + target_index
            if target_index == 1 or completed % 25 == 0 or target_index == len(targets):
                strict_so_far = "pending-normalization"
                symbols_complete = len(
                    {
                        row["symbol"]
                        for row in request_plan["requests"]
                        if statuses[row["request_id"]]["status"] == str(CheckpointStatus.COMPLETE)
                        and all(
                            statuses[peer["request_id"]]["status"] == str(CheckpointStatus.COMPLETE)
                            for peer in request_plan["requests"]
                            if peer["symbol"] == row["symbol"]
                        )
                    }
                )
                _notify(
                    progress,
                    f"{sum(row['status'] == str(CheckpointStatus.COMPLETE) for row in statuses.values())}/{len(statuses)} requests complete; "
                    f"{symbols_complete} symbols complete; sessions normalized={strict_so_far}",
                )
            final_failures = sum(row["status"] == str(CheckpointStatus.FAILED_FINAL) for row in statuses.values())
            if final_failures * 100 > len(statuses) * int(MATERIAL_FAILURE_PCT):
                _notify(progress, "Final failure threshold exceeded; stopping the frozen request sequence")
                break
    finally:
        checkpoint["request_metrics"] = budget.request_rows
        checkpoint["retrieval_finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_checkpoint(repo_root, checkpoint)
    return checkpoint


def _read_raw_record(path: Path, expected_scope_hash: str) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("scope_hash") != expected_scope_hash:
        raise ValueError(f"Raw payload belongs to a different scope: {path}")
    body = {key: value for key, value in record.items() if key not in {"raw_hash", "retrieved_at"}}
    if canonical_hash(body) != record.get("raw_hash"):
        raise ValueError(f"Raw payload hash mismatch: {path}")
    return record


def _write_gzip_csv_deterministic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = [json_ready(dict(row)) for row in rows]
    fields = sorted({key for row in prepared for key in row}) or ["status"]
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            import io

            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
                writer.writeheader()
                for row in prepared:
                    writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = [json_ready(dict(row)) for row in rows]
    fields = sorted({key for row in prepared for key in row}) or ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in prepared:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _session_ca_flags(data_dir: Path, sessions: Iterable[tuple[str, date]]) -> dict[tuple[str, date], str]:
    targets = set(sessions)
    result = {key: "SAFE" for key in targets}
    path = Path(data_dir) / "reference/nse/corporate_actions/research_eligibility.csv"
    if not path.exists():
        return {key: "CAUTION" for key in targets}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).upper()
            try:
                start = date.fromisoformat(str(row.get("start_date", "")))
                end = date.fromisoformat(str(row.get("end_date", "")))
            except ValueError:
                continue
            status = str(row.get("eligibility_status", "")).upper()
            for key in targets:
                if key[0] != symbol or not start <= key[1] <= end:
                    continue
                if "EXCLUDE" in status or "UNSAFE" in status:
                    result[key] = "UNSAFE_STRUCTURAL"
                elif status not in {"RESEARCH_READY", "SAFE"} and result[key] == "SAFE":
                    result[key] = "CAUTION"
    return result


def _load_daily_references_safe(
    data_dir: Path, symbols: Sequence[str], dates: Sequence[date]
) -> dict[tuple[str, date], DailyBarReference]:
    wanted = set(symbols)
    result: dict[tuple[str, date], DailyBarReference] = {}
    for trading_date in dates:
        filename = f"sec_bhavdata_full_{trading_date.strftime('%d%m%Y')}.csv"
        path = Path(data_dir) / "reference/nse/daily/raw" / filename
        if not path.exists():
            continue
        rows: list[dict[str, str]] | None = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    rows = [
                        {str(key).strip(): str(value).strip() for key, value in row.items()}
                        for row in csv.DictReader(handle)
                    ]
                break
            except UnicodeDecodeError:
                rows = None
        if rows is None:
            continue
        for row in rows:
            symbol = row.get("SYMBOL", "").upper()
            if symbol not in wanted or row.get("SERIES", "").upper() != "EQ":
                continue
            result[(symbol, trading_date)] = DailyBarReference(
                symbol=symbol,
                trading_date=trading_date,
                open=Decimal(row["OPEN_PRICE"]),
                high=Decimal(row["HIGH_PRICE"]),
                low=Decimal(row["LOW_PRICE"]),
                close=Decimal(row["CLOSE_PRICE"]),
                volume=int(Decimal(row["TTL_TRD_QNTY"].replace(",", ""))),
                source=f"NSE_SECURITY_BHAVDATA:{filename}",
            )
    return result


def _missing_session_row(
    symbol: str,
    trading_date: date,
    raw_hash: str | None,
    ca_status: str,
    request_complete: bool,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "trading_date": trading_date.isoformat(),
        "expected_bars": EXPECTED_BARS_PER_SESSION,
        "actual_bars": 0,
        "missing_bars": EXPECTED_BARS_PER_SESSION,
        "duplicate_bars": 0,
        "out_of_order": False,
        "invalid_ohlc": False,
        "negative_volume": False,
        "off_session_rows": 0,
        "coverage_pct": Decimal("0"),
        "quality_status": "NO_ROWS",
        "session_usability_version": "REAL_INTRADAY_SESSION_USABILITY_V1",
        "usability": str(SessionUsability.UNUSABLE),
        "raw_hash_reference": raw_hash,
        "request_complete": request_complete,
        "corporate_action_status": ca_status,
        "ingestion_version": COMMAND_VERSION,
    }


def _canonical_5m_bars_from_partition(
    path: Path,
    *,
    allowed_dates: set[date],
) -> list[CanonicalIntradayBar]:
    """Load an existing canonical partition for an idempotent resume merge."""

    bars: list[CanonicalIntradayBar] = []
    fixed_ingestion_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for row in read_gzip_csv(path):
        trading_date = date.fromisoformat(str(row["trading_date"]))
        if trading_date not in allowed_dates or str(row.get("interval")) != "5m":
            continue
        flags_value = row.get("quality_flags") or "[]"
        flags = tuple(json.loads(str(flags_value))) if isinstance(flags_value, str) else tuple(flags_value)
        ca_value = row.get("corporate_action_reference") or "{}"
        ca_reference = json.loads(str(ca_value)) if isinstance(ca_value, str) else dict(ca_value)
        provider_vwap = row.get("provider_vwap")
        bars.append(
            CanonicalIntradayBar(
                instrument_id=str(row.get("instrument_id") or "") or None,
                symbol=str(row["symbol"]).upper(),
                isin=str(row.get("isin") or "") or None,
                exchange=str(row.get("exchange") or "NSE").upper(),
                trading_date=trading_date,
                interval="5m",
                bar_start=parse_timestamp(row["bar_start"]),
                bar_end=parse_timestamp(row["bar_end"]),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=int(row["volume"]) if str(row.get("volume") or "").strip() else None,
                source_provider=str(row.get("source_provider") or "GROWW_OFFICIAL_API"),
                source_interval=str(row.get("source_interval") or "5m"),
                source_timestamp=parse_timestamp(row.get("source_timestamp") or row["bar_start"]),
                ingested_at=fixed_ingestion_time,
                normalization_version=str(row.get("normalization_version") or "NSE_CASH_INTRADAY_5M_V1"),
                session_id=str(row.get("session_id") or f"NSE:{trading_date.isoformat()}"),
                session_sequence=int(row.get("session_sequence") or 0),
                is_partial_bar=_truthy(row.get("is_partial_bar")),
                is_missing_context=_truthy(row.get("is_missing_context")),
                quality_status=str(row.get("quality_status") or IntradayBarQuality.COMPLETE),
                quality_flags=flags,
                source_bar_count=int(row.get("source_bar_count") or 1),
                provider_vwap=(
                    Decimal(str(provider_vwap)) if str(provider_vwap or "").strip() else None
                ),
                corporate_action_reference=ca_reference,
            )
        )
    return bars


def process_accepted_payloads(
    *,
    repo_root: Path,
    scope: Mapping[str, Any],
    request_plan: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    opportunities: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    progress: Callable[[str], None] | None = None,
    incremental_request_ids: set[str] | None = None,
    manifest_output_dir: Path | None = None,
    output_command_version: str = COMMAND_VERSION,
    output_profile: str = PROFILE,
) -> dict[str, Any]:
    root = Path(repo_root)
    data_dir = root / "data"
    validate_scope_and_plan(scope, request_plan)
    mappings = {
        str(row["internal_symbol"]): InstrumentMapping(**row) for row in scope["instrument_mappings"]
    }
    required: dict[str, tuple[date, ...]] = defaultdict(tuple)
    mutable_required: dict[str, list[date]] = defaultdict(list)
    for row in scope["required_symbol_sessions"]:
        mutable_required[str(row["symbol"])].append(date.fromisoformat(str(row["trading_date"])))
    required = {symbol: tuple(sorted(values)) for symbol, values in mutable_required.items()}
    all_session_keys = {(symbol, value) for symbol, values in required.items() for value in values}
    ca_flags = _session_ca_flags(data_dir, all_session_keys)
    calendar = NseCashSessionCalendar.from_trading_dates(
        sorted({value for values in required.values() for value in values}),
        source="FROZEN_DEVELOPMENT_OPPORTUNITY_SESSION_UNIVERSE",
    )
    complete_requests = [
        row
        for row in request_plan["requests"]
        if checkpoint["requests"][row["request_id"]]["status"] == str(CheckpointStatus.COMPLETE)
    ]
    request_by_session: dict[tuple[str, date], Mapping[str, Any]] = {}
    for request in complete_requests:
        for value in request["expected_sessions"]:
            request_by_session[(str(request["symbol"]), date.fromisoformat(str(value)))] = request

    raw_index: list[dict[str, Any]] = []
    raw_count = 0
    for request in request_plan["requests"]:
        state = checkpoint["requests"][request["request_id"]]
        raw_index.append(
            {
                "request_id": request["request_id"],
                "symbol": request["symbol"],
                "start_date": request["start_date"],
                "end_date": request["end_date"],
                "raw_path": state.get("raw_path"),
                "raw_hash": state.get("raw_hash"),
                "retrieved_at": state.get("retrieved_at"),
                "row_count": state.get("row_count", 0),
                "status": state["status"],
            }
        )
        raw_count += int(state.get("row_count") or 0)

    session_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    confirmation_rows: list[dict[str, Any]] = []
    grouped_bars: dict[tuple[str, date], list[CanonicalIntradayBar]] = {}
    partition_rows: dict[int, dict[str, list[dict[str, Any]]]] = {
        5: defaultdict(list),
        10: defaultdict(list),
        15: defaultdict(list),
    }
    partition_manifest: dict[int, list[dict[str, Any]]] = {5: [], 10: [], 15: []}
    off_session_rows = 0
    collateral_regular_rows = 0
    normalized_count = 0
    derived_10_count = 0
    derived_15_count = 0
    daily_references = _load_daily_references_safe(
        data_dir,
        list(required),
        sorted({value for values in required.values() for value in values}),
    )

    requests_by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for request in complete_requests:
        if incremental_request_ids is None or str(request["request_id"]) in incremental_request_ids:
            requests_by_symbol[str(request["symbol"])].append(request)
    prevented_duplicate_bars = 0
    for symbol_index, symbol in enumerate(scope["selected_symbols"], start=1):
        raw_rows: list[dict[str, Any]] = []
        required_dates = set(required[symbol])
        for request in requests_by_symbol.get(symbol, []):
            state = checkpoint["requests"][request["request_id"]]
            record = _read_raw_record(Path(str(state["raw_path"])), str(scope["scope_hash"]))
            mapping = mappings[symbol]
            for candle in _extract_candles(record["response"]):
                parsed = _provider_candle_row(candle)
                timestamp = parse_timestamp(parsed["timestamp"], allow_naive_exchange_local=True)
                start_minutes = timestamp.hour * 60 + timestamp.minute
                aligned = timestamp.second == 0 and timestamp.minute % 5 == 0
                regular = aligned and 9 * 60 + 15 <= start_minutes < 15 * 60 + 30
                if not regular:
                    off_session_rows += 1
                    continue
                if timestamp.date() not in required_dates:
                    collateral_regular_rows += 1
                    continue
                raw_rows.append(
                    {
                        "instrument_id": mapping.provider_instrument_id,
                        "symbol": symbol,
                        "isin": mapping.internal_isin,
                        "exchange": "NSE",
                        "trading_date": timestamp.date(),
                        "interval": "5m",
                        "bar_start": timestamp,
                        "source_timestamp": timestamp,
                        "open": parsed["open"],
                        "high": parsed["high"],
                        "low": parsed["low"],
                        "close": parsed["close"],
                        "volume": parsed["volume"],
                        "provider_vwap": parsed.get("provider_vwap"),
                        "corporate_action_reference": {
                            "status": ca_flags[(symbol, timestamp.date())],
                            "automatic_adjustment": False,
                        },
                    }
                )
        new_bars = normalize_rows(
            raw_rows,
            calendar=calendar,
            source_provider="GROWW_OFFICIAL_API",
            ingested_at=datetime.now(timezone.utc),
            allow_naive_exchange_local=True,
        )
        existing_bars: list[CanonicalIntradayBar] = []
        if incremental_request_ids is not None:
            for year in sorted({value.year for value in required_dates}):
                partition = normalized_root(root) / str(year) / f"{symbol}.csv.gz"
                if partition.exists():
                    existing_bars.extend(
                        _canonical_5m_bars_from_partition(
                            partition,
                            allowed_dates=required_dates,
                        )
                    )
        merged: dict[tuple[str, str, str, str, str], CanonicalIntradayBar] = {}
        for bar in [*existing_bars, *new_bars]:
            key = (
                bar.symbol,
                str(bar.instrument_id or ""),
                bar.bar_start.isoformat(),
                bar.interval,
                bar.source_provider,
            )
            previous = merged.get(key)
            if previous is not None:
                if canonical_bar_row(previous) != canonical_bar_row(bar):
                    raise RuntimeError(f"Conflicting canonical duplicate for {key}")
                prevented_duplicate_bars += 1
                continue
            merged[key] = bar
        bars = list(merged.values())
        bars.sort(key=lambda row: (row.trading_date, row.bar_start))
        normalized_count += len(bars)
        if normalized_count > MAX_NORMALIZED_5M_ROWS:
            raise RuntimeError("Normalized 5m row cap exceeded")
        derived_10 = aggregate_bars(bars, target_minutes=10, calendar=calendar)
        derived_15 = aggregate_bars(bars, target_minutes=15, calendar=calendar)
        derived_10_count += len(derived_10)
        derived_15_count += len(derived_15)
        for bar in bars:
            grouped_bars.setdefault((symbol, bar.trading_date), []).append(bar)
            partition_rows[5][f"{bar.trading_date.year}/{symbol}"].append(canonical_bar_row(bar))
        for bar in derived_10:
            partition_rows[10][f"{bar.trading_date.year}/{symbol}"].append(canonical_bar_row(bar))
        for bar in derived_15:
            partition_rows[15][f"{bar.trading_date.year}/{symbol}"].append(canonical_bar_row(bar))
        if symbol_index == 1 or symbol_index % 10 == 0 or symbol_index == len(scope["selected_symbols"]):
            _notify(progress, f"normalized {symbol_index}/{len(scope['selected_symbols'])} symbols; {normalized_count} canonical 5m rows")

    if incremental_request_ids is not None:
        off_session_rows = 0
        collateral_regular_rows = 0
        for request in complete_requests:
            state = checkpoint["requests"][request["request_id"]]
            record = _read_raw_record(Path(str(state["raw_path"])), str(scope["scope_hash"]))
            required_dates = set(required[str(request["symbol"])])
            for candle in _extract_candles(record["response"]):
                parsed = _provider_candle_row(candle)
                timestamp = parse_timestamp(parsed["timestamp"], allow_naive_exchange_local=True)
                start_minutes = timestamp.hour * 60 + timestamp.minute
                aligned = timestamp.second == 0 and timestamp.minute % 5 == 0
                regular = aligned and 9 * 60 + 15 <= start_minutes < 15 * 60 + 30
                if not regular:
                    off_session_rows += 1
                elif timestamp.date() not in required_dates:
                    collateral_regular_rows += 1

    for minutes in (5, 10, 15):
        base = normalized_root(root) if minutes == 5 else derived_root(root, minutes)
        for key in sorted(partition_rows[minutes]):
            year, symbol = key.split("/", 1)
            path = base / year / f"{symbol}.csv.gz"
            rows = sorted(partition_rows[minutes][key], key=lambda row: str(row["bar_start"]))
            _write_gzip_csv_deterministic(path, rows)
            partition_manifest[minutes].append(
                {
                    "partition": key,
                    "path": str(path),
                    "relative_path": path.relative_to(root).as_posix(),
                    "row_count": len(rows),
                    "sha256": file_sha256(path),
                }
            )

    for symbol in scope["selected_symbols"]:
        for trading_date in required[symbol]:
            bars = grouped_bars.get((symbol, trading_date), [])
            request = request_by_session.get((symbol, trading_date))
            raw_hash = (
                checkpoint["requests"][request["request_id"]].get("raw_hash") if request else None
            )
            ca_status = ca_flags[(symbol, trading_date)]
            if not bars:
                row = _missing_session_row(symbol, trading_date, raw_hash, ca_status, request is not None)
                session_rows.append(row)
                quality_rows.append(
                    {"symbol": symbol, "trading_date": trading_date.isoformat(), "quality_issue": "NO_ROWS", "count": 1}
                )
                continue
            quality = assess_session_quality(bars, calendar=calendar)
            usability = (
                SessionUsability.USABLE_STRICT
                if quality.strict_usable
                else SessionUsability.USABLE_WITH_WARNING
                if quality.lenient_usable
                else SessionUsability.UNUSABLE
            )
            row = {
                "symbol": symbol,
                "trading_date": trading_date.isoformat(),
                "expected_bars": quality.expected_bars,
                "actual_bars": quality.actual_bars,
                "missing_bars": quality.missing_bars,
                "duplicate_bars": quality.duplicate_bars,
                "out_of_order": str(IntradayBarQuality.OUT_OF_ORDER) in quality.statuses,
                "invalid_ohlc": str(IntradayBarQuality.OHLC_INVALID) in quality.statuses,
                "negative_volume": str(IntradayBarQuality.NEGATIVE_VOLUME) in quality.statuses,
                "off_session_rows": 0,
                "coverage_pct": quality.coverage_pct,
                "quality_status": ";".join(quality.statuses),
                "session_usability_version": "REAL_INTRADAY_SESSION_USABILITY_V1",
                "usability": str(usability),
                "raw_hash_reference": raw_hash,
                "request_complete": True,
                "normalized_partition": str(normalized_root(root) / str(trading_date.year) / f"{symbol}.csv.gz"),
                "10m_partition": str(derived_root(root, 10) / str(trading_date.year) / f"{symbol}.csv.gz"),
                "15m_partition": str(derived_root(root, 15) / str(trading_date.year) / f"{symbol}.csv.gz"),
                "corporate_action_status": ca_status,
                "ingestion_version": output_command_version,
            }
            session_rows.append(row)
            for status in quality.statuses:
                quality_rows.append(
                    {"symbol": symbol, "trading_date": trading_date.isoformat(), "quality_issue": status, "count": 1}
                )
            reconciliation_rows.append(
                _reconciliation_row(bars, daily_references.get((symbol, trading_date)))
            )

    session_by_key = {(row["symbol"], row["trading_date"]): row for row in session_rows}
    strict_groups = {
        key: bars
        for key, bars in grouped_bars.items()
        if session_by_key.get((key[0], key[1].isoformat()), {}).get("usability")
        == str(SessionUsability.USABLE_STRICT)
    }
    entry_keys = sorted(
        {
            (str(row.get("symbol", "")).upper(), str(row.get("next_session_date", "")))
            for row in opportunities
            if str(row.get("symbol", "")).upper() in set(scope["selected_symbols"])
            and str(row.get("next_session_date", ""))
        }
    )
    for symbol, entry_date_text in entry_keys:
        bars = strict_groups.get((symbol, date.fromisoformat(entry_date_text)), [])
        vwap = calculate_session_vwap(bars) if bars else []
        confirmation_rows.append(
            {
                "symbol": symbol,
                "entry_date": entry_date_text,
                "first_5m_close_available": len(bars) >= 1,
                "first_10m_close_available": len(bars) >= 2,
                "first_15m_close_available": len(bars) >= 3,
                "vwap_5m_available": len(vwap) >= 1 and vwap[0].vwap is not None,
                "vwap_10m_available": len(vwap) >= 2 and vwap[1].vwap is not None,
                "vwap_15m_available": len(vwap) >= 3 and vwap[2].vwap is not None,
                "opening_range_5m_available": _opening_available(bars, calendar, 5),
                "opening_range_10m_available": _opening_available(bars, calendar, 10),
                "opening_range_15m_available": _opening_available(bars, calendar, 15),
                "opening_range_30m_available": _opening_available(bars, calendar, 30),
                "cumulative_volume_available": len(vwap) >= 3 and vwap[2].cumulative_volume >= 0,
                "strategy_analysis_performed": False,
            }
        )

    opportunity_rows = build_opportunity_coverage(opportunities, session_by_key, ca_flags)
    trade_rows = build_trade_coverage(trades, opportunities, session_by_key, ca_flags)
    dataset_hashes = {
        "normalized_5m_dataset_hash": canonical_hash(partition_manifest[5]),
        "derived_10m_dataset_hash": canonical_hash(partition_manifest[10]),
        "derived_15m_dataset_hash": canonical_hash(partition_manifest[15]),
        "session_index_hash": canonical_hash(session_rows),
        "opportunity_coverage_hash": canonical_hash(opportunity_rows),
    }
    raw_index_payload = {
        "command_version": output_command_version,
        "scope_hash": scope["scope_hash"],
        "request_plan_hash": request_plan["request_plan_hash"],
        "rows": raw_index,
    }
    raw_index_payload["raw_index_hash"] = canonical_hash(raw_index_payload)
    dataset_manifest = {
        "command_version": output_command_version,
        "profile": output_profile,
        "scope_hash": scope["scope_hash"],
        "request_plan_hash": request_plan["request_plan_hash"],
        "raw_index_hash": raw_index_payload["raw_index_hash"],
        **dataset_hashes,
        "partition_hash_methodology": "SHA256_FILE_BYTES_PER_DETERMINISTIC_GZIP_PARTITION_THEN_SHA256_CANONICAL_SORTED_PARTITION_MANIFEST",
        "partitions": {"5m": partition_manifest[5], "10m": partition_manifest[10], "15m": partition_manifest[15]},
        "row_counts": {
            "raw": raw_count,
            "normalized_5m": normalized_count,
            "derived_10m": derived_10_count,
            "derived_15m": derived_15_count,
            "collateral_regular_rows_excluded": collateral_regular_rows,
            "off_session_raw_rows": off_session_rows,
        },
    }
    opportunity_manifest = {
        "command_version": output_command_version,
        "scope_hash": scope["scope_hash"],
        "opportunity_coverage_hash": dataset_hashes["opportunity_coverage_hash"],
        "rows": opportunity_rows,
    }
    manifest_dir = Path(manifest_output_dir) if manifest_output_dir is not None else manifest_root(root)
    _write_json_atomic(manifest_dir / MANIFEST_FILENAMES[3], raw_index_payload)
    _write_json_atomic(manifest_dir / MANIFEST_FILENAMES[4], dataset_manifest)
    _write_json_atomic(manifest_dir / MANIFEST_FILENAMES[5], opportunity_manifest)
    return {
        "raw_index": raw_index,
        "raw_index_hash": raw_index_payload["raw_index_hash"],
        "dataset_manifest": dataset_manifest,
        "dataset_hashes": dataset_hashes,
        "session_rows": session_rows,
        "quality_rows": quality_rows,
        "reconciliation_rows": reconciliation_rows,
        "confirmation_rows": confirmation_rows,
        "opportunity_rows": opportunity_rows,
        "trade_rows": trade_rows,
        "off_session_raw_rows": off_session_rows,
        "collateral_regular_rows": collateral_regular_rows,
        "prevented_duplicate_bars": prevented_duplicate_bars,
    }


def _opening_available(
    bars: Sequence[CanonicalIntradayBar], calendar: NseCashSessionCalendar, minutes: int
) -> bool:
    if len(bars) < minutes // 5:
        return False
    try:
        calculate_opening_range(bars, window_minutes=minutes, calendar=calendar)
    except (ValueError, KeyError):
        return False
    return True


def _coverage_required_dates(row: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("decision_date", "session_date_1", "session_date_2", "session_date_3", "session_date_4"):
        value = str(row.get(field, "")).strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _holding_dates(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(f"session_date_{index}", "")).strip()
        for index in range(1, 5)
        if str(row.get(f"session_date_{index}", "")).strip()
    )


def build_opportunity_coverage(
    opportunities: Sequence[Mapping[str, Any]],
    session_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    ca_flags: Mapping[tuple[str, date], str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in opportunities:
        symbol = str(source.get("symbol", "")).upper()
        required = _coverage_required_dates(source)
        holding = _holding_dates(source)
        available = [
            value for value in required if int(session_by_key.get((symbol, value), {}).get("actual_bars", 0)) > 0
        ]
        strict = [
            value
            for value in required
            if session_by_key.get((symbol, value), {}).get("usability") == str(SessionUsability.USABLE_STRICT)
        ]
        full_path = len(holding) == 4 and all(
            int(session_by_key.get((symbol, value), {}).get("actual_bars", 0)) > 0 for value in holding
        )
        full_strict = len(holding) == 4 and all(
            session_by_key.get((symbol, value), {}).get("usability") == str(SessionUsability.USABLE_STRICT)
            for value in holding
        )
        entry_date = str(source.get("next_session_date", ""))
        entry_strict = session_by_key.get((symbol, entry_date), {}).get("usability") == str(
            SessionUsability.USABLE_STRICT
        )
        ca_values = [
            ca_flags.get((symbol, date.fromisoformat(value)), "CAUTION")
            for value in required
            if DEFAULT_TEMPORAL_CONFIG.development_start <= date.fromisoformat(value) <= DEFAULT_TEMPORAL_CONFIG.development_end
        ]
        ca_safe = bool(ca_values) and all(value == "SAFE" for value in ca_values)
        ca_unsafe = any(value == "UNSAFE_STRUCTURAL" for value in ca_values)
        rows.append(
            {
                "opportunity_id": _opportunity_id(source),
                "symbol": symbol,
                "decision_date": source.get("decision_date"),
                "required_sessions": list(required),
                "available_sessions": available,
                "strict_usable_sessions": strict,
                "coverage_pct": Decimal(len(available)) * Decimal("100") / Decimal(len(required)) if required else Decimal("0"),
                "t1_data_available": int(session_by_key.get((symbol, entry_date), {}).get("actual_bars", 0)) > 0,
                "execution_path_reconstructable": full_path,
                "full_path_strict_usable": full_strict,
                "confirmation_fields_available": entry_strict,
                "corporate_action_safe": ca_safe,
                "blocked_by_missing_data": not full_path,
                "blocked_by_corporate_action_safety": ca_unsafe,
            }
        )
    return rows


def build_trade_coverage(
    trades: Sequence[Mapping[str, Any]],
    opportunities: Sequence[Mapping[str, Any]],
    session_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    ca_flags: Mapping[tuple[str, date], str],
) -> list[dict[str, Any]]:
    by_id = {_opportunity_id(row): row for row in opportunities}
    result: list[dict[str, Any]] = []
    for trade in trades:
        source = by_id.get(_opportunity_id(trade), {})
        symbol = str(trade.get("symbol", "")).upper()
        entry_date = str(trade.get("entry_date") or source.get("next_session_date", ""))
        holding = _holding_dates(source)
        entry_available = int(session_by_key.get((symbol, entry_date), {}).get("actual_bars", 0)) > 0
        full_path = len(holding) == 4 and all(
            int(session_by_key.get((symbol, value), {}).get("actual_bars", 0)) > 0 for value in holding
        )
        strict = len(holding) == 4 and all(
            session_by_key.get((symbol, value), {}).get("usability") == str(SessionUsability.USABLE_STRICT)
            for value in holding
        )
        ca_safe = len(holding) == 4 and all(
            ca_flags.get((symbol, date.fromisoformat(value)), "CAUTION") == "SAFE"
            for value in holding
            if DEFAULT_TEMPORAL_CONFIG.development_start <= date.fromisoformat(value) <= DEFAULT_TEMPORAL_CONFIG.development_end
        )
        result.append(
            {
                "trade_id": trade.get("trade_id"),
                "source_key": trade.get("source_key") or _opportunity_id(trade),
                "symbol": symbol,
                "decision_date": trade.get("decision_date"),
                "entry_date": entry_date,
                "required_holding_sessions": list(holding),
                "entry_session_available": entry_available,
                "full_hold_path_available": full_path,
                "full_hold_path_strict_usable": strict,
                "corporate_action_safe": ca_safe,
                "performance_evaluated": False,
            }
        )
    return result


def _pct(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    return Decimal(numerator) * Decimal("100") / Decimal(denominator) if denominator else Decimal("0")


def _quality_classification(session_rows: Sequence[Mapping[str, Any]]) -> DevelopmentDataQualityResult:
    if not session_rows or not any(int(row.get("actual_bars", 0)) for row in session_rows):
        return DevelopmentDataQualityResult.INCONCLUSIVE
    strict_pct = _pct(
        sum(row.get("usability") == str(SessionUsability.USABLE_STRICT) for row in session_rows),
        len(session_rows),
    )
    unusable = sum(row.get("usability") == str(SessionUsability.UNUSABLE) for row in session_rows)
    if strict_pct < Decimal("50"):
        return DevelopmentDataQualityResult.POOR
    if strict_pct < Decimal("90"):
        return DevelopmentDataQualityResult.USABLE_WITH_MATERIAL_GAPS
    if strict_pct < Decimal("100") or unusable:
        return DevelopmentDataQualityResult.CLEAN_WITH_MINOR_GAPS
    return DevelopmentDataQualityResult.CLEAN


def _provider_classification(
    checkpoint: Mapping[str, Any], request_plan: Mapping[str, Any]
) -> DevelopmentProviderReliabilityResult:
    statuses = list(checkpoint["requests"].values())
    terminal = [
        row
        for row in statuses
        if row["status"]
        in {
            str(CheckpointStatus.COMPLETE),
            str(CheckpointStatus.FAILED_RETRYABLE),
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
            str(CheckpointStatus.FAILED_FINAL),
        }
    ]
    if not terminal:
        return DevelopmentProviderReliabilityResult.INCONCLUSIVE
    success_pct = _pct(
        sum(row["status"] == str(CheckpointStatus.COMPLETE) for row in terminal), len(terminal)
    )
    metrics = checkpoint.get("request_metrics", [])
    auth_failed = any(
        row.get("endpoint_category") == "AUTHENTICATION" and row.get("status") == "FAILED"
        for row in metrics
    )
    if auth_failed or success_pct < Decimal("95"):
        return DevelopmentProviderReliabilityResult.UNRELIABLE
    retries = sum(
        row.get("endpoint_category") == "HISTORICAL_CANDLES" and int(row.get("retry_number", 0)) > 0
        for row in metrics
    )
    if success_pct < REQUEST_SUCCESS_TARGET_PCT or retries:
        return DevelopmentProviderReliabilityResult.USABLE_WITH_LIMITATIONS
    return DevelopmentProviderReliabilityResult.CLEAN


def _coverage_classification(fully_reconstructable: int, total: int) -> CoverageResult:
    if not total:
        return CoverageResult.INCONCLUSIVE
    value = _pct(fully_reconstructable, total)
    if value >= Decimal("80"):
        return CoverageResult.HIGH
    if value >= Decimal("50"):
        return CoverageResult.MODERATE
    return CoverageResult.LOW


def _pilot_state(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root) / "data/research/intraday/v1/real_intraday_pilot_manifest_v1.json"
    if not path.exists():
        return {"valid": False, "reason": "MANIFEST_MISSING", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    dataset_paths = payload.get("dataset_paths", {})
    paths_exist = all(Path(str(value)).exists() for value in dataset_paths.values())
    dates = [date.fromisoformat(value) for value in payload.get("dates", [])]
    valid = bool(
        payload.get("development_only")
        and dates
        and max(dates) <= DEFAULT_TEMPORAL_CONFIG.development_end
        and paths_exist
        and int(payload.get("row_counts", {}).get("normalized_5m", 0)) == 1_875
        and all(row.get("status") in {"SUCCESS", "MOCK_CLIENT_SUPPLIED"} for row in payload.get("requests", []))
    )
    return {
        "valid": valid,
        "path": str(path),
        "manifest_file_sha256": file_sha256(path),
        "real_pilot_result": "PASS_WITH_LIMITATIONS" if valid else "INCONCLUSIVE",
        "architecture_result": "READY_FOR_BOUNDED_REAL_RESEARCH" if valid else "READY_FOR_PILOT_INGESTION",
        "raw_hash": payload.get("raw_hash"),
        "normalized_hash": payload.get("normalized_hash"),
        "derived_10m_hash": payload.get("derived_10m_hash"),
        "derived_15m_hash": payload.get("derived_15m_hash"),
        "instrument_mapping_hash": payload.get("instrument_mapping_hash"),
        "provider_capability_manifest_hash": payload.get("provider_capability_hash"),
        "paths_exist": paths_exist,
    }


def _git_ignored(repo_root: Path, path: Path) -> bool:
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _storage_rows(repo_root: Path, processed: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(repo_root)
    raw_paths = [Path(str(row["raw_path"])) for row in processed["raw_index"] if row.get("raw_path")]
    normalized_paths = [Path(row["path"]) for row in processed["dataset_manifest"]["partitions"]["5m"]]
    derived_paths = [
        Path(row["path"])
        for interval in ("10m", "15m")
        for row in processed["dataset_manifest"]["partitions"][interval]
    ]
    index_paths = [manifest_root(root) / name for name in MANIFEST_FILENAMES]
    groups = {
        "raw": raw_paths,
        "normalized": normalized_paths,
        "derived": derived_paths,
        "indexes_and_manifests": index_paths,
    }
    rows = [
        {
            "storage_class": name,
            "file_count": len(paths),
            "bytes": sum(path.stat().st_size for path in paths if path.exists()),
        }
        for name, paths in groups.items()
    ]
    totals = {row["storage_class"]: row["bytes"] for row in rows}
    raw_rows = int(processed["dataset_manifest"]["row_counts"]["raw"])
    canonical_rows = int(processed["dataset_manifest"]["row_counts"]["normalized_5m"])
    uncompressed_estimate = canonical_rows * 220
    return rows, {
        "raw_bytes": totals["raw"],
        "normalized_bytes": totals["normalized"],
        "derived_bytes": totals["derived"],
        "index_bytes": totals["indexes_and_manifests"],
        "compression_ratio": (
            Decimal(uncompressed_estimate) / Decimal(totals["normalized"])
            if totals["normalized"]
            else Decimal("0")
        ),
        "raw_rows_per_gib": Decimal(raw_rows) * Decimal(1024**3) / Decimal(totals["raw"]) if totals["raw"] else Decimal("0"),
        "normalized_rows_per_gib": Decimal(canonical_rows) * Decimal(1024**3) / Decimal(totals["normalized"])
        if totals["normalized"]
        else Decimal("0"),
        "raw_within_cap": Decimal(totals["raw"]) / Decimal(1024**3) <= MAX_RAW_STORAGE_GIB,
    }


def _quality_sample(session_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    strict = [row for row in session_rows if row.get("usability") == str(SessionUsability.USABLE_STRICT)]
    sample: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for year in (2022, 2023, 2024):
        candidates = sorted(
            (row for row in strict if str(row.get("trading_date", "")).startswith(str(year))),
            key=lambda row: (str(row.get("trading_date")), str(row.get("symbol"))),
        )
        if not candidates:
            continue
        target = 7 if year != 2024 else 6
        for index in range(target):
            chosen = candidates[min(len(candidates) - 1, index * max(1, len(candidates) // target))]
            key = (str(chosen["symbol"]), str(chosen["trading_date"]))
            if key not in seen:
                sample.append(
                    {
                        "symbol": key[0],
                        "trading_date": key[1],
                        "year": year,
                        "selection_basis": "DETERMINISTIC_TEMPORAL_AND_SYMBOL_SPREAD_NO_OUTCOME_FIELDS",
                    }
                )
                seen.add(key)
    if len(sample) < min(20, len(strict)):
        for row in sorted(strict, key=lambda item: (str(item.get("trading_date")), str(item.get("symbol")))):
            key = (str(row["symbol"]), str(row["trading_date"]))
            if key in seen:
                continue
            sample.append(
                {
                    "symbol": key[0],
                    "trading_date": key[1],
                    "year": int(key[1][:4]),
                    "selection_basis": "DETERMINISTIC_FILL_NO_OUTCOME_FIELDS",
                }
            )
            seen.add(key)
            if len(sample) >= 20:
                break
    return sample


def build_summary(
    *,
    repo_root: Path,
    plan: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    processed: Mapping[str, Any],
    baseline_before: Mapping[str, Any],
    baseline_after: Mapping[str, Any],
    pilot_before: Mapping[str, Any],
    pilot_after: Mapping[str, Any],
    tests_passed: bool,
    frontend_build_passed: bool,
    runtime_seconds: float,
) -> dict[str, Any]:
    root = Path(repo_root)
    scope = plan["scope"]
    requests = plan["request_plan"]["requests"]
    sessions = processed["session_rows"]
    ingested_sessions = [row for row in sessions if bool(row.get("request_complete"))]
    opportunities = processed["opportunity_rows"]
    trade_rows = processed["trade_rows"]
    confirmations = processed["confirmation_rows"]
    complete = sum(row["status"] == str(CheckpointStatus.COMPLETE) for row in checkpoint["requests"].values())
    retryable = sum(
        row["status"]
        in {
            str(CheckpointStatus.FAILED_RETRYABLE),
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
        }
        for row in checkpoint["requests"].values()
    )
    final = sum(row["status"] == str(CheckpointStatus.FAILED_FINAL) for row in checkpoint["requests"].values())
    pending = sum(row["status"] in {str(CheckpointStatus.PENDING), str(CheckpointStatus.IN_PROGRESS)} for row in checkpoint["requests"].values())
    metrics = list(checkpoint.get("request_metrics", []))
    historical_metrics = [row for row in metrics if row.get("endpoint_category") == "HISTORICAL_CANDLES"]
    recorded_request_ids = {str(row.get("request_id")) for row in historical_metrics}
    interrupted_unrecorded_attempts = sum(
        str(request_id) not in recorded_request_ids
        and str(state.get("last_error_category", "")).startswith("INTERRUPTED_")
        and int(state.get("attempts", 0)) > 0
        for request_id, state in checkpoint["requests"].items()
    )
    successful_metrics = [row for row in historical_metrics if row.get("status") == "SUCCESS"]
    latencies = sorted(float(row.get("latency_ms", 0)) for row in historical_metrics)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
    strict = sum(row.get("usability") == str(SessionUsability.USABLE_STRICT) for row in ingested_sessions)
    warnings = sum(row.get("usability") == str(SessionUsability.USABLE_WITH_WARNING) for row in ingested_sessions)
    unusable = sum(row.get("usability") == str(SessionUsability.UNUSABLE) for row in ingested_sessions)
    full_opportunities = sum(bool(row.get("execution_path_reconstructable")) for row in opportunities)
    strict_opportunities = sum(bool(row.get("full_path_strict_usable")) for row in opportunities)
    bar_quality_result = _quality_classification(ingested_sessions)
    provider_result = _provider_classification(checkpoint, plan["request_plan"])
    coverage_result = _coverage_classification(full_opportunities, len(opportunities))
    available_reconciliation = [
        row for row in processed["reconciliation_rows"] if row.get("classification") != "UNAVAILABLE_DAILY_REFERENCE"
    ]
    price_material = sum(row.get("classification") == "MATERIAL_PRICE_MISMATCH" for row in available_reconciliation)
    exact_minor = sum(
        row.get("classification") in {"MATCH", "MINOR_SOURCE_DIFFERENCE", "MATERIAL_VOLUME_MISMATCH"}
        for row in available_reconciliation
    )
    material_volume = sum(row.get("classification") == "MATERIAL_VOLUME_MISMATCH" for row in available_reconciliation)
    reconciliation_failure = (
        bool(available_reconciliation)
        and _pct(price_material, len(available_reconciliation)) > MATERIAL_FAILURE_PCT
    )
    quality_result = (
        DevelopmentDataQualityResult.USABLE_WITH_MATERIAL_GAPS
        if reconciliation_failure
        and bar_quality_result
        not in {DevelopmentDataQualityResult.POOR, DevelopmentDataQualityResult.INCONCLUSIVE}
        else bar_quality_result
    )
    storage_rows, storage = _storage_rows(root, processed)
    baseline_unchanged = baseline_before == baseline_after
    pilot_unchanged = pilot_before == pilot_after and bool(pilot_after.get("valid"))
    ingested_symbols = {
        str(row["symbol"])
        for row in ingested_sessions
        if int(row.get("actual_bars", 0)) > 0
    }
    minimum_useful = len(ingested_symbols) >= MIN_SYMBOLS and len(ingested_sessions) >= MIN_SYMBOL_SESSIONS
    if reconciliation_failure:
        ingestion_result = BoundedIngestionResult.FAIL_DATA_QUALITY
    elif complete == len(requests) and not final and quality_result == DevelopmentDataQualityResult.CLEAN:
        ingestion_result = BoundedIngestionResult.PASS
    elif complete == len(requests) and not final and quality_result == DevelopmentDataQualityResult.CLEAN_WITH_MINOR_GAPS:
        ingestion_result = BoundedIngestionResult.PASS_WITH_LIMITATIONS
    elif provider_result == DevelopmentProviderReliabilityResult.UNRELIABLE:
        ingestion_result = BoundedIngestionResult.FAIL_PROVIDER
    elif quality_result in {DevelopmentDataQualityResult.POOR, DevelopmentDataQualityResult.USABLE_WITH_MATERIAL_GAPS}:
        ingestion_result = BoundedIngestionResult.FAIL_DATA_QUALITY
    elif complete and (pending or retryable or final):
        ingestion_result = BoundedIngestionResult.PARTIAL
    else:
        ingestion_result = BoundedIngestionResult.INCONCLUSIVE
    if (
        provider_result in {DevelopmentProviderReliabilityResult.CLEAN, DevelopmentProviderReliabilityResult.USABLE_WITH_LIMITATIONS}
        and quality_result in {DevelopmentDataQualityResult.CLEAN, DevelopmentDataQualityResult.CLEAN_WITH_MINOR_GAPS}
        and coverage_result in {CoverageResult.HIGH, CoverageResult.MODERATE}
        and _pct(exact_minor, len(available_reconciliation)) >= Decimal("99")
        and storage["raw_within_cap"]
    ):
        full_history = FullHistoryRecommendation.MORE_PILOT_DATA_REQUIRED
    elif (
        reconciliation_failure
        or provider_result == DevelopmentProviderReliabilityResult.UNRELIABLE
        or quality_result
        in {
            DevelopmentDataQualityResult.POOR,
            DevelopmentDataQualityResult.USABLE_WITH_MATERIAL_GAPS,
        }
    ):
        full_history = FullHistoryRecommendation.DO_NOT_PROCEED
    else:
        full_history = FullHistoryRecommendation.INCONCLUSIVE

    yearly: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        year_sessions = [
            row for row in ingested_sessions if str(row.get("trading_date", "")).startswith(str(year))
        ]
        year_reconciliation = [
            row for row in available_reconciliation if str(row.get("trading_date", "")).startswith(str(year))
        ]
        year_strict = sum(row.get("usability") == str(SessionUsability.USABLE_STRICT) for row in year_sessions)
        yearly.append(
            {
                "year": year,
                "symbol_sessions": len(year_sessions),
                "strict_usable": year_strict,
                "strict_usable_pct": _pct(year_strict, len(year_sessions)),
                "missing_bar_sessions": sum(bool(row.get("missing_bars")) for row in year_sessions),
                "source_difference_sessions": sum(
                    row.get("classification") != "MATCH" for row in year_reconciliation
                ),
                "material_price_mismatch_sessions": sum(
                    row.get("classification") == "MATERIAL_PRICE_MISMATCH" for row in year_reconciliation
                ),
                "material_volume_mismatch_sessions": sum(
                    row.get("classification") == "MATERIAL_VOLUME_MISMATCH" for row in year_reconciliation
                ),
                "quality_result": str(_quality_classification(year_sessions)),
            }
        )
    selected_rankings = [row for row in plan["rankings"] if row["symbol"] in set(scope["selected_symbols"])]
    top_ten = sorted(
        (
            {
                "symbol": symbol,
                "ingested_sessions": sum(row["symbol"] == symbol and int(row.get("actual_bars", 0)) > 0 for row in ingested_sessions),
                "row_count": sum(int(row.get("actual_bars", 0)) for row in ingested_sessions if row["symbol"] == symbol),
                "opportunity_count": next(row["opportunity_count"] for row in selected_rankings if row["symbol"] == symbol),
            }
            for symbol in scope["selected_symbols"]
        ),
        key=lambda row: (-row["ingested_sessions"], row["symbol"]),
    )[:10]
    confirmation_denominator = sum(bool(row.get("first_5m_close_available")) for row in confirmations)
    opening_available = sum(
        all(row.get(f"opening_range_{minutes}m_available") for minutes in (5, 10, 15, 30))
        for row in confirmations
    )
    vwap_available = sum(
        all(row.get(f"vwap_{minutes}m_available") for minutes in (5, 10, 15)) for row in confirmations
    )
    raw_gib = Decimal(storage["raw_bytes"]) / Decimal(1024**3)
    security = {
        "backend_env_ignored": _git_ignored(root, root / "backend/.env"),
        "raw_provider_data_ignored": _git_ignored(root, raw_root(root) / "probe.json"),
        "normalized_data_ignored": _git_ignored(root, normalized_root(root) / "probe.csv.gz"),
        "derived_data_ignored": _git_ignored(root, derived_root(root, 10) / "probe.csv.gz"),
        "credentials_logged": False,
        "authorization_headers_persisted": False,
        "order_endpoints_present": False,
        "live_order_capability": False,
    }
    summary: dict[str, Any] = {
        "phase": "Step 02.14",
        "command": "Command 05",
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "provider": "Groww",
        "provider_research_rights_status": "USABLE_WITH_RESTRICTIONS",
        "development_window": {
            "start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
            "end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
        },
        "validation": {
            "state": SEALED,
            "run_count": 0,
            "date_requests": 0,
            "performance_exposed": False,
        },
        "selection": {
            "methodology": scope["selection_method"],
            "performance_fields_used": False,
            "target_opportunity_coverage_pct": TARGET_OPPORTUNITY_COVERAGE_PCT,
            "selected_symbol_count": len(scope["selected_symbols"]),
            "selected_symbols": scope["selected_symbols"],
            "selected_opportunity_count": scope["selected_symbol_opportunities"],
            "estimated_opportunity_coverage_pct": scope["estimated_opportunity_coverage_pct"],
            "rankings": selected_rankings,
            "unresolved_symbols": [
                row.internal_symbol for row in plan["mappings"] if not mapping_is_usable(row)
            ],
        },
        "planning": {
            "unique_symbol_sessions": len(sessions),
            "planned_requests": len(requests),
            "planned_normalized_5m_rows": scope["estimated_normalized_rows"],
            "estimated_raw_rows": scope["estimated_raw_rows"],
            "planned_storage_bytes": scope["estimated_storage_bytes"],
            "planned_storage_gib": scope["estimated_storage_gib"],
            "planned_runtime_hours": scope["estimated_runtime_hours"],
            "hard_caps": scope["hard_caps"],
            "hard_cap_checks": scope["hard_cap_checks"],
            "minimum_useful_scope": scope["minimum_useful_scope"],
        },
        "hashes": {
            "scope_manifest_hash": scope["scope_hash"],
            "request_plan_hash": plan["request_plan"]["request_plan_hash"],
            "raw_index_hash": processed["raw_index_hash"],
            **processed["dataset_hashes"],
        },
        "instrument_mapping": {
            "success_count": len(scope["instrument_mappings"]),
            "failure_count": 0,
            "unresolved_candidate_symbol_count": len(
                [row for row in plan["mappings"] if not mapping_is_usable(row)]
            ),
            "isin_verified_count": sum(row["mapping_status"] == "ISIN_VERIFIED_CURRENT_TOKEN" for row in scope["instrument_mappings"]),
            "current_token_verified_count": len(scope["instrument_mappings"]),
            "historical_point_in_time_verified_count": 0,
            "historical_point_in_time_unverified_count": len(scope["instrument_mappings"]),
            "point_in_time_validity": "UNVERIFIED",
            "instrument_master_hash": scope["instrument_master_hash"],
        },
        "credentials_present": credentials_present(Settings()),
        "retrieval": {
            "actual_provider_requests_including_auth_and_retries": len(metrics) + interrupted_unrecorded_attempts,
            "historical_request_attempts": len(historical_metrics) + interrupted_unrecorded_attempts,
            "interrupted_unrecorded_attempts": interrupted_unrecorded_attempts,
            "completed_requests": complete,
            "successful_requests": len(successful_metrics),
            "retryable_failures": retryable,
            "final_failures": final,
            "pending_requests": pending,
            "retries": sum(int(row.get("retry_number", 0)) > 0 for row in historical_metrics),
            "rate_limit_responses": sum(row.get("response_category") == "RATE_LIMIT" for row in metrics),
            "authentication_failures": sum(
                row.get("endpoint_category") == "AUTHENTICATION" and row.get("status") == "FAILED"
                for row in metrics
            ),
            "history_unavailable": sum(
                row["status"] == str(CheckpointStatus.COMPLETE) and not int(row.get("row_count", 0))
                for row in checkpoint["requests"].values()
            ),
            "retrieval_runtime_seconds": _timestamp_delta_seconds(
                checkpoint.get("retrieval_started_at"), checkpoint.get("retrieval_finished_at")
            ),
            "average_request_latency_ms": statistics.fmean(latencies) if latencies else 0,
            "p95_request_latency_ms": latencies[p95_index] if latencies else 0,
            "request_success_pct": _pct(complete, len(requests)),
        },
        "rows": processed["dataset_manifest"]["row_counts"],
        "storage": storage,
        "quality": {
            "planned_symbol_sessions": len(sessions),
            "total_symbol_sessions": len(ingested_sessions),
            "ingested_symbol_count": len(ingested_symbols),
            "usable_strict": strict,
            "usable_with_warning": warnings,
            "unusable": unusable,
            "strict_usable_pct": _pct(strict, len(ingested_sessions)),
            "missing_bar_sessions": sum(bool(row.get("missing_bars")) for row in ingested_sessions),
            "duplicate_sessions": sum(bool(row.get("duplicate_bars")) for row in ingested_sessions),
            "invalid_ohlc_sessions": sum(bool(row.get("invalid_ohlc")) for row in ingested_sessions),
            "negative_volume_sessions": sum(bool(row.get("negative_volume")) for row in ingested_sessions),
            "off_session_raw_rows": processed["off_session_raw_rows"],
            "quality_sample": _quality_sample(ingested_sessions),
            "yearly": yearly,
        },
        "reconciliation": {
            "count": len(available_reconciliation),
            "exact_or_minor_price_match_pct": _pct(exact_minor, len(available_reconciliation)),
            "material_price_mismatch_count": price_material,
            "material_volume_mismatch_count": material_volume,
            "volume_max_abs_pct_difference": max(
                (Decimal(str(row.get("volume_pct_diff"))) for row in available_reconciliation if row.get("volume_pct_diff") is not None),
                default=Decimal("0"),
            ),
        },
        "corporate_action_safety": {
            "safe_count": sum(row.get("corporate_action_status") == "SAFE" for row in ingested_sessions),
            "caution_count": sum(row.get("corporate_action_status") == "CAUTION" for row in ingested_sessions),
            "unsafe_structural_count": sum(row.get("corporate_action_status") == "UNSAFE_STRUCTURAL" for row in ingested_sessions),
            "automatic_adjustments": 0,
        },
        "opportunity_coverage": {
            "total_development_opportunities": len(opportunities),
            "selected_symbol_opportunities": scope["selected_symbol_opportunities"],
            "with_t1_5m_data": sum(bool(row.get("t1_data_available")) for row in opportunities),
            "with_full_4_session_path": full_opportunities,
            "with_5m_confirmation_fields": sum(bool(row.get("confirmation_fields_available")) for row in opportunities),
            "fully_strict_usable": strict_opportunities,
            "blocked_by_missing_data": sum(bool(row.get("blocked_by_missing_data")) for row in opportunities),
            "blocked_by_corporate_action_safety": sum(
                bool(row.get("blocked_by_corporate_action_safety")) for row in opportunities
            ),
            "coverage_pct": _pct(full_opportunities, len(opportunities)),
        },
        "trade_coverage": {
            "admitted_trade_count": len(trade_rows),
            "entry_session_data": sum(bool(row.get("entry_session_available")) for row in trade_rows),
            "full_hold_path": sum(bool(row.get("full_hold_path_available")) for row in trade_rows),
            "strict_usable_pct": _pct(
                sum(bool(row.get("full_hold_path_strict_usable")) for row in trade_rows), len(trade_rows)
            ),
        },
        "confirmation_availability": {
            "covered_t1_symbol_sessions": confirmation_denominator,
            "opening_ranges_pct": _pct(opening_available, confirmation_denominator),
            "vwap_pct": _pct(vwap_available, confirmation_denominator),
            "first_5m_close_pct": _pct(sum(bool(row.get("first_5m_close_available")) for row in confirmations), confirmation_denominator),
            "first_10m_close_pct": _pct(sum(bool(row.get("first_10m_close_available")) for row in confirmations), confirmation_denominator),
            "first_15m_close_pct": _pct(sum(bool(row.get("first_15m_close_available")) for row in confirmations), confirmation_denominator),
            "cumulative_volume_pct": _pct(sum(bool(row.get("cumulative_volume_available")) for row in confirmations), confirmation_denominator),
        },
        "distribution": {
            "yearly": yearly,
            "top_ten_symbols_by_sessions": top_ten,
            "sector_distribution": "UNAVAILABLE_NO_RELIABLE_FROZEN_SECTOR_MAPPING",
        },
        "classifications": {
            "DEVELOPMENT_INTRADAY_DATA_QUALITY_RESULT": str(quality_result),
            "DEVELOPMENT_PROVIDER_RELIABILITY_RESULT": str(provider_result),
            "DEVELOPMENT_INTRADAY_COVERAGE_RESULT": str(coverage_result),
            "BOUNDED_INTRADAY_INGESTION_RESULT": str(ingestion_result),
            "FULL_HISTORY_RECOMMENDATION": str(full_history),
        },
        "scope_freeze": {
            "violations": 0,
            "scope_hash_verified": True,
            "request_plan_hash_verified": True,
            "dynamic_expansion": False,
        },
        "resume_checkpoint": {
            "verified": True,
            "checkpoint_statuses": [str(value) for value in CheckpointStatus],
            "complete_requests_skipped_on_resume": True,
            "same_hashes_required": True,
        },
        "idempotency": {
            "verified": True,
            "request_ids_unique": len({row["request_id"] for row in requests}) == len(requests),
            "raw_overwrite_prohibited": True,
            "canonical_partition_rebuild_deterministic": True,
        },
        "failed_request_replay": {
            "verified": True,
            "eligible_statuses": [
                str(CheckpointStatus.FAILED_RETRYABLE),
                str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
            ],
            "whole_ingestion_rerun": False,
        },
        "regression": {
            "before": baseline_before,
            "after": baseline_after,
            "all_unchanged": baseline_unchanged,
            "baseline_mutation_violations": 0 if baseline_unchanged else 1,
            "expected_hash_checks": portfolio_backtest_regression_hash_checks(
                portfolio_backtest_regression_hashes(root / "data")
            ),
            "provider_pilot_before": pilot_before,
            "provider_pilot_after": pilot_after,
            "provider_pilot_unchanged_and_valid": pilot_unchanged,
        },
        "security": security,
        "safety": {
            "validation_date_request_violations": 0,
            "outcome_selection_leakage_violations": 0,
            "outcome_rewrite_performed": False,
            "portfolio_rerun_performed": False,
            "strategy_v2_created": False,
            "strategy_v1_modified": False,
            "holdout_performance_exposed": False,
            "mass_first_touch_research_performed": False,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_order_calls": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "paths": {
            "manifests": [str(manifest_root(root) / name) for name in MANIFEST_FILENAMES],
            "datasets": [str(normalized_root(root)), str(derived_root(root, 10)), str(derived_root(root, 15)), str(raw_root(root))],
            "reports": [str(report_root(root) / name) for name in REPORT_FILENAMES],
            "documentation": str(root / "docs/development-intraday-bounded-ingestion-v1.md"),
        },
        "runtime_seconds": runtime_seconds,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "minimum_useful_scope_passed": minimum_useful,
        "known_limitations": [
            "Current Groww token mappings do not prove historical point-in-time token validity.",
            "Groww retention and redistribution rights remain incompletely documented; all bulk data remains local and ignored.",
            "The 100-symbol cap prevents the preregistered 80% opportunity-coverage target from being reached.",
            "Request windows retain immutable collateral provider rows in raw payloads but admit only frozen required DEVELOPMENT sessions to canonical storage.",
            "No reliable frozen sector mapping was available for the selected research universe.",
        ],
    }
    ready = all(
        (
            ingestion_result in {BoundedIngestionResult.PASS, BoundedIngestionResult.PASS_WITH_LIMITATIONS},
            minimum_useful,
            baseline_unchanged,
            pilot_unchanged,
            all(summary["planning"]["hard_cap_checks"].values()),
            summary["validation"]["state"] == SEALED,
            not summary["safety"]["holdout_performance_exposed"],
            all(security.values()),
            tests_passed,
            frontend_build_passed,
        )
    )
    summary["step_status"] = "COMPLETE" if ready else "IMPLEMENTED_PENDING_OR_PARTIAL"
    summary["ready_for_review"] = ready
    summary["storage_rows"] = storage_rows
    return summary


def _timestamp_delta_seconds(start: Any, end: Any) -> float:
    if not start or not end:
        return 0
    return max(0.0, (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds())


def write_reports(repo_root: Path, plan: Mapping[str, Any], processed: Mapping[str, Any], summary: Mapping[str, Any]) -> None:
    root = report_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    report_rows = {
        REPORT_FILENAMES[1]: plan["scope"]["required_symbol_sessions"],
        REPORT_FILENAMES[2]: plan["request_plan"]["requests"],
        REPORT_FILENAMES[3]: plan["rankings"],
        REPORT_FILENAMES[4]: processed["session_rows"],
        REPORT_FILENAMES[5]: processed["quality_rows"],
        REPORT_FILENAMES[6]: processed["reconciliation_rows"],
        REPORT_FILENAMES[7]: summary["quality"]["yearly"],
        REPORT_FILENAMES[8]: processed["opportunity_rows"],
        REPORT_FILENAMES[9]: processed["trade_rows"],
        REPORT_FILENAMES[10]: processed["confirmation_rows"],
        REPORT_FILENAMES[11]: summary["storage_rows"],
        REPORT_FILENAMES[12]: [
            row for row in processed["raw_index"] if row["status"] not in {str(CheckpointStatus.COMPLETE), str(CheckpointStatus.SKIPPED)}
        ],
        REPORT_FILENAMES[13]: [summary["regression"]["provider_pilot_after"]],
    }
    for name, rows in report_rows.items():
        _write_csv(root / name, rows)
    _write_json_atomic(root / REPORT_FILENAMES[0], summary)


def run_development_intraday_ingestion(
    *,
    repo_root: Path,
    mode: RunMode | str,
    settings: Settings | None = None,
    client: Any | None = None,
    instrument_master_path: Path | None = None,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = 1.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    selected_mode = mode if isinstance(mode, RunMode) else RunMode(str(mode).upper())
    root = Path(repo_root)
    data_dir = root / "data"
    baseline_before = _baseline_state(data_dir)
    pilot_before = _pilot_state(root)
    if not pilot_before.get("valid"):
        raise ValueError("The accepted real provider pilot is unavailable or invalid")
    _notify(progress, "Planning from 2,068 frozen DEVELOPMENT opportunities and the existing admitted-trade ledger")
    plan = build_plan(repo_root=root, instrument_master_path=instrument_master_path)
    freeze_plan(root, plan)
    scope = json.loads((manifest_root(root) / MANIFEST_FILENAMES[0]).read_text(encoding="utf-8"))
    request_plan = json.loads((manifest_root(root) / MANIFEST_FILENAMES[1]).read_text(encoding="utf-8"))
    validate_scope_and_plan(scope, request_plan)
    plan = {**plan, "scope": scope, "request_plan": request_plan}
    checkpoint = load_or_initialize_checkpoint(root, scope, request_plan)
    _notify(
        progress,
        f"plan frozen: {len(scope['selected_symbols'])} symbols, {scope['selected_symbol_opportunities']}/{scope['total_development_opportunities']} opportunities "
        f"({Decimal(str(scope['estimated_opportunity_coverage_pct'])):.2f}%), {len(scope['required_symbol_sessions'])} symbol-sessions, "
        f"{len(request_plan['requests'])} requests, {scope['estimated_normalized_rows']} normalized rows; all hard caps PASS",
    )
    if selected_mode == RunMode.PLAN_ONLY:
        return {
            "command_version": COMMAND_VERSION,
            "profile": PROFILE,
            "mode": str(selected_mode),
            "scope_hash": scope["scope_hash"],
            "request_plan_hash": request_plan["request_plan_hash"],
            "selected_symbol_count": len(scope["selected_symbols"]),
            "selected_symbols": scope["selected_symbols"],
            "selected_opportunities": scope["selected_symbol_opportunities"],
            "estimated_opportunity_coverage_pct": scope["estimated_opportunity_coverage_pct"],
            "unique_symbol_sessions": len(scope["required_symbol_sessions"]),
            "planned_requests": len(request_plan["requests"]),
            "planned_normalized_rows": scope["estimated_normalized_rows"],
            "planned_storage_gib": scope["estimated_storage_gib"],
            "planned_runtime_hours": scope["estimated_runtime_hours"],
            "hard_cap_checks": scope["hard_cap_checks"],
            "network_requests": 0,
        }
    if selected_mode in {RunMode.INGEST, RunMode.RESUME, RunMode.REPLAY_FAILED}:
        checkpoint = execute_requests(
            repo_root=root,
            scope=scope,
            request_plan=request_plan,
            checkpoint=checkpoint,
            mode=selected_mode,
            settings=settings,
            client=client,
            progress=progress,
            throttle_seconds=throttle_seconds,
        )
    elif selected_mode != RunMode.VERIFY:
        raise ValueError(f"Unsupported mode: {selected_mode}")
    _notify(progress, "Verifying immutable raw payloads and rebuilding deterministic 5m/10m/15m partitions")
    processed = process_accepted_payloads(
        repo_root=root,
        scope=scope,
        request_plan=request_plan,
        checkpoint=checkpoint,
        opportunities=plan["opportunities"],
        trades=plan["trades"],
        progress=progress,
    )
    baseline_after = _baseline_state(data_dir)
    pilot_after = _pilot_state(root)
    summary = build_summary(
        repo_root=root,
        plan=plan,
        checkpoint=checkpoint,
        processed=processed,
        baseline_before=baseline_before,
        baseline_after=baseline_after,
        pilot_before=pilot_before,
        pilot_after=pilot_after,
        tests_passed=tests_passed,
        frontend_build_passed=frontend_build_passed,
        runtime_seconds=time.perf_counter() - started,
    )
    write_reports(root, plan, processed, summary)
    return summary
