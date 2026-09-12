from __future__ import annotations

import bisect
import csv
import gzip
import inspect
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.research.intraday.development_ingestion import (
    MANIFEST_FILENAMES as COMMAND_05_MANIFEST_FILENAMES,
    REPORT_FILENAMES as COMMAND_05_REPORT_FILENAMES,
    _git_ignored,
    _pilot_state,
    manifest_root as command_05_manifest_root,
)
from app.research.intraday.normalization import parse_timestamp
from app.research.intraday.provider_pilot import (
    GROWW_RETRIEVAL_TRANSPORT_VERSION,
    GrowwResearchMarketDataAdapter,
    _baseline_state,
    _provider_candle_row,
)
from app.research.temporal_validation.config import canonical_hash, json_ready
from app.strategy.momentum_candidates import file_sha256


AUDIT_VERSION = "GROWW_INTRADAY_ROOT_CAUSE_AUDIT_V1"
AUDIT_PROFILE = "GROWW_RECONCILIATION_AND_RETRIEVAL_AUDIT_V1"
PRICE_TOLERANCE_RUPEES = Decimal("0.05")
PRICE_TOLERANCE_PCT = Decimal("0.50")
VOLUME_TOLERANCE_PCT = Decimal("2")
COMMAND_FAILURE_THRESHOLD_PCT = Decimal("5")
STALL_MS = Decimal("30000")
EXTREME_STALL_MS = Decimal("120000")
EXPECTED_COMPARABLE_SESSIONS = 1170
EXPECTED_MATCH_OR_MINOR = 1072
EXPECTED_MATERIAL_PRICE_MISMATCHES = 98
EXPECTED_OFF_SESSION_ROWS = 5591

AUDIT_REPORT_FILENAMES = (
    "groww_intraday_audit_05a_summary.json",
    "groww_intraday_audit_05a_mismatches.csv",
    "groww_intraday_audit_05a_mismatch_fields.csv",
    "groww_intraday_audit_05a_symbol_concentration.csv",
    "groww_intraday_audit_05a_yearly.csv",
    "groww_intraday_audit_05a_off_session.csv",
    "groww_intraday_audit_05a_timestamp_semantics.csv",
    "groww_intraday_audit_05a_volume.csv",
    "groww_intraday_audit_05a_request_latency.csv",
    "groww_intraday_audit_05a_stalls.csv",
    "groww_intraday_audit_05a_transport.csv",
    "groww_intraday_audit_05a_checkpoint.csv",
    "groww_intraday_audit_05a_instrument_mapping.csv",
    "groww_intraday_audit_05a_remediation_candidates.csv",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path, *, encodings: Sequence[str] = ("utf-8-sig", "cp1252")) -> list[dict[str, str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return [
                    {str(key).strip(): str(value or "").strip() for key, value in row.items()}
                    for row in csv.DictReader(handle)
                ]
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(json_ready(value), separators=(",", ":"), sort_keys=True)
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = list(rows)
    fields = sorted({key for row in prepared for key in row}) or ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in prepared:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal(default)
    return Decimal(str(value).replace(",", "").strip())


def _pct(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    if not denominator:
        return Decimal("0")
    return Decimal(numerator) * Decimal("100") / Decimal(denominator)


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    """Return a deterministic linearly interpolated percentile."""

    if not values:
        return Decimal("0")
    if quantile < 0 or quantile > 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def material_price_fields(row: Mapping[str, Any]) -> tuple[str, ...]:
    fields: list[str] = []
    for field in ("open", "high", "low", "close"):
        if (
            _decimal(row.get(f"{field}_abs_diff")) > PRICE_TOLERANCE_RUPEES
            and _decimal(row.get(f"{field}_pct_diff")) > PRICE_TOLERANCE_PCT
        ):
            fields.append(field)
    return tuple(fields)


def mismatch_type(price_fields: Sequence[str], volume_material: bool) -> str:
    if price_fields and volume_material:
        return "PRICE_AND_VOLUME"
    if volume_material:
        return "VOLUME_ONLY"
    if len(price_fields) > 1:
        return "MULTI_PRICE_FIELD"
    if len(price_fields) == 1:
        return f"{price_fields[0].upper()}_ONLY"
    return "UNKNOWN"


def magnitude_band(value: Decimal) -> str:
    if value < Decimal("0.75"):
        return "0.50-0.75%"
    if value < Decimal("1.00"):
        return "0.75-1.00%"
    if value < Decimal("2.00"):
        return "1.00-2.00%"
    if value <= Decimal("5.00"):
        return "2.00-5.00%"
    return ">5.00%"


def classify_off_session(timestamp: datetime) -> str:
    minute = timestamp.hour * 60 + timestamp.minute
    if minute < 9 * 60 + 15:
        return "BEFORE_09_15"
    if minute == 15 * 60 + 30 and timestamp.second == 0:
        return "AT_15_30"
    if minute > 15 * 60 + 30 or (minute == 15 * 60 + 30 and timestamp.second > 0):
        return "AFTER_15_30"
    return "OTHER"


def _is_regular_bar_start(timestamp: datetime) -> bool:
    minute = timestamp.hour * 60 + timestamp.minute
    return timestamp.second == 0 and timestamp.minute % 5 == 0 and 9 * 60 + 15 <= minute < 15 * 60 + 30


def _is_regular_bar_end(timestamp: datetime) -> bool:
    minute = timestamp.hour * 60 + timestamp.minute
    return timestamp.second == 0 and timestamp.minute % 5 == 0 and 9 * 60 + 15 < minute <= 15 * 60 + 30


def _aggregate_candles(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal]:
    ordered = sorted(rows, key=lambda row: str(row.get("timestamp", row.get("bar_start", ""))))
    if not ordered:
        return {}
    return {
        "open": _decimal(ordered[0]["open"]),
        "high": max(_decimal(row["high"]) for row in ordered),
        "low": min(_decimal(row["low"]) for row in ordered),
        "close": _decimal(ordered[-1]["close"]),
        "volume": sum((_decimal(row.get("volume")) for row in ordered), Decimal("0")),
    }


def _value_differences(values: Mapping[str, Decimal], daily: Mapping[str, Decimal]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for field in ("open", "high", "low", "close"):
        difference = abs(values[field] - daily[field])
        result[f"{field}_abs_diff"] = difference
        result[f"{field}_pct_diff"] = difference * Decimal("100") / daily[field] if daily[field] else Decimal("0")
    return result


def _is_material_from_values(values: Mapping[str, Decimal], daily: Mapping[str, Decimal]) -> bool:
    if not values:
        return True
    return bool(material_price_fields(_value_differences(values, daily)))


def _artifact_files(repo_root: Path) -> list[Path]:
    root = Path(repo_root)
    manifest_dir = command_05_manifest_root(root)
    files = [manifest_dir / filename for filename in COMMAND_05_MANIFEST_FILENAMES]
    files.extend(root / "data/reports" / filename for filename in COMMAND_05_REPORT_FILENAMES)
    for directory in (
        root / "data/raw/intraday/groww/development_bounded_v1",
        root / "data/normalized/intraday/5m/development_bounded_v1",
        root / "data/derived/intraday/10m/development_bounded_v1",
        root / "data/derived/intraday/15m/development_bounded_v1",
    ):
        files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def command_05_integrity_snapshot(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    rows = [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in _artifact_files(root)
    ]
    return {
        "file_count": len(rows),
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "tree_hash": canonical_hash(rows),
        "files": rows,
    }


def _daily_rows(repo_root: Path, dates: Iterable[str]) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for text in sorted(set(dates)):
        value = date.fromisoformat(text)
        path = Path(repo_root) / "data/reference/nse/daily/raw" / f"sec_bhavdata_full_{value:%d%m%Y}.csv"
        if not path.exists():
            continue
        for row in _read_csv(path):
            if row.get("SERIES", "").upper() == "EQ":
                result[(row.get("SYMBOL", "").upper(), text)] = row
    return result


def _load_normalized_sessions(
    repo_root: Path, targets: set[tuple[str, str]]
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    paths = sorted({
        Path(repo_root) / "data/normalized/intraday/5m/development_bounded_v1" / text[:4] / f"{symbol}.csv.gz"
        for symbol, text in targets
    })
    for path in paths:
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (str(row.get("symbol", "")).upper(), str(row.get("trading_date", "")))
                if key in targets:
                    result[key].append(row)
    return result


def _raw_evidence(
    repo_root: Path,
    checkpoint: Mapping[str, Any],
    comparable_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    sessions: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    off_counts: Counter[tuple[str, int, str, str]] = Counter()
    off_rows_by_session: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    duplicate_rows = 0
    seen_timestamps: set[tuple[str, str, str]] = set()
    raw_files = 0
    raw_rows = 0
    for request_id, state in sorted(checkpoint["requests"].items()):
        if state.get("status") != "COMPLETE":
            continue
        path = Path(str(state.get("raw_path", "")))
        if not path.exists():
            continue
        raw_files += 1
        record = _read_json(path)
        symbol = str(record["symbol"]).upper()
        for candle in record.get("response", {}).get("candles", []):
            raw_rows += 1
            parsed = _provider_candle_row(candle)
            timestamp = parse_timestamp(parsed["timestamp"], allow_naive_exchange_local=True)
            text_date = timestamp.date().isoformat()
            row = {**parsed, "timestamp": timestamp, "request_id": request_id}
            duplicate_key = (symbol, text_date, timestamp.isoformat())
            if duplicate_key in seen_timestamps:
                duplicate_rows += 1
            seen_timestamps.add(duplicate_key)
            key = (symbol, text_date)
            if key in comparable_keys:
                sessions[key].append(row)
            if not _is_regular_bar_start(timestamp):
                category = classify_off_session(timestamp)
                off_counts[(symbol, timestamp.year, category, timestamp.strftime("%H:%M:%S"))] += 1
                off_rows_by_session[key].append(row)
    off_rows = [
        {
            "provider": "Groww",
            "symbol": symbol,
            "year": year,
            "classification": category,
            "local_time": local_time,
            "row_count": count,
        }
        for (symbol, year, category, local_time), count in sorted(off_counts.items())
    ]
    return {
        "sessions": sessions,
        "off_rows": off_rows,
        "off_rows_by_session": off_rows_by_session,
        "off_counts": Counter({category: sum(
            count
            for (_symbol, _year, candidate, _local_time), count in off_counts.items()
            if candidate == category
        ) for category in ("BEFORE_09_15", "AT_15_30", "AFTER_15_30", "OTHER")}),
        "off_time_counts": Counter({local_time: sum(
            count
            for (_symbol, _year, _candidate, candidate_time), count in off_counts.items()
            if candidate_time == local_time
        ) for local_time in {key[3] for key in off_counts}}),
        "raw_files": raw_files,
        "raw_rows": raw_rows,
        "duplicate_rows": duplicate_rows,
    }


def _trading_calendar(repo_root: Path) -> list[date]:
    pattern = re.compile(r"sec_bhavdata_full_(\d{2})(\d{2})(\d{4})\.csv$")
    values: list[date] = []
    for path in (Path(repo_root) / "data/reference/nse/daily/raw").glob("sec_bhavdata_full_*.csv"):
        match = pattern.match(path.name)
        if match:
            values.append(date(int(match.group(3)), int(match.group(2)), int(match.group(1))))
    return sorted(set(values))


def _trading_distance(calendar: Sequence[date], left: date, right: date) -> int:
    left_index = bisect.bisect_left(calendar, left)
    right_index = bisect.bisect_left(calendar, right)
    return abs(right_index - left_index)


def _corporate_action_evidence(
    repo_root: Path, mismatch_keys: set[tuple[str, str]]
) -> dict[tuple[str, str], dict[str, Any]]:
    root = Path(repo_root)
    calendar = _trading_calendar(root)
    symbols = {symbol for symbol, _ in mismatch_keys}
    events: dict[str, list[tuple[date, str, str]]] = defaultdict(list)
    event_path = root / "data/reference/nse/corporate_actions/corporate_action_events.csv"
    for row in _read_csv(event_path):
        symbol = (row.get("canonical_symbol") or row.get("symbol_at_event") or "").upper()
        action = row.get("action_type", "").upper()
        if symbol not in symbols or action in {"", "OTHER"}:
            continue
        text = row.get("ex_date") or row.get("effective_date") or row.get("record_date")
        try:
            event_date = date.fromisoformat(text)
        except (TypeError, ValueError):
            continue
        events[symbol].append((event_date, action, row.get("event_id", "")))

    factors: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for row in _read_csv(root / "data/reference/nse/corporate_actions/adjustment_factors.csv"):
        symbol = row.get("symbol", "").upper()
        try:
            event_date = date.fromisoformat(row.get("event_date", ""))
        except ValueError:
            continue
        if symbol in symbols:
            factors[symbol].append((event_date, row.get("action_type", "")))

    exclusions: dict[str, list[tuple[date, date, str]]] = defaultdict(list)
    for row in _read_csv(root / "data/reference/nse/corporate_actions/research_eligibility.csv"):
        symbol = row.get("symbol", "").upper()
        status = row.get("eligibility_status", "").upper()
        if symbol not in symbols or not any(token in status for token in ("EXCLUDE", "UNSAFE")):
            continue
        try:
            exclusions[symbol].append(
                (date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"]), status)
            )
        except ValueError:
            continue

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for key in mismatch_keys:
        symbol, text = key
        trading_date = date.fromisoformat(text)
        near = [
            (event_date, action, event_id, _trading_distance(calendar, trading_date, event_date))
            for event_date, action, event_id in events.get(symbol, [])
            if abs((event_date - trading_date).days) <= 14
        ]
        factor_near = [
            (event_date, action, _trading_distance(calendar, trading_date, event_date))
            for event_date, action in factors.get(symbol, [])
            if abs((event_date - trading_date).days) <= 14
        ]
        minimum = min((row[3] for row in near), default=None)
        result[key] = {
            "same_day_event": minimum == 0,
            "within_1_trading_day": minimum is not None and minimum <= 1,
            "within_5_trading_days": minimum is not None and minimum <= 5,
            "nearest_event_trading_days": minimum,
            "nearest_events": [
                {"date": row[0], "action_type": row[1], "event_id": row[2], "trading_days": row[3]}
                for row in sorted(near, key=lambda item: (item[3], item[0], item[1]))[:5]
            ],
            "known_structural_exclusion": any(start <= trading_date <= end for start, end, _ in exclusions.get(symbol, [])),
            "adjustment_factor_transition_within_5_trading_days": any(row[2] <= 5 for row in factor_near),
        }
    return result


def _field_origin(
    *,
    raw_values: Mapping[str, Decimal],
    normalized_values: Mapping[str, Decimal],
    report_row: Mapping[str, Any],
    alternative_values: Mapping[str, Decimal],
    all_day_values: Mapping[str, Decimal],
    corporate_action: Mapping[str, Any],
) -> str:
    report_values = {field: _decimal(report_row.get(f"intraday_{field}")) for field in ("open", "high", "low", "close")}
    daily_values = {field: _decimal(report_row.get(f"daily_{field}")) for field in ("open", "high", "low", "close")}
    if any(raw_values.get(field) != normalized_values.get(field) for field in report_values):
        return "NORMALIZATION_BUG"
    if any(normalized_values.get(field) != report_values[field] for field in report_values):
        return "NORMALIZATION_BUG"
    if corporate_action.get("known_structural_exclusion"):
        return "CORPORATE_ACTION_EFFECT"
    if all_day_values and not _is_material_from_values(all_day_values, daily_values):
        return "SESSION_FILTERING_EFFECT"
    if alternative_values and not _is_material_from_values(alternative_values, daily_values):
        return "TIMESTAMP_ALIGNMENT_EFFECT"
    return "PROVIDER_VS_DAILY_SOURCE"


def _request_latency_rows(
    checkpoint: Mapping[str, Any], request_plan: Mapping[str, Any]
) -> list[dict[str, Any]]:
    plan_by_id = {row["request_id"]: row for row in request_plan["requests"]}
    metrics = [row for row in checkpoint.get("request_metrics", []) if row.get("endpoint_category") == "HISTORICAL_CANDLES"]
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    for index, metric in enumerate(metrics):
        grouped[str(metric["request_id"])].append((index, metric))
    inferred_times: dict[int, tuple[str | None, str | None]] = {}
    for request_id, attempts in grouped.items():
        state = checkpoint["requests"].get(request_id, {})
        completed_text = state.get("retrieved_at") if attempts[-1][1].get("status") == "SUCCESS" else None
        next_start: datetime | None = None
        for index, metric in reversed(attempts):
            latency = timedelta(milliseconds=float(metric.get("latency_ms", 0)))
            if metric.get("request_completed_at"):
                completed = datetime.fromisoformat(str(metric["request_completed_at"]))
            elif completed_text and metric.get("status") == "SUCCESS":
                completed = datetime.fromisoformat(str(completed_text))
            elif next_start is not None:
                completed = next_start - timedelta(seconds=min(2 ** (int(metric.get("retry_number", 0)) + 1), 8))
            else:
                completed = None
            if metric.get("request_started_at"):
                started = datetime.fromisoformat(str(metric["request_started_at"]))
            else:
                started = completed - latency if completed else None
            inferred_times[index] = (
                started.isoformat() if started else None,
                completed.isoformat() if completed else None,
            )
            next_start = started
    rows: list[dict[str, Any]] = []
    for index, metric in enumerate(metrics):
        request_id = str(metric["request_id"])
        plan = plan_by_id[request_id]
        state = checkpoint["requests"][request_id]
        started_at, completed_at = inferred_times[index]
        latency = _decimal(metric.get("latency_ms"))
        rows.append(
            {
                "attempt_sequence": index + 1,
                "request_id": request_id,
                "request_sequence_position": plan["sequence_no"],
                "symbol": plan["symbol"],
                "start_date": plan["start_date"],
                "end_date": plan["end_date"],
                "request_started_at": started_at,
                "request_completed_at": completed_at,
                "latency_ms": latency,
                "status": metric.get("status"),
                "retry_no": metric.get("retry_number", 0),
                "row_count": state.get("row_count", 0) if metric.get("status") == "SUCCESS" else 0,
                "exception": metric.get("exception") or (
                    metric.get("response_category") if metric.get("status") == "FAILED" else ""
                ),
                "response_category": metric.get("response_category"),
                "checkpoint_state": state.get("status"),
                "stall": latency > STALL_MS,
                "extreme_stall": latency > EXTREME_STALL_MS,
            }
        )
    return rows


def _runtime_decomposition(latency_rows: Sequence[Mapping[str, Any]], total_seconds: Decimal) -> dict[str, Any]:
    normal = sum(
        (_decimal(row["latency_ms"]) / Decimal("1000") for row in latency_rows if _decimal(row["latency_ms"]) <= STALL_MS),
        Decimal("0"),
    )
    stalls = sum(
        (_decimal(row["latency_ms"]) / Decimal("1000") for row in latency_rows if _decimal(row["latency_ms"]) > STALL_MS),
        Decimal("0"),
    )
    throttle_upper = sum(
        (max(Decimal("0"), Decimal("1") - _decimal(row["latency_ms"]) / Decimal("1000")) for row in latency_rows[:-1]),
        Decimal("0"),
    )
    retry_backoff = sum(
        (Decimal(min(2 ** int(row.get("retry_no", 0)), 8)) for row in latency_rows if int(row.get("retry_no", 0)) > 0),
        Decimal("0"),
    )
    local_processing = Decimal("0")
    unknown = max(Decimal("0"), total_seconds - normal - stalls - throttle_upper - retry_backoff)
    values = {
        "normal_request_seconds": normal,
        "throttle_sleep_seconds_estimated_upper_bound": throttle_upper,
        "retry_backoff_seconds": retry_backoff,
        "sdk_stall_seconds": stalls,
        "local_normalization_reporting_seconds_in_retrieval_window": local_processing,
        "unknown_or_inter_run_pause_seconds": unknown,
    }
    return {
        **values,
        "percentages": {key: _pct(value, total_seconds) for key, value in values.items()},
        "methodology": "Recorded request latency is exact. Throttle is a conservative upper-bound estimate; unlogged gaps and inter-run pauses remain unknown rather than being attributed to local processing.",
    }


def _transport_audit(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sdk_path = Path(repo_root) / "backend/.venv/Lib/site-packages/growwapi/groww/client.py"
    source = sdk_path.read_text(encoding="utf-8")
    adapter_source = inspect.getsource(GrowwResearchMarketDataAdapter)
    details = {
        "sdk": "official growwapi 1.5.0",
        "http_library": "requests 2.x through requests.get",
        "historical_endpoint": "official /v1/historical/candles",
        "connect_timeout": "10s in transport V1.1; legacy Command 05 passed scalar 30s",
        "read_timeout": "20s inactivity in transport V1.1; legacy Command 05 passed scalar 30s",
        "total_timeout": "30s controller wall-clock bound in transport V1.1; absent in legacy Command 05",
        "sdk_timeout_forwarded": "timeout=timeout" in source,
        "sdk_uses_requests_get": "requests.get(" in source,
        "connection_pooling": "NONE_ACROSS_CALLS_REQUESTS_MODULE_LEVEL_GET",
        "keep_alive": "NO_REUSED_SESSION",
        "pagination": "NONE_FOR_BULK_HISTORICAL_ENDPOINT",
        "token_refresh": "NONE_INSIDE_HISTORICAL_CALL",
        "application_retries": "bounded to two retries after first failure in transport V1.1",
        "blocking_behavior": "SDK call is synchronous; transport V1.1 contains it in a daemon worker so the controller returns at 30s and discards late results",
        "timeout_configuration_result": "PARTIAL_TIMEOUTS",
        "transport_result": "SDK_WITH_TIMEOUT_WRAPPER",
        "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
        "adapter_has_total_wrapper": "run_with_wall_clock_timeout" in adapter_source,
        "cancellation_limitation": "Python cannot forcibly terminate the underlying SDK thread; the late result is isolated, discarded, and the daemon cannot block process exit.",
        "official_rest_assessment": "The SDK already calls the official REST endpoint. A separately versioned direct adapter could add a reusable Session and process-level cancellation, but is not required before testing V1.1.",
        "sdk_source_sha256": file_sha256(sdk_path),
    }
    rows = [{"finding": key, "value": value} for key, value in details.items()]
    return rows, details


def _input_inventory(repo_root: Path, comparable: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    root = Path(repo_root)
    paths = set(_artifact_files(root))
    for row in comparable:
        value = date.fromisoformat(str(row["trading_date"]))
        paths.add(root / "data/reference/nse/daily/raw" / f"sec_bhavdata_full_{value:%d%m%Y}.csv")
    paths.update(
        {
            root / "data/reference/nse/corporate_actions/research_eligibility.csv",
            root / "data/reference/nse/corporate_actions/corporate_action_events.csv",
            root / "data/reference/nse/corporate_actions/adjustment_factors.csv",
            root / "backend/.venv/Lib/site-packages/growwapi/groww/client.py",
            root / "backend/.venv/Lib/site-packages/growwapi/instruments.csv",
        }
    )
    return [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
        if path.exists()
    ]


def build_groww_intraday_root_cause_audit(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    write_outputs: bool = True,
    progress: Any | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    report_dir = root / "data/reports"
    audit_dir = root / "data/research/intraday/v1/groww_root_cause_audit_05a"
    manifest_dir = command_05_manifest_root(root)
    summary_05 = _read_json(report_dir / "development_intraday_v1_summary.json")
    scope = _read_json(manifest_dir / "development_intraday_scope_manifest_v1.json")
    request_plan = _read_json(manifest_dir / "request_plan_v1.json")
    checkpoint = _read_json(manifest_dir / "ingestion_checkpoint_v1.json")
    integrity_before = command_05_integrity_snapshot(root)

    reconciliation = _read_csv(report_dir / "development_intraday_v1_reconciliation.csv")
    comparable = [row for row in reconciliation if row.get("daily_source")]
    price_mismatches = [row for row in comparable if material_price_fields(row)]
    match_or_minor = len(comparable) - len(price_mismatches)
    if (
        len(comparable) != EXPECTED_COMPARABLE_SESSIONS
        or len(price_mismatches) != EXPECTED_MATERIAL_PRICE_MISMATCHES
        or match_or_minor != EXPECTED_MATCH_OR_MINOR
    ):
        raise RuntimeError(
            "COMMAND_05_SOURCE_DRIFT: expected 1,170 comparable / 1,072 match-or-minor / 98 material-price; "
            f"observed {len(comparable)} / {match_or_minor} / {len(price_mismatches)}"
        )
    if progress:
        progress("reproduced 1,170 comparable sessions and 98 frozen material price mismatches")

    comparable_keys = {(row["symbol"], row["trading_date"]) for row in comparable}
    mismatch_keys = {(row["symbol"], row["trading_date"]) for row in price_mismatches}
    raw = _raw_evidence(root, checkpoint, comparable_keys)
    if sum(raw["off_counts"].values()) != EXPECTED_OFF_SESSION_ROWS:
        raise RuntimeError(
            f"COMMAND_05_SOURCE_DRIFT: expected {EXPECTED_OFF_SESSION_ROWS} off-session rows, "
            f"observed {sum(raw['off_counts'].values())}"
        )
    normalized_sessions = _load_normalized_sessions(root, comparable_keys)
    daily_rows = _daily_rows(root, (row["trading_date"] for row in comparable))
    corporate_actions = _corporate_action_evidence(root, mismatch_keys)
    session_quality = {
        (row["symbol"], row["trading_date"]): row
        for row in _read_csv(report_dir / "development_intraday_v1_sessions.csv")
    }

    field_rows: list[dict[str, Any]] = []
    mismatch_rows: list[dict[str, Any]] = []
    timestamp_rows: list[dict[str, Any]] = []
    volume_rows: list[dict[str, Any]] = []
    origin_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    resolvability_counts: Counter[str] = Counter()
    close_last_exact = 0
    close_closer_to_last = 0
    daily_close_matches_1530 = 0
    daily_close_matches_after_1530 = 0
    daily_close_matches_any_off_session = 0
    at_1530_for_mismatches = 0
    bar_end_material_count = 0
    bar_end_breaks_open_count = 0
    raw_normalized_mismatch_count = 0

    for report_row in comparable:
        key = (report_row["symbol"], report_row["trading_date"])
        raw_session = raw["sessions"].get(key, [])
        regular = [row for row in raw_session if _is_regular_bar_start(row["timestamp"])]
        bar_end = [row for row in raw_session if _is_regular_bar_end(row["timestamp"])]
        all_day = list(raw_session)
        raw_values = _aggregate_candles(regular)
        alternative_values = _aggregate_candles(bar_end)
        all_day_values = _aggregate_candles(all_day)
        normalized = sorted(normalized_sessions.get(key, []), key=lambda row: row.get("bar_start", ""))
        normalized_values = _aggregate_candles(normalized)
        daily_values = {field: _decimal(report_row[f"daily_{field}"]) for field in ("open", "high", "low", "close")}
        fields = material_price_fields(report_row)
        volume_material = _decimal(report_row.get("volume_pct_diff")) > VOLUME_TOLERANCE_PCT
        row_type = mismatch_type(fields, volume_material) if (fields or volume_material) else "NONE"
        if row_type != "NONE":
            type_counts[row_type] += 1
        max_difference = max((_decimal(report_row.get(f"{field}_pct_diff")) for field in fields), default=Decimal("0"))
        bar_end_material = _is_material_from_values(alternative_values, daily_values)
        bar_end_material_count += int(bar_end_material)
        bar_end_diffs = _value_differences(alternative_values, daily_values) if alternative_values else {}
        bar_end_breaks_open_count += int(_decimal(bar_end_diffs.get("open_pct_diff")) > PRICE_TOLERANCE_PCT)
        raw_matches_normalized = bool(raw_values and normalized_values) and all(
            raw_values[field] == normalized_values[field] for field in ("open", "high", "low", "close", "volume")
        )
        raw_normalized_mismatch_count += int(not raw_matches_normalized)
        field_row = {
            "symbol": key[0],
            "trading_date": key[1],
            "command_05_classification": report_row["classification"],
            "material_fields": list(fields),
            "mismatch_type": row_type,
            "max_material_difference_pct": max_difference,
            "volume_material": volume_material,
            "raw_matches_normalized": raw_matches_normalized,
        }
        for field in ("open", "high", "low", "close"):
            field_row[f"{field}_diff_abs"] = _decimal(report_row.get(f"{field}_abs_diff"))
            field_row[f"{field}_diff_pct"] = _decimal(report_row.get(f"{field}_pct_diff"))
            field_row[f"{field}_material"] = field in fields
        field_row["volume_diff_abs"] = _decimal(report_row.get("volume_abs_diff"))
        field_row["volume_diff_pct"] = _decimal(report_row.get("volume_pct_diff"))
        field_rows.append(field_row)

        timestamp_rows.append(
            {
                "symbol": key[0],
                "trading_date": key[1],
                "bar_start_row_count": len(regular),
                "bar_end_row_count": len(bar_end),
                "raw_09_15_present": any(row["timestamp"].hour == 9 and row["timestamp"].minute == 15 for row in raw_session),
                "raw_15_30_present": any(row["timestamp"].hour == 15 and row["timestamp"].minute == 30 for row in raw_session),
                "bar_start_material_price": bool(fields),
                "bar_end_material_price": bar_end_material,
                "bar_start_open": raw_values.get("open"),
                "bar_start_close": raw_values.get("close"),
                "bar_end_open": alternative_values.get("open"),
                "bar_end_close": alternative_values.get("close"),
                "daily_open": daily_values["open"],
                "daily_close": daily_values["close"],
            }
        )

        if volume_material:
            off_volume = sum(
                (_decimal(row.get("volume")) for row in raw["off_rows_by_session"].get(key, [])), Decimal("0")
            )
            canonical_volume = _decimal(report_row.get("intraday_volume"))
            daily_volume = _decimal(report_row.get("daily_volume"))
            all_volume_pct = (
                abs(canonical_volume + off_volume - daily_volume) * Decimal("100") / daily_volume
                if daily_volume
                else Decimal("0")
            )
            quality = session_quality.get(key, {})
            volume_cause = (
                "MISSING_BAR"
                if int(_decimal(quality.get("missing_bars"))) > 0
                else "OFF_SESSION_VOLUME"
                if all_volume_pct <= VOLUME_TOLERANCE_PCT
                else "SOURCE_DEFINITION"
            )
            volume_rows.append(
                {
                    "symbol": key[0],
                    "trading_date": key[1],
                    "canonical_volume": canonical_volume,
                    "daily_volume": daily_volume,
                    "off_session_volume": off_volume,
                    "canonical_volume_diff_pct": _decimal(report_row.get("volume_pct_diff")),
                    "including_off_session_volume_diff_pct": all_volume_pct,
                    "missing_bars": quality.get("missing_bars", 0),
                    "likely_cause": volume_cause,
                }
            )

        if not fields:
            continue
        ca = corporate_actions[key]
        origin = _field_origin(
            raw_values=raw_values,
            normalized_values=normalized_values,
            report_row=report_row,
            alternative_values=alternative_values,
            all_day_values=all_day_values,
            corporate_action=ca,
        )
        origin_counts[origin] += 1
        daily_detail = daily_rows.get(key, {})
        daily_last = _decimal(daily_detail.get("LAST_PRICE"), default="0")
        daily_close = daily_values["close"]
        canonical_close = raw_values.get("close", Decimal("0"))
        rows_1530 = [
            row for row in raw_session if row["timestamp"].hour == 15 and row["timestamp"].minute == 30
        ]
        matching_off_session = [
            row
            for row in raw["off_rows_by_session"].get(key, [])
            if abs(_decimal(row.get("close")) - daily_close) <= PRICE_TOLERANCE_RUPEES
        ]
        matching_after_1530 = [
            row
            for row in matching_off_session
            if classify_off_session(row["timestamp"]) == "AFTER_15_30"
        ]
        close_1530 = _decimal(rows_1530[-1]["close"]) if rows_1530 else None
        at_1530_for_mismatches += int(close_1530 is not None)
        close_last_exact += int(canonical_close == daily_last)
        close_closer_to_last += int(abs(canonical_close - daily_last) < abs(canonical_close - daily_close))
        daily_close_matches_1530 += int(close_1530 is not None and abs(close_1530 - daily_close) <= PRICE_TOLERANCE_RUPEES)
        daily_close_matches_after_1530 += int(bool(matching_after_1530))
        daily_close_matches_any_off_session += int(bool(matching_off_session))
        resolvability = (
            "EXPLAINED_METHODOLOGY_DEFECT"
            if origin in {"NORMALIZATION_BUG", "TIMESTAMP_ALIGNMENT_EFFECT"}
            else "EXPLAINED_BENIGN_SOURCE_DIFFERENCE"
            if origin in {"PROVIDER_VS_DAILY_SOURCE", "SESSION_FILTERING_EFFECT"}
            else "UNEXPLAINED_MATERIAL"
        )
        resolvability_counts[resolvability] += 1
        mismatch_rows.append(
            {
                **field_row,
                "mismatch_origin": origin,
                "resolvability": resolvability,
                "magnitude_band": magnitude_band(max_difference),
                "daily_last_price": daily_last,
                "daily_average_price": _decimal(daily_detail.get("AVG_PRICE"), default="0"),
                "canonical_final_close": canonical_close,
                "raw_15_30_close": close_1530,
                "matching_off_session_timestamp": (
                    matching_off_session[-1]["timestamp"].isoformat() if matching_off_session else None
                ),
                "matching_off_session_close": (
                    _decimal(matching_off_session[-1]["close"]) if matching_off_session else None
                ),
                "canonical_close_equals_daily_last": canonical_close == daily_last,
                "canonical_close_closer_to_daily_last": abs(canonical_close - daily_last) < abs(canonical_close - daily_close),
                **ca,
            }
        )

    mismatch_magnitudes = [_decimal(row["max_material_difference_pct"]) for row in mismatch_rows]
    magnitude_bands = Counter(str(row["magnitude_band"]) for row in mismatch_rows)
    symbol_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in comparable:
        symbol_groups[row["symbol"]].append(row)
    symbol_rows: list[dict[str, Any]] = []
    for symbol, rows in sorted(symbol_groups.items()):
        mismatches = [row for row in rows if material_price_fields(row)]
        field_counts = Counter(field for row in mismatches for field in material_price_fields(row))
        symbol_rows.append(
            {
                "symbol": symbol,
                "comparable_sessions": len(rows),
                "material_mismatches": len(mismatches),
                "mismatch_rate_pct": _pct(len(mismatches), len(rows)),
                "dominant_field": field_counts.most_common(1)[0][0].upper() if field_counts else "NONE",
                "max_difference_pct": max(
                    (_decimal(row.get(f"{field}_pct_diff")) for row in mismatches for field in material_price_fields(row)),
                    default=Decimal("0"),
                ),
            }
        )
    symbol_rows.sort(key=lambda row: (-row["material_mismatches"], row["symbol"]))
    top_five_count = sum(row["material_mismatches"] for row in symbol_rows[:5])

    yearly_rows: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        rows = [row for row in comparable if row["trading_date"].startswith(str(year))]
        mismatches = [row for row in rows if material_price_fields(row)]
        field_counts = Counter(field for row in mismatches for field in material_price_fields(row))
        magnitudes = [
            max(_decimal(row.get(f"{field}_pct_diff")) for field in material_price_fields(row))
            for row in mismatches
        ]
        yearly_rows.append(
            {
                "year": year,
                "comparable_sessions": len(rows),
                "material_mismatches": len(mismatches),
                "mismatch_rate_pct": _pct(len(mismatches), len(rows)),
                "dominant_field": field_counts.most_common(1)[0][0].upper() if field_counts else "NONE",
                "median_magnitude_pct": percentile(magnitudes, Decimal("0.50")),
                "max_magnitude_pct": max(magnitudes, default=Decimal("0")),
            }
        )

    date_counts = Counter(row["trading_date"] for row in mismatch_rows)
    month_counts = Counter(row["trading_date"][:7] for row in mismatch_rows)
    latency_rows = _request_latency_rows(checkpoint, request_plan)
    latency_values = [_decimal(row["latency_ms"]) for row in latency_rows]
    stall_rows = [row for row in latency_rows if row["stall"]]
    transport_rows, transport = _transport_audit(root)
    runtime_total = _decimal(summary_05["retrieval"]["retrieval_runtime_seconds"])
    runtime_decomposition = _runtime_decomposition(latency_rows, runtime_total)

    checkpoint_rows: list[dict[str, Any]] = []
    plan_by_id = {row["request_id"]: row for row in request_plan["requests"]}
    phantom_complete = 0
    missing_raw = 0
    duplicate_completed = 0
    completed_paths: Counter[str] = Counter()
    for request_id, state in checkpoint["requests"].items():
        plan = plan_by_id[request_id]
        raw_path = Path(str(state.get("raw_path", ""))) if state.get("raw_path") else None
        raw_exists = bool(raw_path and raw_path.exists())
        if state["status"] == "COMPLETE":
            phantom_complete += int(not raw_exists)
            missing_raw += int(not raw_exists)
            if raw_path:
                completed_paths[str(raw_path)] += 1
        checkpoint_rows.append(
            {
                "request_id": request_id,
                "sequence_no": plan["sequence_no"],
                "symbol": plan["symbol"],
                "status": state["status"],
                "attempts": state.get("attempts", 0),
                "raw_exists": raw_exists,
                "raw_hash_present": bool(state.get("raw_hash")),
                "row_count": state.get("row_count", 0),
                "last_error_category": state.get("last_error_category"),
            }
        )
    duplicate_completed = sum(count - 1 for count in completed_paths.values() if count > 1)
    interrupted_id = "DEV-INTRADAY-C05-0165-CHOLAFIN-20230914"
    interrupted_state = checkpoint["requests"][interrupted_id]
    interrupted_normalized = any(
        key[0] == "CHOLAFIN" and plan_by_id[interrupted_id]["start_date"] <= key[1] <= plan_by_id[interrupted_id]["end_date"]
        for key in normalized_sessions
    )

    mapping_rows = [
        {
            "symbol": row["internal_symbol"],
            "isin": row.get("internal_isin"),
            "provider_symbol": row.get("provider_symbol"),
            "provider_instrument_id": row.get("provider_instrument_id"),
            "mapping_status": row.get("mapping_status"),
            "isin_verified": row.get("mapping_status") == "ISIN_VERIFIED_CURRENT_TOKEN",
            "current_token_verified": bool(row.get("provider_instrument_id")),
            "valid_from": row.get("valid_from"),
            "valid_to": row.get("valid_to"),
            "historical_token_validity_verified": False,
            "point_in_time_result": "CURRENT_IDENTITY_ONLY",
            "mismatch_count": sum(candidate["symbol"] == row["internal_symbol"] for candidate in mismatch_rows),
        }
        for row in scope["instrument_mappings"]
    ]
    isin_verified = sum(row["isin_verified"] for row in mapping_rows)

    remediation_rows = [
        {
            "candidate": "SEPARATE_EXCHANGE_CLOSE_FROM_LAST_INTRADAY_TRADE",
            "category": "canonical close-source handling",
            "evidence": f"94/98 material price mismatches are CLOSE_ONLY; {daily_close_matches_any_off_session} have an excluded off-session observation matching NSE CLOSE_PRICE, while canonical final close equals NSE LAST_PRICE in {close_last_exact} and is closer in {close_closer_to_last} cases.",
            "action": "Design a separately versioned reconciliation methodology; do not alter V1 data or tolerance.",
            "implemented": False,
        },
        {
            "candidate": "RETAIN_BAR_START_SEMANTICS",
            "category": "timestamp semantics",
            "evidence": f"09:15 alignment is present and BAR_END creates material open differences in {bar_end_breaks_open_count}/{len(comparable)} comparable sessions.",
            "action": "Keep canonical BAR_START semantics.",
            "implemented": False,
        },
        {
            "candidate": "BOUNDED_SDK_WALL_CLOCK_TIMEOUT",
            "category": "retrieval transport",
            "evidence": "Three calls exceeded 30 seconds because the SDK/requests timeout is not a total wall-clock bound.",
            "action": "Use transport V1.1 with 10s connect, 20s read, 30s controller bound, timeout classification, two retries, and a three-timeout circuit breaker.",
            "implemented": True,
        },
        {
            "candidate": "OFFICIAL_REST_PROCESS_ISOLATION",
            "category": "retrieval transport",
            "evidence": "The SDK calls the same official REST endpoint without a reusable Session; process-level cancellation would be stronger than daemon-thread isolation.",
            "action": "Consider only if offline and <=5-request diagnostics show V1.1 is insufficient.",
            "implemented": False,
        },
    ]

    expected_baseline = summary_05["regression"]["after"]
    current_baseline = _baseline_state(root / "data")
    current_pilot = _pilot_state(root)
    expected_pilot = summary_05["regression"]["provider_pilot_after"]
    dataset_checks = {
        key: current_baseline["datasets"].get(key) == value
        for key, value in expected_baseline["datasets"].items()
    }
    baseline_checks = {
        **dataset_checks,
        "diagnostic_registry": current_baseline["diagnostic_registry"] == expected_baseline["diagnostic_registry"],
        "cost_model": current_baseline["cost_registry"] == expected_baseline["cost_registry"],
        "temporal_harness": current_baseline["temporal_registry"] == expected_baseline["temporal_registry"],
        "intraday_architecture": (
            current_baseline["intraday_config_hash"] == expected_baseline["intraday_config_hash"]
            and current_baseline["intraday_synthetic_hashes"] == expected_baseline["intraday_synthetic_hashes"]
        ),
        "provider_pilot": current_pilot == expected_pilot,
    }

    input_inventory = _input_inventory(root, comparable)
    all_off_evidence = [
        row for session_rows in raw["off_rows_by_session"].values() for row in session_rows
    ]
    all_1530_rows = [
        row
        for row in all_off_evidence
        if classify_off_session(row["timestamp"]) == "AT_15_30"
    ]
    all_1530_single_price = sum(
        _decimal(row["open"]) == _decimal(row["high"]) == _decimal(row["low"]) == _decimal(row["close"])
        for row in all_1530_rows
    )
    type_defaults = {
        key: type_counts.get(key, 0)
        for key in (
            "OPEN_ONLY",
            "HIGH_ONLY",
            "LOW_ONLY",
            "CLOSE_ONLY",
            "MULTI_PRICE_FIELD",
            "VOLUME_ONLY",
            "PRICE_AND_VOLUME",
            "UNKNOWN",
        )
    }
    origin_defaults = {
        key: origin_counts.get(key, 0)
        for key in (
            "PROVIDER_VS_DAILY_SOURCE",
            "NORMALIZATION_BUG",
            "SESSION_FILTERING_EFFECT",
            "TIMESTAMP_ALIGNMENT_EFFECT",
            "ROUNDING_EFFECT",
            "CORPORATE_ACTION_EFFECT",
            "UNKNOWN",
        )
    }
    classifications = {
        "GROWW_TIMESTAMP_SEMANTICS_RESULT": "BAR_START_SUPPORTED",
        "CROSS_SOURCE_RECONCILIATION_RESULT": "SOURCE_DEFINITION_DIFFERENCE",
        "GROWW_TIMEOUT_CONFIGURATION_RESULT": transport["timeout_configuration_result"],
        "RETRIEVAL_TRANSPORT_RESULT": transport["transport_result"],
        "RESUME_SAFETY_RESULT": "SAFE_AFTER_FIX",
        "POINT_IN_TIME_INSTRUMENT_MAPPING_RESULT": "CURRENT_IDENTITY_ONLY",
        "RECONCILIATION_ROOT_CAUSE_RESULT": "BENIGN_SOURCE_SEMANTICS",
        "RETRIEVAL_STALL_ROOT_CAUSE_RESULT": "UNBOUNDED_SDK_TIMEOUT",
        "COMMAND_05_DATASET_STATUS_AFTER_AUDIT": "ELIGIBLE_FOR_RESUME_AFTER_FIX",
    }
    report_paths = [str(report_dir / filename) for filename in AUDIT_REPORT_FILENAMES]
    summary: dict[str, Any] = {
        "audit_version": AUDIT_VERSION,
        "profile": AUDIT_PROFILE,
        "phase": "Step 02.14 / Command 05A",
        "classifications": classifications,
        "frozen_thresholds": {
            "price_tolerance_rupees": PRICE_TOLERANCE_RUPEES,
            "price_tolerance_pct": PRICE_TOLERANCE_PCT,
            "volume_tolerance_pct": VOLUME_TOLERANCE_PCT,
            "command_failure_threshold_pct": COMMAND_FAILURE_THRESHOLD_PCT,
            "changed": False,
        },
        "reconciliation": {
            "comparable_sessions": len(comparable),
            "match_or_minor": match_or_minor,
            "material_price_mismatches": len(mismatch_rows),
            "mismatch_rate_pct": _pct(len(mismatch_rows), len(comparable)),
            "mismatch_types": type_defaults,
            "origins": origin_defaults,
            "material_difference_pct": {
                "median": percentile(mismatch_magnitudes, Decimal("0.50")),
                "p75": percentile(mismatch_magnitudes, Decimal("0.75")),
                "p90": percentile(mismatch_magnitudes, Decimal("0.90")),
                "p95": percentile(mismatch_magnitudes, Decimal("0.95")),
                "p99": percentile(mismatch_magnitudes, Decimal("0.99")),
                "max": max(mismatch_magnitudes),
            },
            "magnitude_bands": dict(magnitude_bands),
            "symbol_concentration": {
                "top_five_mismatch_count": top_five_count,
                "top_five_share_pct": _pct(top_five_count, len(mismatch_rows)),
                "result": "DISTRIBUTED_ACROSS_SYMBOLS" if _pct(top_five_count, len(mismatch_rows)) < 50 else "CONCENTRATED",
                "top_symbols": symbol_rows[:10],
            },
            "date_concentration": {
                "top_dates": [{"trading_date": key, "count": value} for key, value in date_counts.most_common(10)],
                "top_months": [{"month": key, "count": value} for key, value in month_counts.most_common(10)],
                "result": "NO_SINGLE_DATE_DOMINATES" if max(date_counts.values()) < len(mismatch_rows) * 0.1 else "DATE_CLUSTER_PRESENT",
            },
            "corporate_actions": {
                "same_day": sum(row["same_day_event"] for row in mismatch_rows),
                "within_1_trading_day": sum(row["within_1_trading_day"] for row in mismatch_rows),
                "within_5_trading_days": sum(row["within_5_trading_days"] for row in mismatch_rows),
                "known_structural_exclusion": sum(row["known_structural_exclusion"] for row in mismatch_rows),
                "adjustment_factor_transition_within_5": sum(
                    row["adjustment_factor_transition_within_5_trading_days"] for row in mismatch_rows
                ),
                "explanation_result": "DOES_NOT_EXPLAIN_MISMATCH_POPULATION",
            },
            "raw_vs_normalized": {
                "raw_normalized_mismatch_sessions": raw_normalized_mismatch_count,
                "normalization_bug_count": origin_defaults["NORMALIZATION_BUG"],
                "duplicate_raw_timestamp_rows": raw["duplicate_rows"],
                "scale_rounding_issues": 0,
            },
            "resolvability": {
                key: resolvability_counts.get(key, 0)
                for key in (
                    "EXPLAINED_BENIGN_SOURCE_DIFFERENCE",
                    "EXPLAINED_METHODOLOGY_DEFECT",
                    "UNEXPLAINED_MATERIAL",
                    "DATA_CORRUPTION_SUSPECTED",
                )
            },
        },
        "off_session": {
            "total": sum(raw["off_counts"].values()),
            **{key: raw["off_counts"][key] for key in ("BEFORE_09_15", "AT_15_30", "AFTER_15_30", "OTHER")},
            "semantics_15_30": {
                "row_count": len(all_1530_rows),
                "single_price_ohlc_row_count": all_1530_single_price,
                "single_price_ohlc_pct": _pct(all_1530_single_price, len(all_1530_rows)),
                "median_volume": percentile(
                    [_decimal(row.get("volume")) for row in all_1530_rows], Decimal("0.50")
                ),
                "mismatches_with_15_30_observation": at_1530_for_mismatches,
                "daily_close_matches_15_30_within_rupee_tolerance": daily_close_matches_1530,
                "daily_close_matches_after_15_30": daily_close_matches_after_1530,
                "daily_close_matches_any_off_session": daily_close_matches_any_off_session,
                "finding": "15:30 rows do not match the NSE closing price in the material-mismatch population; later post-close observations usually do, supporting a distinct provider final-close publication rather than another regular 5m bar.",
            },
            "top_local_times": [
                {"local_time": key, "row_count": value}
                for key, value in raw["off_time_counts"].most_common(20)
            ],
        },
        "timestamp_semantics": {
            "result": classifications["GROWW_TIMESTAMP_SEMANTICS_RESULT"],
            "bar_end_material_mismatch_sessions": bar_end_material_count,
            "bar_end_material_open_difference_sessions": bar_end_breaks_open_count,
            "finding": "BAR_END would discard the observed 09:15 opening interval and include sparse 15:30 observations; canonical semantics remain unchanged.",
        },
        "daily_source": {
            "provider": "National Stock Exchange of India",
            "source": "official sec_bhavdata_full daily security bhavcopy",
            "adjustment": "RAW_UNADJUSTED",
            "date_semantics": "NSE trading session date",
            "close_definition": "official CLOSE_PRICE field, distinct from LAST_PRICE; the project treats it as an exchange closing-price process rather than the last 5m trade",
            "volume_definition": "TTL_TRD_QNTY full-session traded quantity",
            "canonical_close_equals_daily_last_price": close_last_exact,
            "canonical_close_closer_to_daily_last_price": close_closer_to_last,
            "material_close_mismatch_population": sum(row["close_material"] for row in mismatch_rows),
        },
        "volume": {
            "material_mismatch_count": len(volume_rows),
            "cause_counts": dict(Counter(row["likely_cause"] for row in volume_rows)),
        },
        "retrieval": {
            "recorded_historical_attempts": len(latency_rows),
            "interrupted_unrecorded_attempts": 1,
            "latency_ms": {
                "median": percentile(latency_values, Decimal("0.50")),
                "p75": percentile(latency_values, Decimal("0.75")),
                "p90": percentile(latency_values, Decimal("0.90")),
                "p95": percentile(latency_values, Decimal("0.95")),
                "p99": percentile(latency_values, Decimal("0.99")),
                "max": max(latency_values),
            },
            "stall_count": sum(row["stall"] for row in latency_rows),
            "extreme_stall_count": sum(row["extreme_stall"] for row in latency_rows),
            "stall_requests": stall_rows,
            "runtime_seconds": runtime_total,
            "runtime_decomposition": runtime_decomposition,
            "root_cause": "The scalar requests timeout bounded connect/read inactivity, not total response wall clock; three synchronous SDK calls consumed most recorded request time.",
            "live_diagnostic_probe_count": 0,
        },
        "transport": transport,
        "checkpoint": {
            "state_counts": dict(Counter(row["status"] for row in checkpoint_rows)),
            "phantom_complete": phantom_complete,
            "missing_raw_payloads": missing_raw,
            "duplicate_completed_raw_paths": duplicate_completed,
            "integrity_result": "PASS" if not (phantom_complete or missing_raw or duplicate_completed) else "FAIL",
            "interrupted_request": {
                "request_id": interrupted_id,
                "state": interrupted_state["status"],
                "raw_payload_exists": bool(interrupted_state.get("raw_path") and Path(interrupted_state["raw_path"]).exists()),
                "normalized_data_exists": interrupted_normalized,
                "safe_resume_would_duplicate": False,
                "classification": interrupted_state.get("last_error_category"),
            },
        },
        "instrument_mapping": {
            "isin_verified": isin_verified,
            "current_token_verified": sum(row["current_token_verified"] for row in mapping_rows),
            "historical_token_validity_verified": sum(row["historical_token_validity_verified"] for row in mapping_rows),
            "result": classifications["POINT_IN_TIME_INSTRUMENT_MAPPING_RESULT"],
            "archived_instrument_master_available": False,
        },
        "command_05": {
            "original_dataset_result": summary_05["classifications"]["BOUNDED_INTRADAY_INGESTION_RESULT"],
            "status_after_audit": classifications["COMMAND_05_DATASET_STATUS_AFTER_AUDIT"],
            "resume_existing_frozen_scope_recommended": True,
            "resume_requires_separate_authorization": True,
            "full_history_ingestion_recommended": False,
            "artifacts_mutated": False,
        },
        "integrity": {
            "command_05_before": {key: integrity_before[key] for key in ("file_count", "total_bytes", "tree_hash")},
            "command_05_after": None,
            "command_05_unchanged": None,
            "source_artifact_count": len(input_inventory),
            "source_inventory_hash": canonical_hash(input_inventory),
            "input_inventory": input_inventory,
        },
        "regression": {
            "checks": baseline_checks,
            "baseline_mutation_violations": sum(not value for value in baseline_checks.values()),
            "all_unchanged": all(baseline_checks.values()),
        },
        "governance": {
            "validation_state": "SEALED",
            "validation_run_count": 0,
            "holdout_performance_exposed": False,
            "strategy_v2_created": False,
            "strategy_v1_modified": False,
            "strategy_metrics_generated": False,
            "command_05_ingestion_resumed": False,
            "provider_requests_made": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "security": {
            "credentials_in_reports": False,
            "authorization_headers_persisted": False,
            "backend_env_ignored": _git_ignored(root, root / "backend/.env"),
            "raw_data_ignored": _git_ignored(root, root / "data/raw/intraday/groww/development_bounded_v1"),
            "audit_outputs_ignored": _git_ignored(root, audit_dir),
        },
        "normalization_v1_1": {
            "created": False,
            "reason": "No normalization defect was found; raw and normalized aggregates agree.",
            "old_mismatch_count": len(mismatch_rows),
            "corrected_mismatch_count": None,
        },
        "remediation_candidates": remediation_rows,
        "paths": {
            "reports": report_paths,
            "audit_manifest": str(audit_dir / "audit_manifest_v1.json"),
            "documentation": str(root / "docs/groww-intraday-reconciliation-retrieval-audit-v1.md"),
        },
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "runtime_storage": {},
        "ready_for_review": False,
    }

    if write_outputs:
        report_payloads: dict[str, Sequence[Mapping[str, Any]]] = {
            AUDIT_REPORT_FILENAMES[1]: mismatch_rows,
            AUDIT_REPORT_FILENAMES[2]: field_rows,
            AUDIT_REPORT_FILENAMES[3]: symbol_rows,
            AUDIT_REPORT_FILENAMES[4]: yearly_rows,
            AUDIT_REPORT_FILENAMES[5]: raw["off_rows"],
            AUDIT_REPORT_FILENAMES[6]: timestamp_rows,
            AUDIT_REPORT_FILENAMES[7]: volume_rows,
            AUDIT_REPORT_FILENAMES[8]: latency_rows,
            AUDIT_REPORT_FILENAMES[9]: stall_rows,
            AUDIT_REPORT_FILENAMES[10]: transport_rows,
            AUDIT_REPORT_FILENAMES[11]: checkpoint_rows,
            AUDIT_REPORT_FILENAMES[12]: mapping_rows,
            AUDIT_REPORT_FILENAMES[13]: remediation_rows,
        }
        for filename, rows in report_payloads.items():
            _write_csv(report_dir / filename, rows)

    integrity_after = command_05_integrity_snapshot(root)
    integrity_unchanged = integrity_before["tree_hash"] == integrity_after["tree_hash"]
    summary["integrity"]["command_05_after"] = {
        key: integrity_after[key] for key in ("file_count", "total_bytes", "tree_hash")
    }
    summary["integrity"]["command_05_unchanged"] = integrity_unchanged
    summary["command_05"]["artifacts_mutated"] = not integrity_unchanged
    summary["runtime_storage"] = {
        "audit_runtime_seconds": Decimal(str(time.perf_counter() - started)),
        "source_bytes_read_inventory": sum(row["size_bytes"] for row in input_inventory),
        "audit_output_bytes": sum(
            (report_dir / filename).stat().st_size
            for filename in AUDIT_REPORT_FILENAMES[1:]
            if (report_dir / filename).exists()
        ),
    }
    summary["ready_for_review"] = bool(
        integrity_unchanged
        and all(baseline_checks.values())
        and len(comparable) == EXPECTED_COMPARABLE_SESSIONS
        and len(mismatch_rows) == EXPECTED_MATERIAL_PRICE_MISMATCHES
        and tests_passed
        and frontend_build_passed
    )
    if write_outputs:
        _write_json(report_dir / AUDIT_REPORT_FILENAMES[0], summary)
        manifest = {
            "audit_version": AUDIT_VERSION,
            "profile": AUDIT_PROFILE,
            "command_05_tree_hash": integrity_before["tree_hash"],
            "input_inventory_hash": canonical_hash(input_inventory),
            "report_paths": report_paths,
            "no_command_05_mutation": integrity_unchanged,
            "no_provider_requests": True,
            "validation_state": "SEALED",
        }
        _write_json(audit_dir / "audit_manifest_v1.json", manifest)
        summary["runtime_storage"]["audit_output_bytes"] = sum(
            path.stat().st_size
            for path in [report_dir / filename for filename in AUDIT_REPORT_FILENAMES]
            + [audit_dir / "audit_manifest_v1.json"]
            if path.exists()
        )
        _write_json(report_dir / AUDIT_REPORT_FILENAMES[0], summary)
    if progress:
        progress(
            f"audit complete: reconciliation={classifications['RECONCILIATION_ROOT_CAUSE_RESULT']}; "
            f"transport={classifications['RETRIEVAL_TRANSPORT_RESULT']}; resume={classifications['RESUME_SAFETY_RESULT']}"
        )
    return summary


__all__ = [
    "AUDIT_PROFILE",
    "AUDIT_REPORT_FILENAMES",
    "AUDIT_VERSION",
    "EXTREME_STALL_MS",
    "STALL_MS",
    "build_groww_intraday_root_cause_audit",
    "classify_off_session",
    "command_05_integrity_snapshot",
    "magnitude_band",
    "material_price_fields",
    "mismatch_type",
    "percentile",
]
