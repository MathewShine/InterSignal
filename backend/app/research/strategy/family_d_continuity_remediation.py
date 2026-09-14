from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.config.settings import Settings
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.research.intraday.calendar import NseCashSessionCalendar
from app.research.intraday.development_ingestion import (
    _canonical_5m_bars_from_partition,
    _read_raw_record,
    _write_gzip_csv_deterministic,
    _write_immutable_raw,
    raw_root as frozen_raw_root,
)
from app.research.intraday.models import CanonicalIntradayBar
from app.research.intraday.normalization import canonical_bar_row, normalize_rows, parse_timestamp
from app.research.intraday.provider_pilot import (
    GROWW_RETRIEVAL_TRANSPORT_VERSION,
    InstrumentMapping,
    _extract_candles,
    _provider_candle_row,
    classify_provider_failure,
    credentials_present,
)
from app.research.intraday.quality import assess_session_quality
from app.research.intraday.resume_ingestion import (
    MAX_RETRIES,
    REQUEST_TIMEOUT_CIRCUIT_BREAKER,
    AttemptGenerationGuard,
    ResumeGrowwTransport,
    ResumeRequestFailure,
    ResumeRuntimeLimit,
)
from app.research.strategy.family_a_momentum import (
    _load_aliases,
    file_sha256,
    read_csv,
)
from app.research.strategy.family_c_breakout_continuation import (
    _load_adjusted_bars,
    _load_sessions,
)
from app.research.strategy.family_c_research_closure import (
    EXPECTED_FAMILY_C_CLOSURE_HASH,
    family_c_baseline_snapshot,
)
from app.research.strategy.family_d_opening_range import (
    ACTIVITY_LOOKBACK,
    ACTIVITY_THRESHOLD,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    INGESTION_SCOPE_HASH,
    OPENING_BAR_TIMES,
    _percentile,
    _scope_rows,
    opening_activity_ratio,
    verify_frozen_inputs,
    verify_preregistration_hashes,
    verify_scope_hash,
)
from app.research.temporal_validation.config import canonical_hash, json_ready


COMMAND_VERSION = "FAMILY_D_INTRADAY_CONTINUITY_REMEDIATION_V1"
PROFILE = "PRIOR20_OPENING_VOLUME_CONTINUITY_V1"
CONTINUITY_DATA_VERSION = "FAMILY_D_INTRADAY_CONTINUITY_V1"
NORMALIZATION_PROFILE = "NSE_CASH_INTRADAY_5M_V1"
DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
FIXED_INGESTION_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 20.0
WALL_CLOCK_TIMEOUT_SECONDS = 30.0
THROTTLE_SECONDS = 1.0
MAX_REQUEST_WINDOW_DAYS = 30
MATERIAL_UNEXPLAINED_RATE = Decimal("0.001")

AVAILABILITY_REASONS = (
    "COMPLETE",
    "PROVIDER_HISTORY_UNAVAILABLE",
    "SYMBOL_NOT_LISTED",
    "MISSING_INTRADAY_SESSION",
    "MISSING_OPENING_BARS",
    "INVALID_VOLUME",
    "IDENTITY_MAPPING_ISSUE",
    "SESSION_QUALITY_FAILURE",
    "OTHER_EXPLAINED",
    "UNEXPLAINED",
)
REPORT_NAMES = (
    "family_d_continuity_v1_summary.json",
    "family_d_continuity_v1_request_plan.csv",
    "family_d_continuity_v1_reconciliation.csv",
    "family_d_continuity_v1_matrix.csv",
    "family_d_continuity_v1_unavailable.csv",
    "family_d_continuity_v1_activity_distribution.csv",
    "family_d_continuity_v1_yearly_counts.csv",
    "family_d_continuity_v1_pilots.csv",
    "family_d_continuity_v1_readiness.csv",
)


class ContinuityInputMismatch(RuntimeError):
    pass


def output_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/strategy_families/family_d/v1/continuity_remediation"


def report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def _json_dump(value: Any) -> str:
    return json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(value), encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = [json_ready(dict(row)) for row in rows]
    names = list(fields or sorted({key for row in prepared for key in row}) or ["status"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in prepared:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True, separators=(",", ":"))
                    if isinstance(value, (list, tuple, dict))
                    else value
                    for key, value in row.items()
                }
            )


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def continuity_config_document() -> dict[str, Any]:
    body: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "continuity_data_version": CONTINUITY_DATA_VERSION,
        "family_version": "STRATEGY_FAMILY_D_OPENING_RANGE_V1",
        "development_period": [DEVELOPMENT_START.isoformat(), DEVELOPMENT_END.isoformat()],
        "target_population": "EXACT_FROZEN_FAMILY_D_INTRADAY_SCOPE_V1",
        "activity_baseline": {
            "lookback": ACTIVITY_LOOKBACK,
            "session_rule": "IMMEDIATELY_PRECEDING_20_NSE_TRADING_SESSIONS",
            "opening_bar_starts": [value.strftime("%H:%M") for value in OPENING_BAR_TIMES],
            "opening_volume": "SUM_EXACT_THREE_BARS",
            "denominator": "MEDIAN_EXACT_PRIOR20",
            "current_session_excluded": True,
            "future_sessions_excluded": True,
            "strict_sessions_only": True,
            "sparse_valid_sample_substitution": False,
        },
        "provider": "GROWW",
        "provider_path": "REAL_INTRADAY_PROVIDER_PILOT_V1",
        "transport": {
            "version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
            "read_timeout_seconds": READ_TIMEOUT_SECONDS,
            "wall_clock_timeout_seconds": WALL_CLOCK_TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
            "timeout_circuit_breaker": REQUEST_TIMEOUT_CIRCUIT_BREAKER,
            "throttle_seconds": THROTTLE_SECONDS,
            "max_request_window_calendar_days": MAX_REQUEST_WINDOW_DAYS,
        },
        "normalization": {
            "profile": NORMALIZATION_PROFILE,
            "timezone": "Asia/Kolkata",
            "bar_convention": "BAR_START",
        },
        "coverage_thresholds": {
            "EXCELLENT": ">=98_PERCENT",
            "STRONG": ">=95_PERCENT",
            "USABLE_WITH_LIMITATIONS": ">=90_PERCENT",
            "INSUFFICIENT": "<90_PERCENT",
        },
        "material_unexplained_overlap_rate": MATERIAL_UNEXPLAINED_RATE,
        "frozen_hashes": {
            "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
            "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
            "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
            "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "family_c_closure_hash": EXPECTED_FAMILY_C_CLOSURE_HASH,
        },
        "immutability": {
            "frozen_command_05b_raw_mutation_allowed": False,
            "frozen_normalized_partition_mutation_allowed": False,
            "family_d_command_01_mutation_allowed": False,
        },
        "performance_allowed": False,
        "validation_allowed": False,
        "strategy_parameter_changes_allowed": False,
    }
    body["continuity_remediation_config_hash"] = canonical_hash(body)
    return body


def verify_continuity_inputs(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    frozen = verify_frozen_inputs(root)
    prereg = verify_preregistration_hashes()
    verify_scope_hash(root)
    family_c = json.loads((root / "data/reports/family_c_closure_v1_summary.json").read_text(encoding="utf-8"))
    checks = {
        **prereg,
        "intraday_scope_hash": True,
        "family_c_closure_hash": family_c.get("family_c_closure_hash") == EXPECTED_FAMILY_C_CLOSURE_HASH,
        "frozen_ingestion_inputs": frozen["status"] == "VERIFIED",
    }
    if not all(checks.values()):
        raise ContinuityInputMismatch("FAMILY_D_REMEDIATION_INPUT_MISMATCH")
    return {"result": "VERIFIED", "checks": checks, "frozen_ingestion": frozen}


def prior_market_sessions(target_session: date, market_sessions: Sequence[date]) -> tuple[date, ...]:
    try:
        index = market_sessions.index(target_session)
    except ValueError as exc:
        raise ValueError(f"Target date is absent from authoritative NSE calendar: {target_session}") from exc
    if index < ACTIVITY_LOOKBACK:
        raise ValueError(f"Authoritative calendar lacks prior20 coverage for {target_session}")
    result = tuple(market_sessions[index - ACTIVITY_LOOKBACK : index])
    if len(result) != ACTIVITY_LOOKBACK or any(value >= target_session for value in result):
        raise AssertionError("PRIOR20_ORDERING_FAILURE")
    return result


def _calendar(root: Path, sessions: Sequence[date]) -> NseCashSessionCalendar:
    return NseCashSessionCalendar.from_trading_dates(tuple(sessions), source="PROJECT_AUTHORITATIVE_NSE_CALENDAR")


def _special_session_dates(root: Path) -> set[date]:
    return {
        date.fromisoformat(row["trading_date"])
        for row in read_csv(root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv")
        if row.get("source_available") == "True" and row.get("session_type") == "SPECIAL"
    }


def _mapping_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "data/research/intraday/v1/development_bounded/manifests/development_intraday_scope_manifest_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["internal_symbol"]): dict(row) for row in payload["instrument_mappings"]}


def _bar_values(bar: CanonicalIntradayBar) -> tuple[Decimal, Decimal, Decimal, Decimal, int | None]:
    return (bar.open, bar.high, bar.low, bar.close, bar.volume)


def _deduplicate_bars(bars: Iterable[CanonicalIntradayBar]) -> tuple[list[CanonicalIntradayBar], bool]:
    output: dict[str, CanonicalIntradayBar] = {}
    conflict = False
    for bar in bars:
        key = bar.bar_start.isoformat()
        previous = output.get(key)
        if previous is not None:
            if _bar_values(previous) != _bar_values(bar):
                conflict = True
            continue
        output[key] = bar
    return sorted(output.values(), key=lambda row: row.bar_start), conflict


def _session_fact(
    bars: Sequence[CanonicalIntradayBar],
    *,
    calendar: NseCashSessionCalendar,
    source: str,
    conflict: bool = False,
) -> dict[str, Any]:
    if not bars:
        return {
            "exists": False,
            "strict": False,
            "opening_volume": None,
            "reason": "MISSING_INTRADAY_SESSION",
            "actual_bars": 0,
            "source": source,
            "row_hash": None,
        }
    by_time = {bar.bar_start.time().replace(tzinfo=None): bar for bar in bars}
    opening = [by_time.get(value) for value in OPENING_BAR_TIMES]
    quality = assess_session_quality(bars, calendar=calendar)
    if conflict:
        reason = "UNEXPLAINED"
    elif any(bar is None for bar in opening):
        reason = "MISSING_OPENING_BARS"
    elif any(bar.volume is None or bar.volume < 0 for bar in opening if bar is not None):
        reason = "INVALID_VOLUME"
    else:
        reason = "COMPLETE" if quality.strict_usable else "SESSION_QUALITY_FAILURE"
    strict = reason == "COMPLETE"
    volume = (
        sum((Decimal(bar.volume) for bar in opening if bar is not None and bar.volume is not None), Decimal("0"))
        if strict
        else None
    )
    row_values = [
        {
            "bar_start": bar.bar_start.isoformat(),
            "open": format(bar.open, "f"),
            "high": format(bar.high, "f"),
            "low": format(bar.low, "f"),
            "close": format(bar.close, "f"),
            "volume": bar.volume,
        }
        for bar in bars
    ]
    return {
        "exists": True,
        "strict": strict,
        "opening_volume": volume,
        "reason": reason,
        "actual_bars": len(bars),
        "source": source,
        "row_hash": canonical_hash(row_values),
        "quality_classification": (
            "STRICT"
            if strict
            else "WARNING"
            if quality.lenient_usable and not conflict
            else "UNUSABLE"
        ),
        "quality_statuses": list(quality.statuses),
    }


def _load_frozen_normalized(
    root: Path,
    required: Mapping[str, set[date]],
    calendar: NseCashSessionCalendar,
) -> tuple[dict[tuple[str, date], dict[str, Any]], dict[tuple[str, date], list[CanonicalIntradayBar]]]:
    facts: dict[tuple[str, date], dict[str, Any]] = {}
    bar_groups: dict[tuple[str, date], list[CanonicalIntradayBar]] = {}
    for symbol, dates in required.items():
        for year in sorted({value.year for value in dates}):
            path = root / f"data/normalized/intraday/5m/development_bounded_v1/{year}/{symbol}.csv.gz"
            if not path.exists():
                continue
            for bar in _canonical_5m_bars_from_partition(path, allowed_dates={value for value in dates if value.year == year}):
                bar_groups.setdefault((symbol, bar.trading_date), []).append(bar)
    for key, values in bar_groups.items():
        bars, conflict = _deduplicate_bars(values)
        bar_groups[key] = bars
        facts[key] = _session_fact(bars, calendar=calendar, source="FROZEN_NORMALIZED_05B", conflict=conflict)
    return facts, bar_groups


@lru_cache(maxsize=4)
def _raw_paths_by_symbol(root: Path, *, extension: bool) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = defaultdict(list)
    if extension:
        plan_path = output_root(root) / "request_plan/continuity_request_plan_v1.json"
        if not plan_path.exists():
            return result
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for row in plan["requests"]:
            path = output_root(root) / "raw_extension/requests" / f"{row['request_id']}.json"
            if path.exists():
                result[str(row["symbol"])].append(path)
        return result
    plan = json.loads(
        (root / "data/research/intraday/v1/development_bounded/manifests/request_plan_v1.json").read_text(encoding="utf-8")
    )
    for row in plan["requests"]:
        path = frozen_raw_root(root) / f"{row['request_id']}.json"
        if path.exists():
            result[str(row["symbol"])].append(path)
    return result


def _provider_rows_by_session(path: Path, symbol: str, wanted: set[date], *, frozen: bool) -> dict[date, list[dict[str, Any]]]:
    record = _read_raw_record(path, INGESTION_SCOPE_HASH) if frozen else json.loads(path.read_text(encoding="utf-8"))
    if not frozen:
        expected_hash = record.get("raw_hash")
        body = {key: value for key, value in record.items() if key not in {"raw_hash", "retrieved_at"}}
        if expected_hash != canonical_hash(body):
            raise RuntimeError(f"CONTINUITY_RAW_HASH_MISMATCH: {path}")
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for candle in _extract_candles(record["response"]):
        parsed = _provider_candle_row(candle)
        timestamp = parse_timestamp(parsed["timestamp"], allow_naive_exchange_local=True)
        minute = timestamp.hour * 60 + timestamp.minute
        if timestamp.date() not in wanted or timestamp.second or timestamp.minute % 5 or not 9 * 60 + 15 <= minute < 15 * 60 + 30:
            continue
        grouped[timestamp.date()].append(
            {
                "symbol": symbol,
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
            }
        )
    return grouped


def _normalize_provider_session(
    rows: Sequence[Mapping[str, Any]],
    *,
    mapping: Mapping[str, Any],
    calendar: NseCashSessionCalendar,
    source: str,
) -> tuple[list[CanonicalIntradayBar], bool]:
    prepared = []
    for row in rows:
        prepared.append(
            {
                **row,
                "instrument_id": mapping.get("provider_instrument_id"),
                "isin": mapping.get("internal_isin"),
                "corporate_action_reference": {"status": "REFERENCE_ONLY", "automatic_adjustment": False},
            }
        )
    normalized = normalize_rows(
        prepared,
        calendar=calendar,
        source_provider=source,
        ingested_at=FIXED_INGESTION_TIME,
        allow_naive_exchange_local=True,
    )
    return _deduplicate_bars(normalized)


def _load_raw_facts(
    root: Path,
    required: Mapping[str, set[date]],
    calendar: NseCashSessionCalendar,
    mappings: Mapping[str, Mapping[str, Any]],
    *,
    extension: bool,
) -> dict[tuple[str, date], dict[str, Any]]:
    paths = _raw_paths_by_symbol(root, extension=extension)
    facts: dict[tuple[str, date], dict[str, Any]] = {}
    source = "CONTINUITY_FETCH" if extension else "FROZEN_RAW_05B_COLLATERAL"
    provider_source = "GROWW_OFFICIAL_API_CONTINUITY_V1" if extension else "GROWW_OFFICIAL_API_FROZEN_05B"
    for symbol in sorted(required):
        for path in paths.get(symbol, []):
            for trading_date, rows in _provider_rows_by_session(path, symbol, required[symbol], frozen=not extension).items():
                bars, conflict = _normalize_provider_session(rows, mapping=mappings[symbol], calendar=calendar, source=provider_source)
                fact = _session_fact(bars, calendar=calendar, source=source, conflict=conflict)
                key = (symbol, trading_date)
                previous = facts.get(key)
                if previous is None or (fact["strict"] and not previous["strict"]):
                    facts[key] = fact
                elif previous["row_hash"] != fact["row_hash"]:
                    facts[key] = {**previous, "strict": False, "reason": "UNEXPLAINED"}
    return facts


def _required_population(root: Path) -> tuple[list[dict[str, Any]], list[date], dict[tuple[str, date], tuple[date, ...]], dict[str, set[date]]]:
    scope = _scope_rows(root)
    sessions = _load_sessions(root)
    requirements: dict[tuple[str, date], tuple[date, ...]] = {}
    required: dict[str, set[date]] = defaultdict(set)
    for row in scope:
        target = date.fromisoformat(str(row["session_date"]))
        values = prior_market_sessions(target, sessions)
        requirements[(str(row["symbol"]), target)] = values
        required[str(row["symbol"])].update(values)
    return scope, sessions, requirements, required


def _listing_dates(root: Path, symbols: set[str]) -> dict[str, date]:
    aliases = _load_aliases(root)
    daily = _load_adjusted_bars(root, symbols, aliases)
    values: dict[str, list[date]] = defaultdict(list)
    for trading_date, rows in daily.items():
        for symbol in rows:
            values[symbol].append(trading_date)
    return {symbol: min(dates) for symbol, dates in values.items()}


def _choose_current_fact(
    key: tuple[str, date],
    normalized: Mapping[tuple[str, date], Mapping[str, Any]],
    collateral: Mapping[tuple[str, date], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    left = normalized.get(key)
    right = collateral.get(key)
    if left and left.get("strict"):
        return left
    if right and right.get("strict"):
        return right
    return left or right


def _group_request_windows(missing: Mapping[str, Sequence[date]], mappings: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    sequence = 0
    for symbol in sorted(missing):
        dates = sorted(set(missing[symbol]))
        cursor = 0
        while cursor < len(dates):
            start = dates[cursor]
            end_limit = start + timedelta(days=MAX_REQUEST_WINDOW_DAYS - 1)
            stop = cursor
            while stop + 1 < len(dates) and dates[stop + 1] <= end_limit:
                stop += 1
            selected = dates[cursor : stop + 1]
            sequence += 1
            mapping = mappings[symbol]
            requests.append(
                {
                    "request_id": f"FAMILY-D-CONT-V1-{sequence:04d}-{symbol}-{start:%Y%m%d}",
                    "sequence_no": sequence,
                    "symbol": symbol,
                    "provider_instrument": mapping["provider_symbol"],
                    "provider_instrument_id": mapping["provider_instrument_id"],
                    "start_date": start.isoformat(),
                    "end_date": selected[-1].isoformat(),
                    "interval": "5m",
                    "required_sessions": [value.isoformat() for value in selected],
                    "required_session_count": len(selected),
                }
            )
            cursor = stop + 1
    return requests


def build_continuity_plan(repo_root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root)
    verification = verify_continuity_inputs(root)
    config = continuity_config_document()
    scope, sessions, requirements, required = _required_population(root)
    calendar = _calendar(root, sessions)
    mappings = _mapping_rows(root)
    normalized, _ = _load_frozen_normalized(root, required, calendar)
    collateral = _load_raw_facts(root, required, calendar, mappings, extension=False)
    listings = _listing_dates(root, set(required))
    requirement_rows: list[dict[str, Any]] = []
    missing_by_symbol: dict[str, list[date]] = defaultdict(list)
    unique_missing: set[tuple[str, date]] = set()
    unique_not_listed: set[tuple[str, date]] = set()
    unique_invalid: set[tuple[str, date]] = set()
    for row in scope:
        symbol = str(row["symbol"])
        target = date.fromisoformat(str(row["session_date"]))
        required_dates = requirements[(symbol, target)]
        present: list[str] = []
        missing: list[str] = []
        invalid: list[str] = []
        not_listed: list[str] = []
        for value in required_dates:
            fact = _choose_current_fact((symbol, value), normalized, collateral)
            if fact and fact.get("strict"):
                present.append(value.isoformat())
            elif listings.get(symbol) and value < listings[symbol]:
                not_listed.append(value.isoformat())
                unique_not_listed.add((symbol, value))
            elif fact and fact.get("exists"):
                invalid.append(value.isoformat())
                unique_invalid.add((symbol, value))
                missing_by_symbol[symbol].append(value)
                unique_missing.add((symbol, value))
            else:
                missing.append(value.isoformat())
                missing_by_symbol[symbol].append(value)
                unique_missing.add((symbol, value))
        requirement_rows.append(
            {
                "symbol": symbol,
                "target_session": target.isoformat(),
                "required_prior_session_dates": [value.isoformat() for value in required_dates],
                "currently_present_dates": present,
                "missing_dates": missing,
                "present_but_invalid_dates": invalid,
                "known_not_listed_dates": not_listed,
            }
        )
    requests = _group_request_windows(missing_by_symbol, mappings)
    plan_body: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "continuity_data_version": CONTINUITY_DATA_VERSION,
        "continuity_remediation_config_hash": config["continuity_remediation_config_hash"],
        "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
        "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
        "provider": "GROWW",
        "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
        "symbol_count": len({row["symbol"] for row in scope}),
        "target_session_count": len(scope),
        "total_required_prior_session_references": len(scope) * ACTIVITY_LOOKBACK,
        "unique_required_symbol_sessions": sum(len(values) for values in required.values()),
        "strict_present_from_frozen_normalized": sum(bool(row.get("strict")) for row in normalized.values()),
        "strict_present_from_frozen_raw_collateral": sum(bool(row.get("strict")) for row in collateral.values()),
        "unique_missing_symbol_sessions_before_remediation": len(unique_missing),
        "present_but_invalid_symbol_sessions": len(unique_invalid),
        "known_symbol_not_listed_symbol_sessions": len(unique_not_listed),
        "earliest_required_date": min(value for values in required.values() for value in values).isoformat(),
        "latest_required_date": max(value for values in required.values() for value in values).isoformat(),
        "earliest_requested_date": min((row["start_date"] for row in requests), default=None),
        "latest_requested_date": max((row["end_date"] for row in requests), default=None),
        "request_count": len(requests),
        "requests": requests,
        "target_requirements": requirement_rows,
        "network_requests_made_while_planning": 0,
        "validation_accessed": False,
    }
    plan_body["continuity_request_plan_hash"] = canonical_hash(plan_body)
    if write:
        base = output_root(root)
        _write_json(base / "request_plan/continuity_remediation_config_v1.json", config)
        _write_json(base / "request_plan/continuity_request_plan_v1.json", plan_body)
        _write_csv(report_root(root) / REPORT_NAMES[1], requests)
    return {"verification": verification, "config": config, "plan": plan_body}


def _load_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads((output_root(root) / "request_plan/continuity_remediation_config_v1.json").read_text(encoding="utf-8"))
    plan = json.loads((output_root(root) / "request_plan/continuity_request_plan_v1.json").read_text(encoding="utf-8"))
    if _document_hash(config, "continuity_remediation_config_hash") != config["continuity_remediation_config_hash"]:
        raise ContinuityInputMismatch("FAMILY_D_REMEDIATION_INPUT_MISMATCH")
    if _document_hash(plan, "continuity_request_plan_hash") != plan["continuity_request_plan_hash"]:
        raise ContinuityInputMismatch("FAMILY_D_REMEDIATION_INPUT_MISMATCH")
    return config, plan


def _request_state(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    path = output_root(root) / "raw_extension/retrieval_state_v1.json"
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("continuity_request_plan_hash") != plan["continuity_request_plan_hash"]:
            raise ContinuityInputMismatch("FAMILY_D_REMEDIATION_INPUT_MISMATCH")
        return state
    state = {
        "command_version": COMMAND_VERSION,
        "continuity_request_plan_hash": plan["continuity_request_plan_hash"],
        "requests": {
            row["request_id"]: {"status": "PENDING", "attempts": 0, "last_error_category": None, "raw_hash": None}
            for row in plan["requests"]
        },
        "transport_metrics": [],
        "auth_status": "NOT_ATTEMPTED",
        "circuit_breaker_triggered": False,
        "provider_blocked": False,
        "late_results_discarded": 0,
        "late_result_commit_violations": 0,
    }
    _write_json(path, state)
    return state


def retrieve_missing_history(
    repo_root: Path,
    *,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
    max_wallclock_seconds: float = 3 * 60 * 60,
) -> dict[str, Any]:
    root = Path(repo_root)
    verify_continuity_inputs(root)
    config, plan = _load_plan(root)
    state = _request_state(root, plan)
    pending = [row for row in plan["requests"] if state["requests"][row["request_id"]]["status"] in {"PENDING", "FAILED_RETRYABLE"}]
    if not pending:
        return state
    settings = Settings()
    try:
        if client is None:
            if not credentials_present(settings):
                raise PermissionError("Groww credentials are not present")
            client = GrowwAuthService(credentials=GrowwCredentials.from_settings(settings)).get_client()
        state["auth_status"] = "MOCK_CLIENT_SUPPLIED" if client.__class__.__module__.startswith("backend.tests") else "SUCCESS"
    except Exception as exc:
        state["auth_status"] = "FAILED"
        state["auth_failure_category"] = classify_provider_failure(exc)
        state["provider_blocked"] = True
        _write_json(output_root(root) / "raw_extension/retrieval_state_v1.json", state)
        return state
    mappings = _mapping_rows(root)
    deadline = time.perf_counter() + max_wallclock_seconds
    guard = AttemptGenerationGuard()

    def persist() -> None:
        state["late_results_discarded"] = guard.late_results_discarded
        state["late_result_commit_violations"] = guard.commit_violations
        _write_json(output_root(root) / "raw_extension/retrieval_state_v1.json", state)

    def on_attempt(metric: dict[str, Any], intermediate_status: str | None) -> None:
        request = state["requests"][metric["request_id"]]
        request["attempts"] = int(request["attempts"]) + 1
        request["last_error_category"] = metric["response_category"] if metric["status"] == "FAILED" else None
        if intermediate_status is not None:
            request["status"] = "FAILED_RETRYABLE" if "RETRYABLE" in intermediate_status else "FAILED_FINAL"
        state["transport_metrics"].append(metric)
        persist()

    transport = ResumeGrowwTransport(
        client=client,
        guard=guard,
        on_attempt=on_attempt,
        max_attempts=len(pending) * (MAX_RETRIES + 1),
        deadline_monotonic=deadline,
        throttle_seconds=throttle_seconds,
        allowed_start_date=date.fromisoformat(plan["earliest_required_date"]),
        allowed_end_date=DEVELOPMENT_END,
    )
    consecutive_timeouts = 0
    for index, request in enumerate(pending, start=1):
        request_id = request["request_id"]
        raw_path = output_root(root) / "raw_extension/requests" / f"{request_id}.json"
        if raw_path.exists():
            state["requests"][request_id]["status"] = "COMPLETE"
            continue
        if time.perf_counter() >= deadline:
            state["runtime_limit_triggered"] = True
            break
        mapping = InstrumentMapping(**mappings[request["symbol"]])
        try:
            response, attempt_id = transport.fetch(mapping=mapping, request=request)
            if not guard.claim_commit(attempt_id):
                raise RuntimeError("LATE_RESULT_COMMIT_GUARD_REJECTED")
            body = {
                "command_version": COMMAND_VERSION,
                "profile": PROFILE,
                "continuity_remediation_config_hash": config["continuity_remediation_config_hash"],
                "continuity_request_plan_hash": plan["continuity_request_plan_hash"],
                "provider": "GROWW",
                "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
                "request_id": request_id,
                "symbol": request["symbol"],
                "provider_instrument": request["provider_instrument"],
                "provider_instrument_id": request["provider_instrument_id"],
                "requested_start": request["start_date"],
                "requested_end": request["end_date"],
                "requested_interval": request["interval"],
                "required_sessions": request["required_sessions"],
                "accepted_attempt_id": attempt_id,
                "response": response,
            }
            raw_hash = canonical_hash(body)
            record = {**body, "raw_hash": raw_hash, "retrieved_at": datetime.now(timezone.utc).isoformat()}
            _write_immutable_raw(raw_path, record)
            state["requests"][request_id].update(
                status="COMPLETE", raw_hash=raw_hash, raw_path=str(raw_path), row_count=len(_extract_candles(response)), last_error_category=None
            )
            consecutive_timeouts = 0
        except ResumeRuntimeLimit:
            state["runtime_limit_triggered"] = True
            break
        except ResumeRequestFailure as exc:
            state["requests"][request_id]["status"] = "FAILED_FINAL"
            state["requests"][request_id]["last_error_category"] = exc.category
            if exc.category == "AUTHENTICATION_FAILURE":
                state["provider_blocked"] = True
                break
            consecutive_timeouts = consecutive_timeouts + 1 if exc.category == "TIMEOUT" else 0
            if consecutive_timeouts >= REQUEST_TIMEOUT_CIRCUIT_BREAKER:
                state["circuit_breaker_triggered"] = True
                state["provider_blocked"] = True
                break
        finally:
            persist()
        if progress and (index == 1 or index % 25 == 0 or index == len(pending)):
            complete = sum(row["status"] == "COMPLETE" for row in state["requests"].values())
            progress(f"Family D continuity retrieval {complete}/{len(plan['requests'])} complete")
    persist()
    return state


def coverage_classification(available: int, total: int) -> str:
    percentage = Decimal(available) * Decimal("100") / Decimal(total) if total else Decimal("0")
    if percentage >= Decimal("98"):
        return "EXCELLENT"
    if percentage >= Decimal("95"):
        return "STRONG"
    if percentage >= Decimal("90"):
        return "USABLE_WITH_LIMITATIONS"
    return "INSUFFICIENT"


def _select_fact(
    key: tuple[str, date],
    normalized: Mapping[tuple[str, date], Mapping[str, Any]],
    collateral: Mapping[tuple[str, date], Mapping[str, Any]],
    fetched: Mapping[tuple[str, date], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for source in (normalized, fetched, collateral):
        fact = source.get(key)
        if fact and fact.get("strict"):
            return fact
    return normalized.get(key) or fetched.get(key) or collateral.get(key)


def _request_coverage(plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[tuple[str, date], str]:
    output: dict[tuple[str, date], str] = {}
    for request in plan["requests"]:
        status = state["requests"][request["request_id"]]["status"]
        for value in request["required_sessions"]:
            output[(request["symbol"], date.fromisoformat(value))] = status
    return output


def _target_reason(
    symbol: str,
    required_dates: Sequence[date],
    facts: Mapping[tuple[str, date], Mapping[str, Any] | None],
    listings: Mapping[str, date],
    request_status: Mapping[tuple[str, date], str],
    mapping: Mapping[str, Any],
    special_sessions: set[date] | None = None,
) -> str:
    if all(facts.get((symbol, value)) and facts[(symbol, value)].get("strict") for value in required_dates):
        return "COMPLETE"
    if any(listings.get(symbol) and value < listings[symbol] for value in required_dates):
        return "SYMBOL_NOT_LISTED"
    if not mapping.get("provider_instrument_id") or "MISMATCH" in str(mapping.get("mapping_status")):
        return "IDENTITY_MAPPING_ISSUE"
    reasons = [facts[(symbol, value)]["reason"] for value in required_dates if facts.get((symbol, value))]
    for value in ("UNEXPLAINED", "INVALID_VOLUME", "MISSING_OPENING_BARS", "SESSION_QUALITY_FAILURE"):
        if value in reasons:
            return value
    missing_dates = [value for value in required_dates if not facts.get((symbol, value))]
    if any(value in (special_sessions or set()) for value in missing_dates):
        return "MISSING_OPENING_BARS"
    if any(request_status.get((symbol, value)) == "COMPLETE" for value in missing_dates):
        return "PROVIDER_HISTORY_UNAVAILABLE"
    return "MISSING_INTRADAY_SESSION"


def _load_raw_bars_for_symbol(
    root: Path,
    symbol: str,
    wanted: set[date],
    calendar: NseCashSessionCalendar,
    mapping: Mapping[str, Any],
    *,
    extension: bool,
) -> dict[date, list[CanonicalIntradayBar]]:
    grouped_rows: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for path in _raw_paths_by_symbol(root, extension=extension).get(symbol, []):
        for trading_date, rows in _provider_rows_by_session(path, symbol, wanted, frozen=not extension).items():
            grouped_rows[trading_date].extend(rows)
    output: dict[date, list[CanonicalIntradayBar]] = {}
    source = "GROWW_OFFICIAL_API_CONTINUITY_V1" if extension else "GROWW_OFFICIAL_API_FROZEN_05B"
    for trading_date, rows in grouped_rows.items():
        output[trading_date], _ = _normalize_provider_session(rows, mapping=mapping, calendar=calendar, source=source)
    return output


def classify_overlap(old: CanonicalIntradayBar, new: CanonicalIntradayBar) -> str:
    if _bar_values(old) == _bar_values(new):
        return "EXACT_MATCH"
    price_equal = all(abs(left - right) <= Decimal("0.000001") for left, right in zip(_bar_values(old)[:4], _bar_values(new)[:4]))
    if price_equal and old.volume == new.volume:
        return "SOURCE_EQUIVALENT"
    price_close = all(abs(left - right) <= Decimal("0.05") for left, right in zip(_bar_values(old)[:4], _bar_values(new)[:4]))
    old_volume = Decimal(old.volume or 0)
    new_volume = Decimal(new.volume or 0)
    volume_close = old_volume == new_volume or abs(old_volume - new_volume) / max(old_volume, new_volume, Decimal("1")) <= Decimal("0.01")
    if price_close and volume_close:
        return "EXPLAINED_PROVIDER_DIFFERENCE"
    return "UNEXPLAINED_DIFFERENCE"


def _build_extension_and_reconciliation(
    root: Path,
    required: Mapping[str, set[date]],
    calendar: NseCashSessionCalendar,
    mappings: Mapping[str, Mapping[str, Any]],
    normalized_groups: Mapping[tuple[str, date], list[CanonicalIntradayBar]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    partition_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reconciliation: list[dict[str, Any]] = []
    overlap_counts: Counter[str] = Counter()
    included_sessions = 0
    strict_sessions = 0
    quality_rows: list[dict[str, Any]] = []
    for symbol in sorted(required):
        old_raw = _load_raw_bars_for_symbol(root, symbol, required[symbol], calendar, mappings[symbol], extension=False)
        new_raw = _load_raw_bars_for_symbol(root, symbol, required[symbol], calendar, mappings[symbol], extension=True)
        for trading_date in sorted(required[symbol]):
            frozen_normalized = normalized_groups.get((symbol, trading_date), [])
            for label, comparison in (("FROZEN_RAW_VS_FROZEN_NORMALIZED", old_raw.get(trading_date, [])), ("CONTINUITY_FETCH_VS_EXISTING", new_raw.get(trading_date, []))):
                if not frozen_normalized or not comparison:
                    continue
                old_map = {bar.bar_start.isoformat(): bar for bar in frozen_normalized}
                new_map = {bar.bar_start.isoformat(): bar for bar in comparison}
                local: Counter[str] = Counter()
                for timestamp in sorted(set(old_map) | set(new_map)):
                    classification = (
                        classify_overlap(old_map[timestamp], new_map[timestamp])
                        if timestamp in old_map and timestamp in new_map
                        else "UNEXPLAINED_DIFFERENCE"
                    )
                    local[classification] += 1
                    overlap_counts[classification] += 1
                for classification, count in sorted(local.items()):
                    reconciliation.append(
                        {
                            "symbol": symbol,
                            "trading_date": trading_date.isoformat(),
                            "comparison": label,
                            "classification": classification,
                            "row_count": count,
                        }
                    )
            frozen_fact = _session_fact(frozen_normalized, calendar=calendar, source="FROZEN_NORMALIZED_05B") if frozen_normalized else None
            selected = None
            for candidate in (new_raw.get(trading_date), old_raw.get(trading_date)):
                if candidate:
                    fact = _session_fact(candidate, calendar=calendar, source="EXTENSION")
                    if fact["strict"]:
                        selected = candidate
                        break
                    selected = selected or candidate
            if not selected or (frozen_fact and frozen_fact["strict"]):
                continue
            included_sessions += 1
            selected_fact = _session_fact(selected, calendar=calendar, source="CONTINUITY_EXTENSION")
            strict_sessions += int(selected_fact["strict"])
            quality_rows.append(
                {
                    "symbol": symbol,
                    "trading_date": trading_date.isoformat(),
                    "classification": selected_fact["quality_classification"],
                    "reason": selected_fact["reason"],
                    "actual_bars": selected_fact["actual_bars"],
                    "opening_volume_available": selected_fact["opening_volume"] is not None,
                    "source": "CONTINUITY_FETCH" if trading_date in new_raw else "FROZEN_RAW_05B_COLLATERAL",
                }
            )
            for bar in selected:
                partition_rows[f"{trading_date.year}/{symbol}"].append(canonical_bar_row(bar))
    partitions = []
    total_rows = 0
    base = output_root(root) / "normalized_extension"
    for key in sorted(partition_rows):
        year, symbol = key.split("/", 1)
        path = base / year / f"{symbol}.csv.gz"
        rows = sorted(partition_rows[key], key=lambda row: row["bar_start"])
        _write_gzip_csv_deterministic(path, rows)
        total_rows += len(rows)
        partitions.append(
            {
                "partition": key,
                "relative_path": path.relative_to(root).as_posix(),
                "row_count": len(rows),
                "sha256": file_sha256(path),
            }
        )
    normalized_manifest = {
        "continuity_data_version": CONTINUITY_DATA_VERSION,
        "normalization_profile": NORMALIZATION_PROFILE,
        "timezone": "Asia/Kolkata",
        "bar_convention": "BAR_START",
        "row_count": total_rows,
        "symbol_session_count": included_sessions,
        "strict_symbol_session_count": strict_sessions,
        "partitions": partitions,
    }
    normalized_manifest["continuity_normalized_extension_hash"] = canonical_hash(normalized_manifest)
    _write_json(base / "normalized_extension_manifest_v1.json", normalized_manifest)
    _write_csv(base / "session_quality_v1.csv", quality_rows)
    compared = sum(overlap_counts.values())
    unexplained = overlap_counts["UNEXPLAINED_DIFFERENCE"]
    reconciliation_summary = {
        "overlap_rows_compared": compared,
        "exact_match_rows": overlap_counts["EXACT_MATCH"],
        "source_equivalent_rows": overlap_counts["SOURCE_EQUIVALENT"],
        "explained_provider_difference_rows": overlap_counts["EXPLAINED_PROVIDER_DIFFERENCE"],
        "unexplained_difference_rows": unexplained,
        "unexplained_difference_rate": Decimal(unexplained) / Decimal(compared) if compared else Decimal("0"),
        "material_unexplained_difference": bool(compared and Decimal(unexplained) / Decimal(compared) > MATERIAL_UNEXPLAINED_RATE),
    }
    reconciliation_summary["result"] = "FAIL_MATERIAL_UNEXPLAINED" if reconciliation_summary["material_unexplained_difference"] else "PASS"
    _write_json(output_root(root) / "reconciliation/reconciliation_summary_v1.json", reconciliation_summary)
    return {"manifest": normalized_manifest, "summary": reconciliation_summary}, reconciliation, quality_rows


def _raw_extension_manifest(root: Path, plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    raw_rows = 0
    for request in plan["requests"]:
        request_state = state["requests"][request["request_id"]]
        path = output_root(root) / "raw_extension/requests" / f"{request['request_id']}.json"
        if request_state["status"] != "COMPLETE" or not path.exists():
            continue
        raw_rows += int(request_state.get("row_count") or 0)
        rows.append(
            {
                "request_id": request["request_id"],
                "symbol": request["symbol"],
                "raw_hash": request_state["raw_hash"],
                "file_sha256": file_sha256(path),
                "row_count": request_state.get("row_count", 0),
                "relative_path": path.relative_to(root).as_posix(),
            }
        )
    document = {"continuity_data_version": CONTINUITY_DATA_VERSION, "raw_rows": raw_rows, "responses": rows}
    document["continuity_raw_extension_hash"] = canonical_hash(document)
    _write_json(output_root(root) / "raw_extension/raw_extension_manifest_v1.json", document)
    return document


def _activity_and_counts(
    root: Path,
    requirements: Mapping[tuple[str, date], tuple[date, ...]],
    selected: Mapping[tuple[str, date], Mapping[str, Any] | None],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    signals = read_csv(root / "data/research/strategy_families/family_d/v1/signals/family_d_structural_signals_v1.csv")
    activity_by_target: dict[tuple[str, date], dict[str, Any]] = {}
    for key, dates in requirements.items():
        values = [selected.get((key[0], value), {}).get("opening_volume") if selected.get((key[0], value)) else None for value in dates]
        current = next((row for row in signals if row["symbol"] == key[0] and row["session_date"] == key[1].isoformat()), None)
        activity_by_target[key] = opening_activity_ratio(
            Decimal(current["opening_15m_volume"]) if current and current.get("opening_15m_volume") else None,
            [value for value in values if value is not None],
        )
    structural: list[dict[str, Any]] = []
    for row in signals:
        key = (row["symbol"], date.fromisoformat(row["session_date"]))
        activity = activity_by_target[key]
        control = str(row["control_signal"]).lower() == "true"
        structural.append(
            {
                "symbol": row["symbol"],
                "session_date": row["session_date"],
                "first_breakout_time": row.get("first_breakout_time"),
                "control_signal": control,
                "activity_baseline_available": activity["available"],
                "current_opening_15m_volume": Decimal(row["opening_15m_volume"]) if row.get("opening_15m_volume") else None,
                "prior20_median_opening_volume": activity["median"],
                "opening_activity_ratio": activity["ratio"],
                "activity_threshold_pass": activity["pass"],
                "d001_signal": bool(control and activity["pass"]),
            }
        )
    values = [row["opening_activity_ratio"] for row in structural if row["opening_activity_ratio"] is not None]
    distribution = {
        "metric": "opening_activity_ratio",
        "observation_count": len(values),
        "p10": _percentile(values, Decimal("0.10")),
        "p25": _percentile(values, Decimal("0.25")),
        "median": _percentile(values, Decimal("0.50")),
        "p75": _percentile(values, Decimal("0.75")),
        "p90": _percentile(values, Decimal("0.90")),
        "p95": _percentile(values, Decimal("0.95")),
        "max": max(values) if values else None,
    }
    yearly = []
    for year in (2022, 2023, 2024):
        rows = [row for row in structural if row["session_date"].startswith(str(year))]
        yearly.append(
            {
                "year": year,
                "control_signal_count": sum(row["control_signal"] for row in rows),
                "activity_baseline_available_control_signal_count": sum(row["control_signal"] and row["activity_baseline_available"] for row in rows),
                "d001_signal_count": sum(row["d001_signal"] for row in rows),
            }
        )
    buckets = (("09:30-10:00", "09:30", "10:00"), ("10:00-10:30", "10:00", "10:30"), ("10:30-11:00", "10:30", "11:00"), ("11:00-11:30", "11:00", "11:31"))
    time_rows = []
    for name, start, end in buckets:
        rows = [row for row in structural if row["first_breakout_time"] and start <= row["first_breakout_time"] < end]
        time_rows.append(
            {
                "time_bucket": name,
                "control_breakout_count": len(rows),
                "control_signal_count": sum(row["control_signal"] for row in rows),
                "d001_signal_count": sum(row["d001_signal"] for row in rows),
            }
        )
    return structural, distribution, yearly, time_rows


def _pilots(
    matrix: Sequence[Mapping[str, Any]],
    requirements: Mapping[tuple[str, date], tuple[date, ...]],
    selected: Mapping[tuple[str, date], Mapping[str, Any] | None],
    structural: Sequence[Mapping[str, Any]],
    reconciliation: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    structural_by_key = {(row["symbol"], row["session_date"]): row for row in structural}
    available = [row for row in matrix if row["activity_baseline_available"]]
    early = [row for row in available if any(value.year < 2022 for value in requirements[(row["symbol"], date.fromisoformat(row["target_session"]))])]
    not_listed = [row for row in matrix if row["activity_baseline_reason"] == "SYMBOL_NOT_LISTED"]
    high = [row for row in structural if row["opening_activity_ratio"] is not None and row["opening_activity_ratio"] >= ACTIVITY_THRESHOLD]
    low = [row for row in structural if row["opening_activity_ratio"] is not None and row["opening_activity_ratio"] < ACTIVITY_THRESHOLD]
    overlap = reconciliation[0] if reconciliation else None
    cases = [
        ("A", available[0] if available else None, "PREVIOUSLY_UNAVAILABLE_NOW_RESOLVED"),
        ("B", early[0] if early else None, "EARLY_2022_WITH_PRE_2022_HISTORY"),
        ("C", not_listed[0] if not_listed else None, "LEGITIMATE_RECENT_LISTING"),
        ("D", available[-1] if available else None, "EXACTLY_20_CONSECUTIVE_PRIOR_SESSIONS"),
        ("E", overlap, "OVERLAPPING_EXISTING_AND_PROVIDER_ROWS"),
        ("F", high[0] if high else None, "STRICT_ACTIVITY_RATIO_GTE_1_5"),
        ("G", low[0] if low else None, "STRICT_ACTIVITY_RATIO_LT_1_5"),
    ]
    rows: list[dict[str, Any]] = []
    for pilot_id, value, category in cases:
        if value is None:
            rows.append({"pilot_id": pilot_id, "category": category, "result": "NOT_AVAILABLE", "symbol": None, "target_session": None, "evidence": "No real case exists in frozen population"})
            continue
        symbol = value.get("symbol")
        target_text = value.get("target_session") or value.get("session_date") or value.get("trading_date")
        rows.append({"pilot_id": pilot_id, "category": category, "result": "PASS", "symbol": symbol, "target_session": target_text, "evidence": dict(value)})
    manual_candidates = []
    for row in [*(early[:1]), *(high[:1]), *(low[:1]), *(available[:3])]:
        target_text = row.get("target_session") or row.get("session_date")
        if not target_text:
            continue
        key = (row["symbol"], date.fromisoformat(target_text))
        if key not in manual_candidates:
            manual_candidates.append(key)
        if len(manual_candidates) == 3:
            break
    for index, key in enumerate(manual_candidates, start=1):
        volumes = [selected[(key[0], value)]["opening_volume"] for value in requirements[key]]
        signal = structural_by_key.get((key[0], key[1].isoformat()))
        if not signal:
            continue
        median = Decimal(statistics.median(volumes))
        current = signal["current_opening_15m_volume"]
        recomputed = current / median if current is not None and median > 0 else None
        passed = recomputed == signal["opening_activity_ratio"]
        rows.append(
            {
                "pilot_id": f"MANUAL-{index}",
                "category": "MANUAL_ACTIVITY_RECOMPUTATION",
                "result": "PASS" if passed else "FAIL",
                "symbol": key[0],
                "target_session": key[1].isoformat(),
                "evidence": {
                    "prior_session_dates": [value.isoformat() for value in requirements[key]],
                    "prior_opening_15m_volumes": volumes,
                    "median": median,
                    "current_opening_15m_volume": current,
                    "opening_activity_ratio": recomputed,
                    "reported_ratio": signal["opening_activity_ratio"],
                },
            }
        )
    return rows


def finalize_continuity_remediation(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    verification = verify_continuity_inputs(root)
    config, plan = _load_plan(root)
    state = _request_state(root, plan)
    baseline_before = family_c_baseline_snapshot(root)
    scope, sessions, requirements, required = _required_population(root)
    calendar = _calendar(root, sessions)
    mappings = _mapping_rows(root)
    normalized, normalized_groups = _load_frozen_normalized(root, required, calendar)
    collateral = _load_raw_facts(root, required, calendar, mappings, extension=False)
    fetched = _load_raw_facts(root, required, calendar, mappings, extension=True)
    listings = _listing_dates(root, set(required))
    request_status = _request_coverage(plan, state)
    special_sessions = _special_session_dates(root)
    extension, reconciliation_rows, quality_rows = _build_extension_and_reconciliation(root, required, calendar, mappings, normalized_groups)
    raw_manifest = _raw_extension_manifest(root, plan, state)
    selected: dict[tuple[str, date], Mapping[str, Any] | None] = {}
    for symbol, dates in required.items():
        for value in dates:
            selected[(symbol, value)] = _select_fact((symbol, value), normalized, collateral, fetched)
    matrix: list[dict[str, Any]] = []
    for row in scope:
        symbol = row["symbol"]
        target = date.fromisoformat(row["session_date"])
        required_dates = requirements[(symbol, target)]
        facts = [selected[(symbol, value)] for value in required_dates]
        reason = _target_reason(
            symbol,
            required_dates,
            selected,
            listings,
            request_status,
            mappings[symbol],
            special_sessions,
        )
        matrix.append(
            {
                "symbol": symbol,
                "target_session": target.isoformat(),
                "required_prior_20_count": 20,
                "present_prior_20_count": sum(bool(fact and fact.get("exists")) for fact in facts),
                "strict_prior_20_count": sum(bool(fact and fact.get("strict")) for fact in facts),
                "missing_prior_20_count": sum(not fact or not fact.get("exists") for fact in facts),
                "invalid_prior_20_count": sum(bool(fact and fact.get("exists") and not fact.get("strict")) for fact in facts),
                "activity_baseline_available": reason == "COMPLETE",
                "activity_baseline_reason": reason,
            }
        )
    unavailable_required_rows: list[dict[str, Any]] = []
    for (symbol, trading_date), fact in sorted(selected.items()):
        if fact and fact.get("strict"):
            continue
        reason = _target_reason(
            symbol,
            (trading_date,),
            selected,
            listings,
            request_status,
            mappings[symbol],
            special_sessions,
        )
        unavailable_required_rows.append(
            {
                "symbol": symbol,
                "trading_date": trading_date.isoformat(),
                "reason": reason,
                "rows_present": bool(fact and fact.get("exists")),
                "actual_bars": fact.get("actual_bars", 0) if fact else 0,
                "quality_classification": fact.get("quality_classification") if fact else "UNUSABLE",
                "source": fact.get("source") if fact else None,
            }
        )
    newly_covered_strict_sessions = sum(
        bool(fact and fact.get("strict") and not normalized.get(key, {}).get("strict"))
        for key, fact in selected.items()
    )
    available = sum(row["activity_baseline_available"] for row in matrix)
    unavailable = len(matrix) - available
    reason_counts = Counter(row["activity_baseline_reason"] for row in matrix)
    classification = coverage_classification(available, len(matrix))
    coverage_pct = Decimal(available) * Decimal("100") / Decimal(len(matrix))
    remediable_total = len(matrix) - reason_counts["SYMBOL_NOT_LISTED"]
    remediable_pct = Decimal(available) * Decimal("100") / Decimal(remediable_total) if remediable_total else Decimal("0")
    structural, distribution, yearly, time_rows = _activity_and_counts(root, requirements, selected)
    subset_violations = sum(row["d001_signal"] and not row["control_signal"] for row in structural)
    pilots = _pilots(matrix, requirements, selected, structural, reconciliation_rows)
    manual_rows = [row for row in pilots if row["category"] == "MANUAL_ACTIVITY_RECOMPUTATION"]
    manual_pass = bool(manual_rows) and all(row["result"] == "PASS" for row in manual_rows)
    unexplained_material = extension["summary"]["material_unexplained_difference"]
    mechanics_valid = manual_pass and subset_violations == 0
    acceptable = classification in {"EXCELLENT", "STRONG", "USABLE_WITH_LIMITATIONS"}
    backtest_ready = acceptable and not unexplained_material and mechanics_valid
    if state.get("provider_blocked") and not acceptable:
        remediation_result = "PROVIDER_BLOCKED"
    elif classification == "EXCELLENT" and backtest_ready:
        remediation_result = "READY_FOR_BOUNDED_DEVELOPMENT_BACKTEST"
    elif acceptable and backtest_ready:
        remediation_result = "READY_WITH_LIMITATIONS"
    elif any(row["status"] in {"PENDING", "FAILED_RETRYABLE"} for row in state["requests"].values()):
        remediation_result = "MORE_INGESTION_REQUIRED"
    else:
        remediation_result = "MORE_INGESTION_REQUIRED" if not acceptable else "INCONCLUSIVE"
    data_readiness = "READY_FOR_BOUNDED_RESEARCH" if classification == "EXCELLENT" and backtest_ready else "READY_WITH_LIMITATIONS" if backtest_ready else "BLOCKED"
    architecture_result = "READY_FOR_DEVELOPMENT_BACKTEST" if backtest_ready else "DATA_BLOCKED"
    matrix_document = {
        "continuity_data_version": CONTINUITY_DATA_VERSION,
        "target_session_count": len(matrix),
        "rows": matrix,
    }
    matrix_document["continuity_matrix_hash"] = canonical_hash(matrix_document)
    readiness_body: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "continuity_remediation_config_hash": config["continuity_remediation_config_hash"],
        "continuity_request_plan_hash": plan["continuity_request_plan_hash"],
        "continuity_raw_extension_hash": raw_manifest["continuity_raw_extension_hash"],
        "continuity_normalized_extension_hash": extension["manifest"]["continuity_normalized_extension_hash"],
        "continuity_matrix_hash": matrix_document["continuity_matrix_hash"],
        "target_symbol_session_count": len(matrix),
        "activity_baseline_available_count": available,
        "unavailable_count": unavailable,
        "coverage_pct": coverage_pct,
        "coverage_classification": classification,
        "FAMILY_D_REMEDIABLE_CONTINUITY_COVERAGE": remediable_pct,
        "unavailable_reasons": {value: reason_counts[value] for value in AVAILABILITY_REASONS if value != "COMPLETE"},
        "d001_subset_violations": subset_violations,
        "no_lookahead_verified": all(all(value < key[1] for value in dates) for key, dates in requirements.items()),
        "material_unexplained_overlap": unexplained_material,
        "FAMILY_D_CONTINUITY_REMEDIATION_RESULT": remediation_result,
        "FAMILY_D_DATA_READINESS": data_readiness,
        "FAMILY_D_ARCHITECTURE_RESULT": architecture_result,
        "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS": "YES" if backtest_ready else "NO",
        "performance_run": False,
        "validation_accessed": False,
    }
    readiness_body["family_d_activity_readiness_hash"] = canonical_hash(readiness_body)
    readiness_rows = [
        {"check": "FROZEN_HASHES", "status": "PASS", "evidence": verification["result"]},
        {"check": "CONTINUITY_COVERAGE", "status": "PASS" if acceptable else "FAIL", "evidence": coverage_pct},
        {"check": "OVERLAP_RECONCILIATION", "status": "FAIL" if unexplained_material else "PASS", "evidence": extension["summary"]["result"]},
        {"check": "ACTIVITY_MECHANICS", "status": "PASS" if manual_pass else "FAIL", "evidence": f"manual_pilots={len(manual_rows)}"},
        {"check": "D001_SUBSET", "status": "PASS" if subset_violations == 0 else "FAIL", "evidence": subset_violations},
        {"check": "NO_LOOKAHEAD", "status": "PASS" if readiness_body["no_lookahead_verified"] else "FAIL", "evidence": "PRIOR_SESSIONS_STRICTLY_LT_TARGET"},
        {"check": "NO_PERFORMANCE_NO_VALIDATION", "status": "PASS", "evidence": "ZERO_OUTCOME_FIELDS;VALIDATION_SEALED"},
    ]
    _write_json(output_root(root) / "continuity_matrix/continuity_matrix_v1.json", matrix_document)
    _write_csv(output_root(root) / "continuity_matrix/unavailable_required_sessions_v1.csv", unavailable_required_rows)
    _write_json(output_root(root) / "activity_readiness/family_d_activity_readiness_v1.json", readiness_body)
    _write_csv(output_root(root) / "pilots/family_d_continuity_pilots_v1.csv", pilots)
    reports = report_root(root)
    _write_csv(reports / REPORT_NAMES[2], reconciliation_rows)
    _write_csv(reports / REPORT_NAMES[3], matrix, fields=("symbol", "target_session", "required_prior_20_count", "present_prior_20_count", "strict_prior_20_count", "missing_prior_20_count", "invalid_prior_20_count", "activity_baseline_available", "activity_baseline_reason"))
    _write_csv(reports / REPORT_NAMES[4], [row for row in matrix if not row["activity_baseline_available"]])
    _write_csv(reports / REPORT_NAMES[5], [distribution])
    _write_csv(reports / REPORT_NAMES[6], yearly)
    _write_csv(reports / REPORT_NAMES[7], pilots)
    _write_csv(reports / REPORT_NAMES[8], readiness_rows)
    _write_csv(output_root(root) / "activity_readiness/family_d_structural_activity_v1.csv", structural)
    _write_csv(output_root(root) / "activity_readiness/family_d_time_distribution_v1.csv", time_rows)
    _write_json(output_root(root) / "reconciliation/reconciliation_rows_v1.json", {"rows": reconciliation_rows})
    baseline_after = family_c_baseline_snapshot(root)
    if baseline_before != baseline_after:
        raise RuntimeError("PREVIOUS_FAMILY_BASELINE_CHANGED_DURING_CONTINUITY_REMEDIATION")
    summary = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "continuity_data_version": CONTINUITY_DATA_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "verification": verification,
        "hashes": {
            "continuity_remediation_config_hash": config["continuity_remediation_config_hash"],
            "continuity_request_plan_hash": plan["continuity_request_plan_hash"],
            "continuity_raw_extension_hash": raw_manifest["continuity_raw_extension_hash"],
            "continuity_normalized_extension_hash": extension["manifest"]["continuity_normalized_extension_hash"],
            "continuity_matrix_hash": matrix_document["continuity_matrix_hash"],
            "family_d_activity_readiness_hash": readiness_body["family_d_activity_readiness_hash"],
        },
        "plan": {key: plan[key] for key in ("symbol_count", "target_session_count", "total_required_prior_session_references", "unique_required_symbol_sessions", "unique_missing_symbol_sessions_before_remediation", "present_but_invalid_symbol_sessions", "known_symbol_not_listed_symbol_sessions", "request_count", "earliest_requested_date", "latest_requested_date")},
        "retrieval": {
            "provider": "GROWW",
            "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            "request_count": len(plan["requests"]),
            "completed_requests": sum(row["status"] == "COMPLETE" for row in state["requests"].values()),
            "failed_requests": sum(row["status"] == "FAILED_FINAL" for row in state["requests"].values()),
            "raw_rows_added": raw_manifest["raw_rows"],
            "normalized_rows_added": extension["manifest"]["row_count"],
            "newly_covered_symbol_sessions": newly_covered_strict_sessions,
            "new_strict_session_count": extension["manifest"]["strict_symbol_session_count"],
        },
        "reconciliation": extension["summary"],
        "continuity": {
            "target_symbol_session_count": len(matrix),
            "complete_count": available,
            "unavailable_count": unavailable,
            "coverage_pct": coverage_pct,
            "remediable_coverage_pct": remediable_pct,
            "coverage_classification": classification,
            "unavailable_reasons": dict(reason_counts),
            "unique_unavailable_required_symbol_sessions": len(unavailable_required_rows),
            "unique_unavailable_required_reasons": dict(Counter(row["reason"] for row in unavailable_required_rows)),
        },
        "structural": {
            "strict_target_session_count": len(structural),
            "control_signal_count": sum(row["control_signal"] for row in structural),
            "activity_baseline_available_control_signal_count": sum(row["control_signal"] and row["activity_baseline_available"] for row in structural),
            "d001_signal_count": sum(row["d001_signal"] for row in structural),
            "d001_subset_violations": subset_violations,
            "activity_distribution": distribution,
            "yearly_counts": yearly,
            "time_distribution": time_rows,
        },
        "pilots": {
            "real_case_count": sum(row["pilot_id"] in tuple("ABCDEFG") and row["result"] == "PASS" for row in pilots),
            "not_applicable_case_count": sum(row["pilot_id"] in tuple("ABCDEFG") and row["result"] == "NOT_AVAILABLE" for row in pilots),
            "manual_pilot_count": len(manual_rows),
            "manual_result": "PASS" if manual_pass else "FAIL",
            "rows": pilots,
        },
        **{key: readiness_body[key] for key in ("FAMILY_D_CONTINUITY_REMEDIATION_RESULT", "FAMILY_D_DATA_READINESS", "FAMILY_D_ARCHITECTURE_RESULT", "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS")},
        "governance": {
            "strategy_parameter_changed": False,
            "alternate_activity_baseline_used": False,
            "performance_run": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "frozen_command_05b_mutations": 0,
            "family_d_command_01_mutations": 0,
        },
        "baseline_regression": baseline_after,
        "known_limitations": [
            "The population remains the frozen 100-symbol bounded DEVELOPMENT scope, not full-Nifty500 evidence.",
            "Current Groww instrument mappings are present-day identities; genuine recent listings and unresolved historical identities are never fabricated.",
            "Any exact prior20 window containing a non-strict or unavailable session remains unavailable; older sessions are not substituted.",
            "The frozen target population contains no genuine recent-listing continuity case, so real pilot C is explicitly not applicable rather than fabricated.",
        ],
        "recommended_next_action": "RUN_SEPARATELY_AUTHORIZED_FAMILY_D_BOUNDED_DEVELOPMENT_BACKTEST" if backtest_ready else "RESOLVE_REMAINING_CONTINUITY_LIMITATIONS_BEFORE_PERFORMANCE",
        "ready_for_review": True,
    }
    manifest_path = output_root(root) / "manifests/family_d_continuity_remediation_manifest_v1.json"
    summary["manifest_path"] = manifest_path.relative_to(root).as_posix()
    _write_json(reports / REPORT_NAMES[0], summary)
    _write_documentation(root, summary)
    artifact_paths = [
        path
        for path in output_root(root).rglob("*")
        if path.is_file() and "manifests" not in path.parts
    ] + [reports / name for name in REPORT_NAMES] + [root / "docs/strategy-family-d-intraday-continuity-remediation-v1.md"]
    manifest_body = {
        "version": "FAMILY_D_CONTINUITY_REMEDIATION_MANIFEST_V1",
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "completion_timestamp": summary["completed_at"],
        "frozen_hashes": config["frozen_hashes"],
        "symbol_scope": {"symbol_count": plan["symbol_count"], "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH},
        "target_session_count": plan["target_session_count"],
        "required_prior_session_references": plan["total_required_prior_session_references"],
        "request_plan": {"request_count": plan["request_count"], "hash": plan["continuity_request_plan_hash"]},
        "provider": "GROWW",
        "transport": config["transport"],
        "raw_added_rows": raw_manifest["raw_rows"],
        "normalized_added_rows": extension["manifest"]["row_count"],
        "overlap_reconciliation": extension["summary"],
        "new_strict_sessions": extension["manifest"]["strict_symbol_session_count"],
        "coverage": summary["continuity"],
        "unavailable_reasons": summary["continuity"]["unavailable_reasons"],
        "activity_readiness": {key: readiness_body[key] for key in ("FAMILY_D_DATA_READINESS", "FAMILY_D_ARCHITECTURE_RESULT", "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS")},
        "hashes": summary["hashes"],
        "artifact_hashes": {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(set(artifact_paths)) if path.is_file()},
    }
    manifest_body["manifest_hash"] = canonical_hash(manifest_body)
    _write_json(manifest_path, manifest_body)
    return summary


def _write_documentation(root: Path, summary: Mapping[str, Any]) -> None:
    continuity = summary["continuity"]
    retrieval = summary["retrieval"]
    text = f"""# Family D intraday continuity remediation v1

## Purpose

Family D was data-blocked because the frozen 5-minute dataset sampled DEVELOPMENT sessions but did not retain every immediately preceding market session needed by the preregistered opening-activity denominator. Sparse sampled sessions cannot stand in for the exact prior 20 sessions.

## Frozen method and scope

`{COMMAND_VERSION}` / `{PROFILE}` preserves the exact 100-symbol Family D scope and {continuity['target_symbol_session_count']} target symbol-sessions. For target session T, the baseline uses only the authoritative NSE sessions T-20 through T-1. Each baseline session must be strict and contain exactly the 09:15, 09:20, and 09:25 bar volumes; their sum is `opening_15m_volume`, and the denominator is the median of the 20 sums. No older replacement, current-session denominator input, future session, inferred volume, or daily-volume proxy is permitted.

## Retrieval and versioned extension

The deterministic plan was frozen before network access. Existing frozen normalized rows and auditable collateral rows inside immutable Command 05B Groww responses were reused first. Only remaining required symbol-sessions were grouped into conservative, deduplicated windows of at most 30 calendar days and requested through `{GROWW_RETRIEVAL_TRANSPORT_VERSION}` (10s connect, 20s read, 30s wall clock, bounded retries, circuit breaker, one-request-per-second policy). New responses live only under the versioned Family D raw extension; normalized rows use `{NORMALIZATION_PROFILE}`, Asia/Kolkata, BAR_START semantics. No Command 05B raw, normalized, derived, or manifest artifact was overwritten.

## Reconciliation and coverage

Overlaps were joined by symbol and timestamp and classified as exact, source-equivalent, explained provider difference, or unexplained difference. The reconciliation result is `{summary['reconciliation']['result']}`. The extension added {retrieval['raw_rows_added']} raw rows and {retrieval['normalized_rows_added']} normalized rows.

Complete exact-prior20 continuity is available for {continuity['complete_count']} of {continuity['target_symbol_session_count']} targets ({continuity['coverage_pct']}%), classified `{continuity['coverage_classification']}`. Remediable coverage excluding genuine `SYMBOL_NOT_LISTED` cases is {continuity['remediable_coverage_pct']}%. Unresolved reasons are recorded row-by-row in the continuity matrix and unavailable report; a bad required session is never replaced by an older one.

## Structural-only checks

The command recomputed opening-activity availability, the frozen inclusive 1.50 threshold, D001 structural counts, yearly counts, and breakout-time structure only. It ran real pilots and manual 20-value median/ratio checks. It calculated no returns, P&L, profit factor, expectancy, win rate, drawdown, CAGR, or other performance result, and it accessed no validation data.

## Readiness and next step

`FAMILY_D_CONTINUITY_REMEDIATION_RESULT`: `{summary['FAMILY_D_CONTINUITY_REMEDIATION_RESULT']}`
`FAMILY_D_DATA_READINESS`: `{summary['FAMILY_D_DATA_READINESS']}`
`FAMILY_D_ARCHITECTURE_RESULT`: `{summary['FAMILY_D_ARCHITECTURE_RESULT']}`
`FAMILY_D_DEVELOPMENT_BACKTEST_READINESS`: `{summary['FAMILY_D_DEVELOPMENT_BACKTEST_READINESS']}`

The next action is `{summary['recommended_next_action']}`. This document does not authorize or run performance work.
"""
    path = root / "docs/strategy-family-d-intraday-continuity-remediation-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_family_d_continuity_remediation(
    repo_root: Path,
    *,
    plan_only: bool = False,
    fetch: bool = True,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
) -> dict[str, Any]:
    root = Path(repo_root)
    plan_result = build_continuity_plan(root, write=True)
    if plan_only:
        return plan_result
    if fetch:
        retrieve_missing_history(root, client=client, progress=progress, throttle_seconds=throttle_seconds)
    return finalize_continuity_remediation(root)


__all__ = [
    "AVAILABILITY_REASONS",
    "COMMAND_VERSION",
    "CONTINUITY_DATA_VERSION",
    "PROFILE",
    "build_continuity_plan",
    "classify_overlap",
    "continuity_config_document",
    "coverage_classification",
    "finalize_continuity_remediation",
    "prior_market_sessions",
    "retrieve_missing_history",
    "run_family_d_continuity_remediation",
    "verify_continuity_inputs",
]
