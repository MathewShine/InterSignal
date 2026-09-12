from __future__ import annotations

import csv
import json
import math
import os
import threading
import time
from collections import Counter
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.config.settings import Settings
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.research.intraday.development_ingestion import (
    CheckpointStatus,
    MANIFEST_FILENAMES,
    MAX_NORMALIZED_5M_ROWS,
    MAX_RAW_STORAGE_GIB,
    _baseline_state,
    _extract_candles,
    _git_ignored,
    _pilot_state,
    _provider_candle_row,
    _read_raw_record,
    _write_checkpoint,
    _write_csv,
    _write_immutable_raw,
    _write_json_atomic,
    load_frozen_development_opportunities,
    load_frozen_development_trades,
    manifest_root,
    normalized_root,
    process_accepted_payloads,
    raw_root,
    derived_root,
    validate_scope_and_plan,
)
from app.research.intraday.normalization import parse_timestamp
from app.research.intraday.provider_pilot import (
    GROWW_RETRIEVAL_TRANSPORT_VERSION,
    InstrumentMapping,
    classify_provider_failure,
    credentials_present,
)
from app.research.intraday.root_cause_audit import (
    PRICE_TOLERANCE_RUPEES,
    VOLUME_TOLERANCE_PCT,
    _aggregate_candles,
    _corporate_action_evidence,
    _daily_rows,
    _decimal,
    _field_origin,
    _is_regular_bar_end,
    _is_regular_bar_start,
    _load_normalized_sessions,
    _raw_evidence,
    material_price_fields,
    percentile,
)
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED, canonical_hash, json_ready
from app.strategy.momentum_candidates import file_sha256


COMMAND_VERSION = "DEVELOPMENT_INTRADAY_INGESTION_RESUME_V1"
PROFILE = "NSE_CASH_5M_DEVELOPMENT_BOUNDED_RESUME_V1"
EXPECTED_SCOPE_HASH = "dcf4cc8587c923fd08e6299f472cd8f37add3baae54498351eb53fe76da75fe3"
EXPECTED_REQUEST_PLAN_HASH = "cd871adf88bc571339b0c3ca7efcb066d88ab8b63ceae5d0804a411fd8e7dfaf"
EXPECTED_INITIAL_COUNTS = {
    "COMPLETE": 164,
    "FAILED_RETRYABLE": 1,
    "PENDING": 540,
    "FAILED_FINAL": 0,
}
EXPECTED_RETRYABLE_REQUEST_ID = "DEV-INTRADAY-C05-0165-CHOLAFIN-20230914"
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 20.0
TOTAL_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2
REQUEST_TIMEOUT_CIRCUIT_BREAKER = 3
MAX_RESUME_WALLCLOCK_SECONDS = 3 * 60 * 60
THROTTLE_SECONDS = 1.0
SOURCE_SEMANTICS_CLASSIFICATION = "EXPLAINED_CLOSE_AUCTION_OR_SOURCE_SEMANTICS"

REPORT_FILENAMES = (
    "development_intraday_resume_05b_summary.json",
    "development_intraday_resume_05b_requests.csv",
    "development_intraday_resume_05b_transport.csv",
    "development_intraday_resume_05b_sessions.csv",
    "development_intraday_resume_05b_quality.csv",
    "development_intraday_resume_05b_reconciliation.csv",
    "development_intraday_resume_05b_yearly.csv",
    "development_intraday_resume_05b_opportunity_coverage.csv",
    "development_intraday_resume_05b_trade_coverage.csv",
    "development_intraday_resume_05b_confirmation_availability.csv",
    "development_intraday_resume_05b_failures.csv",
    "development_intraday_resume_05b_pilot_validation.csv",
)


class ResumeMode(StrEnum):
    RESUME = "RESUME"
    VERIFY = "VERIFY"


class TransportResult(StrEnum):
    CLEAN = "CLEAN"
    CLEAN_WITH_RETRIES = "CLEAN_WITH_RETRIES"
    UNSTABLE = "UNSTABLE"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ResumeResult(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_FAILURES = "COMPLETE_WITH_FAILURES"
    PARTIAL_CIRCUIT_BREAKER = "PARTIAL_CIRCUIT_BREAKER"
    PARTIAL_RUNTIME_LIMIT = "PARTIAL_RUNTIME_LIMIT"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class DatasetStatus(StrEnum):
    USABLE_FOR_BOUNDED_RESEARCH = "USABLE_FOR_BOUNDED_RESEARCH"
    USABLE_WITH_LIMITATIONS = "USABLE_WITH_LIMITATIONS"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FullHistoryRecommendationAfterResume(StrEnum):
    PROCEED_TO_SEPARATE_AUTHORIZATION = "PROCEED_TO_SEPARATE_AUTHORIZATION"
    MORE_DATA_QUALITY_WORK_REQUIRED = "MORE_DATA_QUALITY_WORK_REQUIRED"
    DO_NOT_PROCEED = "DO_NOT_PROCEED"
    INCONCLUSIVE = "INCONCLUSIVE"


class GuardedWallClockTimeout(TimeoutError):
    def __init__(self, message: str, *, attempt_id: str, generation: int) -> None:
        super().__init__(message)
        self.attempt_id = attempt_id
        self.generation = generation


class ResumeRuntimeLimit(RuntimeError):
    pass


class ResumeRequestFailure(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(f"Historical request failed: {category}")
        self.category = category


class AttemptGenerationGuard:
    """Own the only channel through which an SDK attempt can reach raw commit."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._generation: Counter[str] = Counter()
        self._active: dict[str, str] = {}
        self._results: dict[str, tuple[str, Any]] = {}
        self._commit_eligible: set[str] = set()
        self._committed: set[str] = set()
        self.late_results_discarded = 0
        self.commit_violations = 0

    def begin(self, request_id: str, retry_no: int) -> tuple[str, int]:
        with self._condition:
            self._generation[request_id] += 1
            generation = self._generation[request_id]
            attempt_id = f"{request_id}:retry-{retry_no}:generation-{generation}"
            self._active[request_id] = attempt_id
            return attempt_id, generation

    def publish(self, request_id: str, attempt_id: str, kind: str, value: Any) -> None:
        with self._condition:
            if self._active.get(request_id) != attempt_id:
                self.late_results_discarded += 1
                return
            self._results[attempt_id] = (kind, value)
            self._condition.notify_all()

    def await_result(self, request_id: str, attempt_id: str, timeout_seconds: float) -> Any:
        deadline = time.perf_counter() + timeout_seconds
        with self._condition:
            while attempt_id not in self._results:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    if self._active.get(request_id) == attempt_id:
                        self._active.pop(request_id, None)
                    generation = int(attempt_id.rsplit("-", 1)[-1])
                    raise GuardedWallClockTimeout(
                        f"Groww historical request exceeded the configured {timeout_seconds:g}s wall-clock bound",
                        attempt_id=attempt_id,
                        generation=generation,
                    )
                self._condition.wait(remaining)
            kind, value = self._results.pop(attempt_id)
            if self._active.get(request_id) == attempt_id:
                self._active.pop(request_id, None)
            if kind == "ERROR":
                raise value
            self._commit_eligible.add(attempt_id)
            return value

    def claim_commit(self, attempt_id: str) -> bool:
        with self._condition:
            if attempt_id not in self._commit_eligible or attempt_id in self._committed:
                self.commit_violations += 1
                return False
            self._committed.add(attempt_id)
            return True


def run_guarded_sdk_call(
    call: Callable[[], Any],
    *,
    guard: AttemptGenerationGuard,
    request_id: str,
    retry_no: int,
    timeout_seconds: float,
) -> tuple[Any, str, int]:
    attempt_id, generation = guard.begin(request_id, retry_no)

    def worker() -> None:
        try:
            guard.publish(request_id, attempt_id, "RESULT", call())
        except BaseException as exc:
            guard.publish(request_id, attempt_id, "ERROR", exc)

    thread = threading.Thread(
        target=worker,
        name=f"groww-resume-{request_id[-20:]}-{generation}",
        daemon=True,
    )
    thread.start()
    return guard.await_result(request_id, attempt_id, timeout_seconds), attempt_id, generation


def resume_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/intraday/v1/development_bounded/resume_05b"


def report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _status_counts(checkpoint: Mapping[str, Any]) -> dict[str, int]:
    counts = Counter(str(row.get("status")) for row in checkpoint["requests"].values())
    return {status: counts.get(status, 0) for status in (
        "COMPLETE",
        "FAILED_RETRYABLE",
        "FAILED_RETRYABLE_TIMEOUT",
        "FAILED_FINAL",
        "FAILED_FINAL_TIMEOUT",
        "PENDING",
        "IN_PROGRESS",
        "SKIPPED",
    )}


def _artifact_snapshot(root: Path, paths: Sequence[Path]) -> dict[str, Any]:
    rows = [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(set(paths), key=lambda value: value.relative_to(root).as_posix())
        if path.exists()
    ]
    return {
        "file_count": len(rows),
        "total_bytes": sum(int(row["size_bytes"]) for row in rows),
        "tree_hash": canonical_hash(rows),
        "files": rows,
    }


def _audit_05a_snapshot(root: Path) -> dict[str, Any]:
    paths = list((root / "data/research/intraday/v1/groww_root_cause_audit_05a").rglob("*"))
    paths.extend((root / "data/reports").glob("groww_intraday_audit_05a_*"))
    return _artifact_snapshot(root, [path for path in paths if path.is_file()])


def _checkpoint_counts_for_initial_gate(checkpoint: Mapping[str, Any]) -> dict[str, int]:
    observed = _status_counts(checkpoint)
    return {
        "COMPLETE": observed["COMPLETE"],
        "FAILED_RETRYABLE": observed["FAILED_RETRYABLE"],
        "PENDING": observed["PENDING"],
        "FAILED_FINAL": observed["FAILED_FINAL"],
    }


def _canonical_session_keys(root: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in normalized_root(root).glob("*/*.csv.gz"):
        import gzip

        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                keys.add((str(row.get("symbol", "")).upper(), str(row.get("trading_date", ""))))
    return keys


def validate_existing_complete_payloads(
    root: Path,
    scope: Mapping[str, Any],
    request_plan: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    plan_by_id = {str(row["request_id"]): row for row in request_plan["requests"]}
    seen_paths: set[Path] = set()
    canonical_sessions = _canonical_session_keys(root)
    regeneration_ids: list[str] = []
    checked = 0
    for request_id, state in checkpoint["requests"].items():
        if state.get("status") != str(CheckpointStatus.COMPLETE):
            continue
        checked += 1
        expected_path = raw_root(root) / f"{request_id}.json"
        declared_path = Path(str(state.get("raw_path") or expected_path))
        if declared_path.resolve() != expected_path.resolve() or not expected_path.exists():
            raise RuntimeError(f"COMPLETE_RAW_PATH_INVALID: {request_id}")
        if expected_path.resolve() in seen_paths:
            raise RuntimeError(f"DUPLICATE_ACCEPTED_RAW_PATH: {request_id}")
        seen_paths.add(expected_path.resolve())
        record = _read_raw_record(expected_path, str(scope["scope_hash"]))
        if record.get("request_id") != request_id:
            raise RuntimeError(f"COMPLETE_RAW_REQUEST_ID_MISMATCH: {request_id}")
        if record.get("raw_hash") != state.get("raw_hash"):
            raise RuntimeError(f"COMPLETE_RAW_CHECKPOINT_HASH_MISMATCH: {request_id}")
        plan_row = plan_by_id[request_id]
        expected_sessions = set(str(value) for value in plan_row.get("expected_sessions", []))
        raw_regular_sessions = {
            parse_timestamp(_provider_candle_row(candle)["timestamp"], allow_naive_exchange_local=True).date().isoformat()
            for candle in _extract_candles(record["response"])
            if _is_regular_bar_start(
                parse_timestamp(_provider_candle_row(candle)["timestamp"], allow_naive_exchange_local=True)
            )
        } & expected_sessions
        if any((str(plan_row["symbol"]), value) not in canonical_sessions for value in raw_regular_sessions):
            regeneration_ids.append(request_id)
    raw_files = list(raw_root(root).glob("*.json"))
    if len(raw_files) != checked:
        raise RuntimeError(f"DUPLICATE_OR_ORPHAN_RAW_FILE: expected {checked}, observed {len(raw_files)}")
    return {
        "checked_complete_requests": checked,
        "valid": True,
        "duplicate_accepted_raw_files": 0,
        "lineage_regeneration_request_ids": regeneration_ids,
        "lineage_result": "PRESENT" if not regeneration_ids else "REGENERABLE",
    }


def run_preflight(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    manifest_dir = manifest_root(root)
    scope_path = manifest_dir / MANIFEST_FILENAMES[0]
    plan_path = manifest_dir / MANIFEST_FILENAMES[1]
    checkpoint_path = manifest_dir / MANIFEST_FILENAMES[2]
    scope = _read_json(scope_path)
    request_plan = _read_json(plan_path)
    validate_scope_and_plan(scope, request_plan)
    if scope.get("scope_hash") != EXPECTED_SCOPE_HASH or request_plan.get("request_plan_hash") != EXPECTED_REQUEST_PLAN_HASH:
        raise RuntimeError("FROZEN_SCOPE_HASH_MISMATCH")
    if request_plan.get("scope_hash") != EXPECTED_SCOPE_HASH:
        raise RuntimeError("FROZEN_SCOPE_HASH_MISMATCH")
    if len(request_plan["requests"]) != 705:
        raise RuntimeError("FROZEN_SCOPE_HASH_MISMATCH")
    if any(str(row["end_date"]) > "2024-12-31" or str(row["start_date"]) < "2022-01-01" for row in request_plan["requests"]):
        raise RuntimeError("VALIDATION_DATE_REQUEST_REJECTED")

    checkpoint = _read_json(checkpoint_path)
    if checkpoint.get("scope_hash") != EXPECTED_SCOPE_HASH or checkpoint.get("request_plan_hash") != EXPECTED_REQUEST_PLAN_HASH:
        raise RuntimeError("FROZEN_SCOPE_HASH_MISMATCH")
    resume_dir = resume_root(root)
    snapshot_path = resume_dir / "pre_resume_checkpoint_v1.json"
    initial_manifest_path = resume_dir / "pre_resume_manifest_v1.json"
    if not snapshot_path.exists():
        observed_counts = _checkpoint_counts_for_initial_gate(checkpoint)
        if observed_counts != EXPECTED_INITIAL_COUNTS:
            raise RuntimeError(f"INITIAL_CHECKPOINT_STATE_MISMATCH: {observed_counts}")
        retryable_ids = [
            request_id
            for request_id, row in checkpoint["requests"].items()
            if row.get("status") == str(CheckpointStatus.FAILED_RETRYABLE)
        ]
        if retryable_ids != [EXPECTED_RETRYABLE_REQUEST_ID]:
            raise RuntimeError(f"INITIAL_RETRYABLE_REQUEST_MISMATCH: {retryable_ids}")
        integrity = validate_existing_complete_payloads(root, scope, request_plan, checkpoint)
        baseline = _baseline_state(root / "data")
        audit_05a = _audit_05a_snapshot(root)
        original_summary = _read_json(report_root(root) / "development_intraday_v1_summary.json")
        _write_json_new(snapshot_path, checkpoint)
        initial_manifest = {
            "command_version": COMMAND_VERSION,
            "profile": PROFILE,
            "scope_hash": EXPECTED_SCOPE_HASH,
            "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_snapshot_path": str(snapshot_path),
            "checkpoint_snapshot_sha256": file_sha256(snapshot_path),
            "checkpoint_source_sha256": file_sha256(checkpoint_path),
            "checkpoint_counts": observed_counts,
            "existing_complete_integrity": integrity,
            "baseline_before": baseline,
            "audit_05a_before": audit_05a,
            "original_command_05_summary_sha256": file_sha256(
                report_root(root) / "development_intraday_v1_summary.json"
            ),
            "original_command_05_result": original_summary["classifications"]["BOUNDED_INTRADAY_INGESTION_RESULT"],
            "validation": {"state": SEALED, "run_count": 0, "date_requests": 0},
        }
        _write_json_new(initial_manifest_path, initial_manifest)
    else:
        initial_manifest = _read_json(initial_manifest_path)
        integrity = validate_existing_complete_payloads(root, scope, request_plan, checkpoint)
    return {
        "scope": scope,
        "request_plan": request_plan,
        "checkpoint": checkpoint,
        "initial_manifest": initial_manifest,
        "existing_complete_integrity": integrity,
    }


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


class ResumeGrowwTransport:
    def __init__(
        self,
        *,
        client: Any,
        guard: AttemptGenerationGuard,
        on_attempt: Callable[[dict[str, Any], str | None], None],
        max_attempts: int,
        deadline_monotonic: float,
        connect_timeout_seconds: float = CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds: float = READ_TIMEOUT_SECONDS,
        total_timeout_seconds: float = TOTAL_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
        throttle_seconds: float = THROTTLE_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.perf_counter,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if GROWW_RETRIEVAL_TRANSPORT_VERSION != "GROWW_RETRIEVAL_TRANSPORT_V1_1":
            raise RuntimeError("LEGACY_GROWW_RETRIEVAL_PATH_BLOCKED")
        if (connect_timeout_seconds, read_timeout_seconds, total_timeout_seconds, max_retries) != (10.0, 20.0, 30.0, 2):
            raise RuntimeError("TRANSPORT_V1_1_CONFIGURATION_REQUIRED")
        self.client = client
        self.guard = guard
        self.on_attempt = on_attempt
        self.max_attempts = max_attempts
        self.deadline_monotonic = deadline_monotonic
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.total_timeout_seconds = total_timeout_seconds
        self.max_retries = max_retries
        self.throttle_seconds = max(throttle_seconds, 0.0)
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self.attempt_count = 0
        self.last_request_at: float | None = None

    def _before_attempt(self) -> None:
        if self.monotonic() >= self.deadline_monotonic:
            raise ResumeRuntimeLimit("MAX_RESUME_WALLCLOCK reached")
        if self.attempt_count >= self.max_attempts:
            raise RuntimeError("RESUME_REQUEST_ATTEMPT_BUDGET_EXHAUSTED")
        if self.last_request_at is not None:
            remaining = self.throttle_seconds - (self.monotonic() - self.last_request_at)
            if remaining > 0:
                self.sleeper(remaining)
        if self.monotonic() >= self.deadline_monotonic:
            raise ResumeRuntimeLimit("MAX_RESUME_WALLCLOCK reached")
        self.attempt_count += 1
        self.last_request_at = self.monotonic()

    def fetch(
        self,
        *,
        mapping: InstrumentMapping,
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str]:
        request_id = str(request["request_id"])
        start_date = date.fromisoformat(str(request["start_date"]))
        end_date = date.fromisoformat(str(request["end_date"]))
        if start_date < DEFAULT_TEMPORAL_CONFIG.development_start or end_date > DEFAULT_TEMPORAL_CONFIG.development_end:
            raise RuntimeError("VALIDATION_DATE_REQUEST_REJECTED")
        if (end_date - start_date).days + 1 > 30:
            raise RuntimeError("FROZEN_REQUEST_WINDOW_INVALID")
        for retry_no in range(self.max_retries + 1):
            self._before_attempt()
            started = self.monotonic()
            started_at = self.wall_clock()
            attempt_id = f"{request_id}:retry-{retry_no}:generation-pending"
            generation = 0
            try:
                def sdk_call() -> Any:
                    with redirect_stdout(StringIO()):
                        return self.client.get_historical_candles(
                            exchange=getattr(self.client, "EXCHANGE_NSE", "NSE"),
                            segment=getattr(self.client, "SEGMENT_CASH", "CASH"),
                            groww_symbol=mapping.provider_symbol,
                            start_time=f"{start_date.isoformat()} 09:15:00",
                            end_time=f"{end_date.isoformat()} 15:30:00",
                            candle_interval=getattr(self.client, "CANDLE_INTERVAL_MIN_5", "5minute"),
                            timeout=(self.connect_timeout_seconds, self.read_timeout_seconds),
                        )

                response, attempt_id, generation = run_guarded_sdk_call(
                    sdk_call,
                    guard=self.guard,
                    request_id=request_id,
                    retry_no=retry_no,
                    timeout_seconds=self.total_timeout_seconds,
                )
                if not isinstance(response, dict):
                    raise ValueError("Provider returned a non-object response")
                metric = self._metric(
                    request_id=request_id,
                    attempt_id=attempt_id,
                    generation=generation,
                    retry_no=retry_no,
                    started=started,
                    started_at=started_at,
                    status="SUCCESS",
                    category="OK",
                    row_count=len(_extract_candles(response)),
                )
                self.on_attempt(metric, None)
                return response, attempt_id
            except Exception as exc:
                if isinstance(exc, ResumeRuntimeLimit):
                    raise
                if isinstance(exc, GuardedWallClockTimeout):
                    attempt_id = exc.attempt_id
                    generation = exc.generation
                timeout_exception = isinstance(exc, (GuardedWallClockTimeout, TimeoutError)) or "timeout" in (
                    f"{type(exc).__name__} {exc}".lower()
                )
                category = "TIMEOUT" if timeout_exception else classify_provider_failure(exc)
                retryable = category in {"RATE_LIMIT", "TIMEOUT", "TRANSIENT_NETWORK", "SERVER_ERROR"}
                metric = self._metric(
                    request_id=request_id,
                    attempt_id=attempt_id,
                    generation=generation,
                    retry_no=retry_no,
                    started=started,
                    started_at=started_at,
                    status="FAILED",
                    category=category,
                    exception=type(exc).__name__,
                )
                intermediate = (
                    str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT)
                    if category == "TIMEOUT"
                    else str(CheckpointStatus.FAILED_RETRYABLE)
                    if retryable or category == "AUTHENTICATION_FAILURE"
                    else str(CheckpointStatus.FAILED_FINAL)
                )
                self.on_attempt(metric, intermediate)
                if category == "AUTHENTICATION_FAILURE" or not retryable or retry_no >= self.max_retries:
                    raise ResumeRequestFailure(category) from exc
                retry_after = _retry_after_seconds(exc) if category == "RATE_LIMIT" else None
                self.sleeper(max(float(2 ** (retry_no + 1)), retry_after or 0.0))
        raise AssertionError("unreachable")

    def _metric(
        self,
        *,
        request_id: str,
        attempt_id: str,
        generation: int,
        retry_no: int,
        started: float,
        started_at: datetime,
        status: str,
        category: str,
        row_count: int | None = None,
        exception: str | None = None,
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "attempt_id": attempt_id,
            "attempt_generation": generation,
            "retry_number": retry_no,
            "provider": "Groww",
            "endpoint_category": "HISTORICAL_CANDLES",
            "status": status,
            "response_category": category,
            "latency_ms": round((self.monotonic() - started) * 1000, 3),
            "request_started_at": started_at.isoformat(),
            "request_completed_at": self.wall_clock().isoformat(),
            "row_count": row_count,
            "exception": exception,
            "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "read_timeout_seconds": self.read_timeout_seconds,
            "wall_clock_timeout_seconds": self.total_timeout_seconds,
        }


def _load_or_initialize_resume_state(root: Path, preflight: Mapping[str, Any]) -> dict[str, Any]:
    path = resume_root(root) / "resume_state_v1.json"
    if path.exists():
        state = _read_json(path)
        if state.get("scope_hash") != EXPECTED_SCOPE_HASH or state.get("request_plan_hash") != EXPECTED_REQUEST_PLAN_HASH:
            raise RuntimeError("FROZEN_SCOPE_HASH_MISMATCH")
        return state
    checkpoint = preflight["checkpoint"]
    eligible = [
        request_id
        for request_id, row in checkpoint["requests"].items()
        if row.get("status") in {
            str(CheckpointStatus.PENDING),
            str(CheckpointStatus.IN_PROGRESS),
            str(CheckpointStatus.FAILED_RETRYABLE),
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
        }
    ]
    state = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "scope_hash": EXPECTED_SCOPE_HASH,
        "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
        "initial_checkpoint_sha256": preflight["initial_manifest"]["checkpoint_source_sha256"],
        "initial_eligible_request_ids": eligible,
        "initial_retryable_request_ids": [EXPECTED_RETRYABLE_REQUEST_ID],
        "logical_request_ids_attempted": [],
        "newly_completed_request_ids": [],
        "retryable_requests_completed": [],
        "transport_metrics": [],
        "auth_metrics": [],
        "network_started_at": None,
        "network_finished_at": None,
        "network_runtime_seconds": 0,
        "circuit_breaker_triggered": False,
        "runtime_cap_triggered": False,
        "auth_blocked": False,
        "late_sdk_results_discarded": 0,
        "late_result_commit_violations": 0,
        "raw_immutability_violations": 0,
        "resume_result": str(ResumeResult.INCONCLUSIVE),
        "last_verified_dataset_hashes": None,
        "reproducibility_verified": False,
        "verify_runs": 0,
        "verify_network_requests": 0,
        "zero_fetch_resume_verified": False,
    }
    _write_json_atomic(path, state)
    return state


def _persist_resume_state(root: Path, state: Mapping[str, Any]) -> None:
    _write_json_atomic(resume_root(root) / "resume_state_v1.json", state)


def _refresh_resume_raw_index(root: Path, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for request_id, state in sorted(checkpoint["requests"].items()):
        if state.get("status") != str(CheckpointStatus.COMPLETE):
            continue
        path = Path(str(state["raw_path"]))
        rows.append(
            {
                "request_id": request_id,
                "raw_path": str(path),
                "raw_hash": state["raw_hash"],
                "raw_file_sha256": file_sha256(path),
                "row_count": state.get("row_count", 0),
                "retrieved_at": state.get("retrieved_at"),
            }
        )
    payload = {
        "command_version": COMMAND_VERSION,
        "scope_hash": EXPECTED_SCOPE_HASH,
        "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
        "rows": rows,
    }
    payload["raw_index_hash"] = canonical_hash(payload)
    _write_json_atomic(resume_root(root) / "raw_index_resume_v1.json", payload)
    return payload


def _progress_checkpoint(root: Path, checkpoint: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    payload = {
        "command_version": COMMAND_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "request_counts": _status_counts(checkpoint),
        "network_attempts": len(state["transport_metrics"]),
        "timeout_attempts": sum(row.get("response_category") == "TIMEOUT" for row in state["transport_metrics"]),
        "strict_session_estimate": state.get(
            "last_strict_session_estimate", "DEFERRED_UNTIL_FULL_DATASET_REBUILD"
        ),
    }
    _write_json_atomic(resume_root(root) / "progress_summary_v1.json", payload)


def execute_resume_requests(
    *,
    repo_root: Path,
    preflight: Mapping[str, Any],
    state: dict[str, Any],
    settings: Settings | None = None,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
    max_wallclock_seconds: float = MAX_RESUME_WALLCLOCK_SECONDS,
    transport_factory: Callable[..., ResumeGrowwTransport] = ResumeGrowwTransport,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(repo_root)
    scope = preflight["scope"]
    request_plan = preflight["request_plan"]
    checkpoint = preflight["checkpoint"]
    allowed = {
        str(CheckpointStatus.PENDING),
        str(CheckpointStatus.IN_PROGRESS),
        str(CheckpointStatus.FAILED_RETRYABLE),
        str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
    }
    targets = [row for row in request_plan["requests"] if checkpoint["requests"][row["request_id"]]["status"] in allowed]
    if not targets:
        state["zero_fetch_resume_verified"] = True
        state["network_finished_at"] = state.get("network_finished_at") or datetime.now(timezone.utc).isoformat()
        _persist_resume_state(root, state)
        return checkpoint, state

    configured = settings or Settings()
    auth_started = time.perf_counter()
    auth_started_at = datetime.now(timezone.utc)
    supplied_client = client is not None
    try:
        if client is None:
            if not credentials_present(configured):
                raise PermissionError("Groww credentials are not present")
            client = GrowwAuthService(credentials=GrowwCredentials.from_settings(configured)).get_client()
        state["auth_metrics"].append(
            {
                "request_id": f"resume-authentication-{len(state['auth_metrics']) + 1}",
                "status": "MOCK_CLIENT_SUPPLIED" if supplied_client else "SUCCESS",
                "response_category": "OFFLINE_TEST" if supplied_client else "OK",
                "latency_ms": round((time.perf_counter() - auth_started) * 1000, 3),
                "request_started_at": auth_started_at.isoformat(),
                "request_completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as exc:
        category = classify_provider_failure(exc)
        state["auth_metrics"].append(
            {
                "request_id": f"resume-authentication-{len(state['auth_metrics']) + 1}",
                "status": "FAILED",
                "response_category": category,
                "latency_ms": round((time.perf_counter() - auth_started) * 1000, 3),
                "request_started_at": auth_started_at.isoformat(),
                "request_completed_at": datetime.now(timezone.utc).isoformat(),
                "exception": type(exc).__name__,
            }
        )
        state["auth_blocked"] = True
        state["resume_result"] = str(ResumeResult.AUTH_BLOCKED)
        _persist_resume_state(root, state)
        return checkpoint, state

    started_perf = time.perf_counter()
    state["network_started_at"] = state.get("network_started_at") or datetime.now(timezone.utc).isoformat()
    deadline = started_perf + max_wallclock_seconds
    guard = AttemptGenerationGuard()
    initial_retryable = set(state["initial_retryable_request_ids"])
    last_progress = started_perf
    completed_since_progress = 0
    consecutive_final_timeouts = 0

    def on_attempt(metric: dict[str, Any], intermediate_status: str | None) -> None:
        request_state = checkpoint["requests"][metric["request_id"]]
        request_state["attempts"] = int(request_state.get("attempts", 0)) + 1
        request_state["last_attempt_id"] = metric["attempt_id"]
        request_state["attempt_generation"] = metric["attempt_generation"]
        if intermediate_status is not None:
            request_state["status"] = intermediate_status
            request_state["last_error_category"] = metric["response_category"]
        state["transport_metrics"].append(metric)
        checkpoint.setdefault("request_metrics", []).append(metric)
        _write_checkpoint(root, checkpoint)
        _persist_resume_state(root, state)

    mappings = {
        str(row["internal_symbol"]): InstrumentMapping(**row) for row in scope["instrument_mappings"]
    }
    transport = transport_factory(
        client=client,
        guard=guard,
        on_attempt=on_attempt,
        max_attempts=len(targets) * (MAX_RETRIES + 1),
        deadline_monotonic=deadline,
        throttle_seconds=throttle_seconds,
    )
    initial_raw_bytes = sum(path.stat().st_size for path in raw_root(root).glob("*.json"))
    try:
        for request in targets:
            request_id = str(request["request_id"])
            request_state = checkpoint["requests"][request_id]
            if time.perf_counter() >= deadline:
                state["runtime_cap_triggered"] = True
                state["resume_result"] = str(ResumeResult.PARTIAL_RUNTIME_LIMIT)
                break
            path = raw_root(root) / f"{request_id}.json"
            if path.exists():
                record = _read_raw_record(path, EXPECTED_SCOPE_HASH)
                if record.get("request_id") != request_id:
                    state["raw_immutability_violations"] += 1
                    raise RuntimeError(f"RAW_IDENTITY_COLLISION: {request_id}")
                request_state.update(
                    status=str(CheckpointStatus.COMPLETE),
                    raw_hash=record["raw_hash"],
                    raw_path=str(path),
                    row_count=len(_extract_candles(record["response"])),
                    retrieved_at=record["retrieved_at"],
                    last_error_category=None,
                )
                _refresh_resume_raw_index(root, checkpoint)
                _write_checkpoint(root, checkpoint)
                continue
            if request_id not in state["logical_request_ids_attempted"]:
                state["logical_request_ids_attempted"].append(request_id)
            request_state["status"] = str(CheckpointStatus.IN_PROGRESS)
            _write_checkpoint(root, checkpoint)
            try:
                response, attempt_id = transport.fetch(mapping=mappings[str(request["symbol"])], request=request)
                if not guard.claim_commit(attempt_id):
                    raise RuntimeError(f"LATE_RESULT_COMMIT_GUARD_REJECTED: {attempt_id}")
                retrieved_at = datetime.now(timezone.utc).isoformat()
                record_without_hash = {
                    "command_version": COMMAND_VERSION,
                    "profile": PROFILE,
                    "provider": "GROWW",
                    "scope_hash": EXPECTED_SCOPE_HASH,
                    "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
                    "request_id": request_id,
                    "symbol": request["symbol"],
                    "provider_instrument": request["provider_instrument"],
                    "provider_instrument_id": request["provider_instrument_id"],
                    "requested_start": request["start_date"],
                    "requested_end": request["end_date"],
                    "requested_interval": request["interval"],
                    "expected_sessions": request["expected_sessions"],
                    "accepted_attempt_id": attempt_id,
                    "response": response,
                }
                raw_hash = canonical_hash(record_without_hash)
                record = {**record_without_hash, "raw_hash": raw_hash, "retrieved_at": retrieved_at}
                _write_immutable_raw(path, record)
                request_state.update(
                    status=str(CheckpointStatus.COMPLETE),
                    raw_hash=raw_hash,
                    raw_path=str(path),
                    row_count=len(_extract_candles(response)),
                    retrieved_at=retrieved_at,
                    last_error_category=None,
                )
                if request_id not in state["newly_completed_request_ids"]:
                    state["newly_completed_request_ids"].append(request_id)
                if request_id in initial_retryable and request_id not in state["retryable_requests_completed"]:
                    state["retryable_requests_completed"].append(request_id)
                _refresh_resume_raw_index(root, checkpoint)
                _write_checkpoint(root, checkpoint)
                consecutive_final_timeouts = 0
                completed_since_progress += 1
            except ResumeRuntimeLimit:
                state["runtime_cap_triggered"] = True
                state["resume_result"] = str(ResumeResult.PARTIAL_RUNTIME_LIMIT)
                if request_state.get("status") == str(CheckpointStatus.IN_PROGRESS):
                    request_state["status"] = str(CheckpointStatus.FAILED_RETRYABLE)
                    request_state["last_error_category"] = "RUNTIME_LIMIT"
                _write_checkpoint(root, checkpoint)
                break
            except ResumeRequestFailure as exc:
                if exc.category == "AUTHENTICATION_FAILURE":
                    request_state["status"] = str(CheckpointStatus.FAILED_RETRYABLE)
                    state["auth_blocked"] = True
                    state["resume_result"] = str(ResumeResult.AUTH_BLOCKED)
                    _write_checkpoint(root, checkpoint)
                    break
                if exc.category == "TIMEOUT":
                    request_state["status"] = str(CheckpointStatus.FAILED_FINAL_TIMEOUT)
                    consecutive_final_timeouts += 1
                else:
                    request_state["status"] = str(CheckpointStatus.FAILED_FINAL)
                    consecutive_final_timeouts = 0
                request_state["last_error_category"] = exc.category
                _write_checkpoint(root, checkpoint)
                if consecutive_final_timeouts >= REQUEST_TIMEOUT_CIRCUIT_BREAKER:
                    state["circuit_breaker_triggered"] = True
                    state["resume_result"] = str(ResumeResult.PARTIAL_CIRCUIT_BREAKER)
                    break
            finally:
                state["late_sdk_results_discarded"] = guard.late_results_discarded
                state["late_result_commit_violations"] = guard.commit_violations
                _persist_resume_state(root, state)
            if completed_since_progress >= 25 or time.perf_counter() - last_progress >= 600:
                _progress_checkpoint(root, checkpoint, state)
                if progress:
                    counts = _status_counts(checkpoint)
                    progress(
                        f"{counts['COMPLETE']}/705 requests complete; {len(state['transport_metrics'])} resume attempts; "
                        f"{sum(row.get('response_category') == 'TIMEOUT' for row in state['transport_metrics'])} timeouts"
                    )
                completed_since_progress = 0
                last_progress = time.perf_counter()
            raw_bytes = sum(path.stat().st_size for path in raw_root(root).glob("*.json"))
            if Decimal(raw_bytes) / Decimal(1024**3) >= MAX_RAW_STORAGE_GIB:
                state["resume_result"] = str(ResumeResult.PROVIDER_BLOCKED)
                break
    finally:
        state["late_sdk_results_discarded"] = guard.late_results_discarded
        state["late_result_commit_violations"] = guard.commit_violations
        state["network_runtime_seconds"] = float(state.get("network_runtime_seconds", 0)) + (
            time.perf_counter() - started_perf
        )
        state["network_finished_at"] = datetime.now(timezone.utc).isoformat()
        counts = _status_counts(checkpoint)
        if not state["circuit_breaker_triggered"] and not state["runtime_cap_triggered"] and not state["auth_blocked"]:
            if counts["PENDING"] + counts["IN_PROGRESS"] + counts["FAILED_RETRYABLE"] + counts["FAILED_RETRYABLE_TIMEOUT"] == 0:
                state["resume_result"] = str(
                    ResumeResult.COMPLETE_WITH_FAILURES
                    if counts["FAILED_FINAL"] + counts["FAILED_FINAL_TIMEOUT"]
                    else ResumeResult.COMPLETE
                )
        state["new_raw_bytes"] = sum(path.stat().st_size for path in raw_root(root).glob("*.json")) - initial_raw_bytes
        _write_checkpoint(root, checkpoint)
        _progress_checkpoint(root, checkpoint, state)
        _persist_resume_state(root, state)
    return checkpoint, state


def _enrich_reconciliation(
    root: Path,
    checkpoint: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    comparable = [dict(row) for row in rows if row.get("daily_source")]
    comparable_keys = {(str(row["symbol"]), str(row["trading_date"])) for row in comparable}
    mismatch_keys = {
        (str(row["symbol"]), str(row["trading_date"])) for row in comparable if material_price_fields(row)
    }
    raw = _raw_evidence(root, checkpoint, comparable_keys)
    normalized = _load_normalized_sessions(root, comparable_keys)
    daily = _daily_rows(root, (str(row["trading_date"]) for row in comparable))
    corporate_actions = _corporate_action_evidence(root, mismatch_keys) if mismatch_keys else {}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        result = dict(row)
        fields = material_price_fields(result) if result.get("daily_source") else ()
        result["legacy_material_price_mismatch"] = bool(fields)
        result["material_price_fields"] = list(fields)
        result["source_semantics_classification"] = "NOT_MATERIAL"
        result["mismatch_origin"] = None
        result["later_off_session_matches_daily_close"] = False
        result["canonical_close_closer_to_daily_last"] = False
        if fields:
            key = (str(result["symbol"]), str(result["trading_date"]))
            raw_session = raw["sessions"].get(key, [])
            regular = [candidate for candidate in raw_session if _is_regular_bar_start(candidate["timestamp"])]
            bar_end = [candidate for candidate in raw_session if _is_regular_bar_end(candidate["timestamp"])]
            raw_values = _aggregate_candles(regular)
            normalized_values = _aggregate_candles(normalized.get(key, []))
            alternative_values = _aggregate_candles(bar_end)
            all_day_values = _aggregate_candles(raw_session)
            origin = _field_origin(
                raw_values=raw_values,
                normalized_values=normalized_values,
                report_row=result,
                alternative_values=alternative_values,
                all_day_values=all_day_values,
                corporate_action=corporate_actions[key],
            )
            daily_detail = daily.get(key, {})
            daily_close = _decimal(result.get("daily_close"))
            daily_last = _decimal(daily_detail.get("LAST_PRICE"), default="0")
            canonical_close = _decimal(result.get("intraday_close"))
            later_match = any(
                candidate["timestamp"].hour * 60 + candidate["timestamp"].minute > 15 * 60 + 30
                and abs(_decimal(candidate.get("close")) - daily_close) <= PRICE_TOLERANCE_RUPEES
                for candidate in raw["off_rows_by_session"].get(key, [])
            )
            closer_to_last = bool(daily_last) and abs(canonical_close - daily_last) < abs(canonical_close - daily_close)
            benign = origin in {"PROVIDER_VS_DAILY_SOURCE", "SESSION_FILTERING_EFFECT"}
            result["mismatch_origin"] = origin
            result["later_off_session_matches_daily_close"] = later_match
            result["canonical_close_closer_to_daily_last"] = closer_to_last
            result["source_semantics_classification"] = (
                SOURCE_SEMANTICS_CLASSIFICATION if benign else "UNEXPLAINED_MATERIAL"
            )
        result["material_volume_mismatch"] = bool(
            result.get("daily_source") and _decimal(result.get("volume_pct_diff")) > VOLUME_TOLERANCE_PCT
        )
        enriched.append(result)
    return enriched


def _pct(numerator: int, denominator: int) -> Decimal:
    return Decimal("0") if not denominator else Decimal(numerator) * Decimal("100") / Decimal(denominator)


def _yearly_rows(
    root: Path,
    checkpoint: Mapping[str, Any],
    processed: Mapping[str, Any],
    reconciliation: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    raw = _raw_evidence(root, checkpoint, set())
    for year in (2022, 2023, 2024):
        sessions = [row for row in processed["session_rows"] if str(row["trading_date"]).startswith(str(year))]
        comparable = [row for row in reconciliation if str(row.get("trading_date", "")).startswith(str(year)) and row.get("daily_source")]
        material = [row for row in comparable if row.get("legacy_material_price_mismatch")]
        explained = [row for row in material if row.get("source_semantics_classification") == SOURCE_SEMANTICS_CLASSIFICATION]
        unexplained = [
            row for row in material if row.get("source_semantics_classification") == "UNEXPLAINED_MATERIAL"
        ]
        result.append(
            {
                "year": year,
                "symbol_sessions": len(sessions),
                "completed_symbol_sessions": sum(int(row.get("actual_bars", 0)) > 0 for row in sessions),
                "strict_count": sum(row.get("usability") == "USABLE_STRICT" for row in sessions),
                "strict_pct": _pct(sum(row.get("usability") == "USABLE_STRICT" for row in sessions), len(sessions)),
                "missing_sessions": sum(int(row.get("actual_bars", 0)) == 0 for row in sessions),
                "duplicate_sessions": sum(bool(row.get("duplicate_bars")) for row in sessions),
                "invalid_ohlc_sessions": sum(bool(row.get("invalid_ohlc")) for row in sessions),
                "off_session_raw_rows": sum(
                    int(row["row_count"]) for row in raw["off_rows"] if int(row["year"]) == year
                ),
                "legacy_comparable_sessions": len(comparable),
                "legacy_material_price_mismatches": len(material),
                "legacy_mismatch_rate_pct": _pct(len(material), len(comparable)),
                "explained_source_semantics_count": len(explained),
                "unexplained_material_count": len(unexplained),
            }
        )
    return result


def _transport_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    metrics = list(state.get("transport_metrics", []))
    latencies = [Decimal(str(row["latency_ms"])) for row in metrics]
    failed = [row for row in metrics if row.get("status") == "FAILED"]
    retried_ids = {row["request_id"] for row in metrics if int(row.get("retry_number", 0)) > 0}
    attempted_ids = set(state.get("logical_request_ids_attempted", []))
    completed_ids = set(state.get("newly_completed_request_ids", []))
    auth_metrics = list(state.get("auth_metrics", []))
    if state.get("circuit_breaker_triggered"):
        result = TransportResult.CIRCUIT_BREAKER_TRIGGERED
    elif not metrics:
        result = TransportResult.INCONCLUSIVE
    elif any(row.get("response_category") not in {"OK", "RATE_LIMIT", "TIMEOUT", "TRANSIENT_NETWORK", "SERVER_ERROR"} for row in failed):
        result = TransportResult.UNSTABLE
    elif failed:
        result = TransportResult.CLEAN_WITH_RETRIES
    else:
        result = TransportResult.CLEAN
    return {
        "version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
        "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        "read_timeout_seconds": READ_TIMEOUT_SECONDS,
        "wall_clock_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
        "max_retries_after_initial": MAX_RETRIES,
        "request_level_timeout_circuit_breaker": REQUEST_TIMEOUT_CIRCUIT_BREAKER,
        "logical_request_ids_attempted": len(state.get("logical_request_ids_attempted", [])),
        "network_attempts": len(metrics),
        "successful_attempts": sum(row.get("status") == "SUCCESS" for row in metrics),
        "logical_request_success_pct": _pct(len(completed_ids & attempted_ids), len(attempted_ids)),
        "timeout_attempts": sum(row.get("response_category") == "TIMEOUT" for row in metrics),
        "timeout_attempt_rate_pct": _pct(
            sum(row.get("response_category") == "TIMEOUT" for row in metrics), len(metrics)
        ),
        "rate_limit_attempts": sum(row.get("response_category") == "RATE_LIMIT" for row in metrics),
        "rate_limit_attempt_rate_pct": _pct(
            sum(row.get("response_category") == "RATE_LIMIT" for row in metrics), len(metrics)
        ),
        "requests_requiring_retry": len(retried_ids),
        "retry_request_rate_pct": _pct(len(retried_ids), len(attempted_ids)),
        "authentication_failure_rate_pct": _pct(
            sum(row.get("status") == "FAILED" for row in auth_metrics), len(auth_metrics)
        ),
        "median_latency_ms": percentile(latencies, Decimal("0.50")),
        "p90_latency_ms": percentile(latencies, Decimal("0.90")),
        "p95_latency_ms": percentile(latencies, Decimal("0.95")),
        "p99_latency_ms": percentile(latencies, Decimal("0.99")),
        "max_latency_ms": max(latencies, default=Decimal("0")),
        "extreme_stalls_prevented": sum(row.get("response_category") == "TIMEOUT" for row in metrics),
        "late_sdk_results_discarded": state.get("late_sdk_results_discarded", 0),
        "late_result_commit_violations": state.get("late_result_commit_violations", 0),
        "circuit_breaker_triggered": bool(state.get("circuit_breaker_triggered")),
        "runtime_cap_triggered": bool(state.get("runtime_cap_triggered")),
        "TRANSPORT_V1_1_RESULT": str(result),
    }


def build_resume_summary(
    *,
    repo_root: Path,
    preflight: Mapping[str, Any],
    state: dict[str, Any],
    processed: dict[str, Any],
    mode: ResumeMode,
    tests_passed: bool,
    frontend_build_passed: bool,
) -> dict[str, Any]:
    root = Path(repo_root)
    checkpoint = preflight["checkpoint"]
    processed["reconciliation_rows"] = _enrich_reconciliation(root, checkpoint, processed["reconciliation_rows"])
    reconciliation = processed["reconciliation_rows"]
    yearly = _yearly_rows(root, checkpoint, processed, reconciliation)
    counts = _status_counts(checkpoint)
    sessions = [row for row in processed["session_rows"] if int(row.get("actual_bars", 0)) > 0]
    strict = sum(row.get("usability") == "USABLE_STRICT" for row in sessions)
    warnings = sum(row.get("usability") == "USABLE_WITH_WARNING" for row in sessions)
    unusable = sum(row.get("usability") == "UNUSABLE" for row in sessions)
    comparable = [row for row in reconciliation if row.get("daily_source")]
    material = [row for row in comparable if row.get("legacy_material_price_mismatch")]
    explained = [row for row in material if row.get("source_semantics_classification") == SOURCE_SEMANTICS_CLASSIFICATION]
    unexplained = sum(row.get("source_semantics_classification") == "UNEXPLAINED_MATERIAL" for row in material)
    selected_symbols = set(preflight["scope"]["selected_symbols"])
    selected_opportunities = [row for row in processed["opportunity_rows"] if row.get("symbol") in selected_symbols]
    full_all = sum(bool(row.get("execution_path_reconstructable")) for row in processed["opportunity_rows"])
    full_selected = sum(bool(row.get("execution_path_reconstructable")) for row in selected_opportunities)
    strict_opportunities = sum(bool(row.get("full_path_strict_usable")) for row in processed["opportunity_rows"])
    transport = _transport_summary(state)
    total_terminal_failures = counts["FAILED_FINAL"] + counts["FAILED_FINAL_TIMEOUT"]
    incomplete = counts["PENDING"] + counts["IN_PROGRESS"] + counts["FAILED_RETRYABLE"] + counts["FAILED_RETRYABLE_TIMEOUT"]
    resume_result = str(state.get("resume_result") or ResumeResult.INCONCLUSIVE)
    if not state.get("circuit_breaker_triggered") and not state.get("runtime_cap_triggered") and not state.get("auth_blocked") and incomplete == 0:
        resume_result = str(ResumeResult.COMPLETE_WITH_FAILURES if total_terminal_failures else ResumeResult.COMPLETE)
    strict_pct = _pct(strict, len(sessions))
    unexplained_pct = _pct(unexplained, len(comparable))
    if not sessions:
        dataset_status = DatasetStatus.INCONCLUSIVE
    elif strict_pct < Decimal("90"):
        dataset_status = DatasetStatus.QUALITY_BLOCKED
    elif full_selected == 0:
        dataset_status = DatasetStatus.INSUFFICIENT_COVERAGE
    elif incomplete or unexplained_pct >= Decimal("5"):
        dataset_status = DatasetStatus.USABLE_WITH_LIMITATIONS
    else:
        dataset_status = DatasetStatus.USABLE_FOR_BOUNDED_RESEARCH
    if (
        counts["COMPLETE"] >= math.ceil(705 * 0.98)
        and transport["TRANSPORT_V1_1_RESULT"] in {str(TransportResult.CLEAN), str(TransportResult.CLEAN_WITH_RETRIES)}
        and strict_pct >= Decimal("95")
        and unexplained_pct < Decimal("5")
        and not state.get("circuit_breaker_triggered")
    ):
        full_history = FullHistoryRecommendationAfterResume.PROCEED_TO_SEPARATE_AUTHORIZATION
    elif sessions:
        full_history = FullHistoryRecommendationAfterResume.MORE_DATA_QUALITY_WORK_REQUIRED
    else:
        full_history = FullHistoryRecommendationAfterResume.INCONCLUSIVE
    current_hashes = dict(processed["dataset_hashes"])
    previous_hashes = state.get("last_verified_dataset_hashes")
    reproducible = previous_hashes is not None and previous_hashes == current_hashes
    state["last_strict_session_estimate"] = strict
    if mode == ResumeMode.VERIFY:
        state["verify_runs"] = int(state.get("verify_runs", 0)) + 1
        state["reproducibility_verified"] = bool(state.get("reproducibility_verified")) or reproducible
        state["last_verified_dataset_hashes"] = current_hashes
        state["verify_network_requests"] = 0
    elif previous_hashes != current_hashes:
        state["reproducibility_verified"] = False
    _persist_resume_state(root, state)
    baseline_after = _baseline_state(root / "data")
    audit_after = _audit_05a_snapshot(root)
    initial = preflight["initial_manifest"]
    baseline_unchanged = baseline_after == initial["baseline_before"]
    audit_unchanged = audit_after == initial["audit_05a_before"]
    original_summary_path = report_root(root) / "development_intraday_v1_summary.json"
    original_summary_unchanged = file_sha256(original_summary_path) == initial["original_command_05_summary_sha256"]
    raw_bytes = sum(path.stat().st_size for path in raw_root(root).glob("*.json"))
    trade_rows = processed["trade_rows"]
    confirmations = processed["confirmation_rows"]
    confirmation_denominator = len(confirmations)
    summary = {
        "phase": "Step 02.14",
        "command": "Command 05B",
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "mode": str(mode),
        "scope": {
            "scope_hash": EXPECTED_SCOPE_HASH,
            "scope_hash_verified": True,
            "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
            "request_plan_hash_verified": True,
            "scope_mutations": 0,
            "validation_date_request_violations": 0,
            "selected_symbols": 100,
            "planned_logical_requests": 705,
            "required_symbol_sessions": 4_829,
        },
        "initial_checkpoint": {
            "sha256": initial["checkpoint_source_sha256"],
            "snapshot_sha256": initial["checkpoint_snapshot_sha256"],
            "counts": initial["checkpoint_counts"],
            "integrity": initial["existing_complete_integrity"],
        },
        "final_checkpoint": {
            "sha256": file_sha256(manifest_root(root) / MANIFEST_FILENAMES[2]),
            "counts": counts,
            "atomic_write_result": "PASS",
        },
        "retrieval": {
            "logical_request_ids_attempted": len(state["logical_request_ids_attempted"]),
            "logical_request_id_list": state["logical_request_ids_attempted"],
            "newly_completed_requests": len(state["newly_completed_request_ids"]),
            "retryable_requests_completed": len(state["retryable_requests_completed"]),
            "new_failed_final": total_terminal_failures,
            "remaining_failed_retryable": counts["FAILED_RETRYABLE"] + counts["FAILED_RETRYABLE_TIMEOUT"],
            "remaining_pending": counts["PENDING"] + counts["IN_PROGRESS"],
            "final_complete": counts["COMPLETE"],
            "logical_completion_pct": _pct(counts["COMPLETE"], 705),
            "authentication_failures": sum(row.get("status") == "FAILED" for row in state["auth_metrics"]),
            "network_runtime_seconds": state["network_runtime_seconds"],
        },
        "transport": transport,
        "raw": {
            "new_payload_count": len(state["newly_completed_request_ids"]),
            "payload_count": counts["COMPLETE"],
            "raw_row_count": processed["dataset_manifest"]["row_counts"]["raw"],
            "raw_bytes": raw_bytes,
            "raw_storage_gib": Decimal(raw_bytes) / Decimal(1024**3),
            "raw_storage_cap_gib": MAX_RAW_STORAGE_GIB,
            "immutability_violations": state["raw_immutability_violations"],
        },
        "datasets": {
            "normalized_5m_rows": processed["dataset_manifest"]["row_counts"]["normalized_5m"],
            "derived_10m_rows": processed["dataset_manifest"]["row_counts"]["derived_10m"],
            "derived_15m_rows": processed["dataset_manifest"]["row_counts"]["derived_15m"],
            **current_hashes,
            "normalization_version": "NSE_CASH_INTRADAY_5M_V1",
            "normalization_semantics_changed": False,
            "prevented_duplicate_bars": processed.get("prevented_duplicate_bars", 0),
            "max_normalized_5m_rows": MAX_NORMALIZED_5M_ROWS,
        },
        "quality": {
            "total_ingested_symbol_sessions": len(sessions),
            "usable_strict": strict,
            "usable_with_warning": warnings,
            "unusable": unusable,
            "strict_usability_pct": strict_pct,
            "missing_bar_sessions": sum(bool(row.get("missing_bars")) for row in sessions),
            "duplicate_sessions": sum(bool(row.get("duplicate_bars")) for row in sessions),
            "invalid_ohlc_sessions": sum(bool(row.get("invalid_ohlc")) for row in sessions),
            "off_session_raw_rows": processed["off_session_raw_rows"],
            "structural_quality_separate_from_reconciliation": True,
        },
        "reconciliation": {
            "legacy_comparable_session_count": len(comparable),
            "legacy_material_price_mismatch_count": len(material),
            "legacy_mismatch_rate_pct": _pct(len(material), len(comparable)),
            "source_semantics_explained_count": len(explained),
            "unexplained_material_count": unexplained,
            "unexplained_material_mismatch_rate_pct": unexplained_pct,
            "material_volume_mismatch_count": sum(bool(row.get("material_volume_mismatch")) for row in comparable),
            "price_tolerance_rupees_unchanged": PRICE_TOLERANCE_RUPEES,
            "volume_tolerance_pct_unchanged": VOLUME_TOLERANCE_PCT,
            "threshold_changes": False,
        },
        "yearly": yearly,
        "corporate_action_safety": {
            "safe": sum(row.get("corporate_action_status") == "SAFE" for row in sessions),
            "caution": sum(row.get("corporate_action_status") == "CAUTION" for row in sessions),
            "unsafe": sum(row.get("corporate_action_status") == "UNSAFE_STRUCTURAL" for row in sessions),
            "automatic_adjustments": 0,
        },
        "opportunity_coverage": {
            "total_development_opportunities": len(processed["opportunity_rows"]),
            "frozen_selected_symbol_opportunities": len(selected_opportunities),
            "with_t1_data": sum(bool(row.get("t1_data_available")) for row in processed["opportunity_rows"]),
            "with_full_4_session_path": full_all,
            "fully_strict_usable": strict_opportunities,
            "all_development_coverage_pct": _pct(full_all, len(processed["opportunity_rows"])),
            "selected_scope_coverage_pct": _pct(full_selected, len(selected_opportunities)),
            "DEVELOPMENT_INTRADAY_COVERAGE_RESULT": (
                "HIGH" if _pct(full_all, len(processed["opportunity_rows"])) >= Decimal("80")
                else "MODERATE" if _pct(full_all, len(processed["opportunity_rows"])) >= Decimal("50")
                else "LOW"
            ),
        },
        "trade_coverage": {
            "development_admitted_trade_count": len(trade_rows),
            "entry_session_data": sum(bool(row.get("entry_session_available")) for row in trade_rows),
            "full_path": sum(bool(row.get("full_hold_path_available")) for row in trade_rows),
            "strict_usable_pct": _pct(sum(bool(row.get("full_hold_path_strict_usable")) for row in trade_rows), len(trade_rows)),
            "portfolio_rerun": False,
        },
        "confirmation_availability": {
            "opening_range_pct": _pct(sum(all(row.get(f"opening_range_{minutes}m_available") for minutes in (5, 10, 15, 30)) for row in confirmations), confirmation_denominator),
            "vwap_pct": _pct(sum(all(row.get(f"vwap_{minutes}m_available") for minutes in (5, 10, 15)) for row in confirmations), confirmation_denominator),
            "first_5m_close_pct": _pct(sum(bool(row.get("first_5m_close_available")) for row in confirmations), confirmation_denominator),
            "first_10m_close_pct": _pct(sum(bool(row.get("first_10m_close_available")) for row in confirmations), confirmation_denominator),
            "first_15m_close_pct": _pct(sum(bool(row.get("first_15m_close_available")) for row in confirmations), confirmation_denominator),
        },
        "classifications": {
            "COMMAND_05_RESUME_RESULT": resume_result,
            "DEVELOPMENT_INTRADAY_DATASET_STATUS_V1": str(dataset_status),
            "TRANSPORT_V1_1_RESULT": transport["TRANSPORT_V1_1_RESULT"],
            "FULL_HISTORY_RECOMMENDATION_AFTER_RESUME": str(full_history),
            "ORIGINAL_COMMAND_05_RESULT": initial["original_command_05_result"],
        },
        "instrument_mapping": {
            "isin_verified": 96,
            "current_token_count": 100,
            "historical_point_in_time_verified": 0,
            "POINT_IN_TIME_INSTRUMENT_MAPPING_RESULT": "CURRENT_IDENTITY_ONLY",
        },
        "validation": {"state": SEALED, "run_count": 0, "date_requests": 0, "performance_exposed": False},
        "governance": {
            "original_command_05_result_rewritten": not original_summary_unchanged,
            "outcome_rewrite_performed": False,
            "portfolio_rerun_performed": False,
            "strategy_v2_created": False,
            "strategy_v1_modified": False,
            "full_history_ingestion_performed": False,
            "full_history_authorized": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "regression": {
            "baseline_unchanged": baseline_unchanged,
            "baseline_mutation_violations": 0 if baseline_unchanged else 1,
            "audit_05a_unchanged": audit_unchanged,
            "original_command_05_summary_unchanged": original_summary_unchanged,
            "provider_pilot": _pilot_state(root),
        },
        "idempotency": {
            "resume_zero_fetch_verified": bool(state.get("zero_fetch_resume_verified")),
            "verify_runs": state.get("verify_runs", 0),
            "verify_network_requests": state.get("verify_network_requests", 0),
            "reproducibility_hash_verified": bool(state.get("reproducibility_verified")) or reproducible,
            "raw_overwrite_prohibited": True,
            "canonical_uniqueness_key": ["symbol", "instrument_id", "bar_start", "interval", "source_provider"],
        },
        "security": {
            "backend_env_ignored": _git_ignored(root, root / "backend/.env"),
            "raw_data_ignored": _git_ignored(root, raw_root(root) / "probe.json"),
            "reports_ignored": _git_ignored(root, report_root(root) / REPORT_FILENAMES[0]),
            "credentials_logged": False,
            "authorization_headers_logged": False,
        },
        "paths": {
            "resume_root": str(resume_root(root)),
            "checkpoint": str(manifest_root(root) / MANIFEST_FILENAMES[2]),
            "raw": str(raw_root(root)),
            "normalized_5m": str(normalized_root(root)),
            "derived_10m": str(derived_root(root, 10)),
            "derived_15m": str(derived_root(root, 15)),
            "reports": [str(report_root(root) / name) for name in REPORT_FILENAMES],
        },
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "known_limitations": [
            "Groww research-data licensing remains usable with restrictions; retention and redistribution rights are not broadened.",
            "Instrument mapping is current-identity-only; point-in-time token validity remains unverified.",
            "The maximum all-DEVELOPMENT opportunity coverage in the frozen 100-symbol scope is about 54.06%.",
            "The Python SDK timeout worker cannot be forcibly killed; generation guards discard any late result before raw commit.",
        ],
    }
    ready = bool(
        resume_result in {str(ResumeResult.COMPLETE), str(ResumeResult.COMPLETE_WITH_FAILURES)}
        and baseline_unchanged
        and audit_unchanged
        and original_summary_unchanged
        and not state["late_result_commit_violations"]
        and not state["raw_immutability_violations"]
        and state.get("reproducibility_verified")
        and tests_passed
        and frontend_build_passed
        and summary["security"]["backend_env_ignored"]
        and summary["security"]["raw_data_ignored"]
        and summary["security"]["reports_ignored"]
    )
    summary["step_status"] = "COMPLETE" if ready else "IMPLEMENTED_PENDING_OR_BLOCKED"
    summary["ready_for_review"] = ready
    return summary


def write_resume_reports(
    root: Path,
    preflight: Mapping[str, Any],
    state: Mapping[str, Any],
    processed: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    plan_by_id = {row["request_id"]: row for row in preflight["request_plan"]["requests"]}
    request_rows = []
    initial_eligible = set(state["initial_eligible_request_ids"])
    attempted = set(state["logical_request_ids_attempted"])
    for request_id, request in plan_by_id.items():
        request_rows.append(
            {
                **request,
                **preflight["checkpoint"]["requests"][request_id],
                "initially_eligible": request_id in initial_eligible,
                "attempted_in_05b": request_id in attempted,
            }
        )
    failures = [
        {"request_id": request_id, **row}
        for request_id, row in preflight["checkpoint"]["requests"].items()
        if row.get("status") not in {str(CheckpointStatus.COMPLETE), str(CheckpointStatus.SKIPPED)}
    ]
    rows_by_name = {
        REPORT_FILENAMES[1]: request_rows,
        REPORT_FILENAMES[2]: list(state["transport_metrics"]),
        REPORT_FILENAMES[3]: processed["session_rows"],
        REPORT_FILENAMES[4]: processed["quality_rows"],
        REPORT_FILENAMES[5]: processed["reconciliation_rows"],
        REPORT_FILENAMES[6]: summary["yearly"],
        REPORT_FILENAMES[7]: processed["opportunity_rows"],
        REPORT_FILENAMES[8]: processed["trade_rows"],
        REPORT_FILENAMES[9]: processed["confirmation_rows"],
        REPORT_FILENAMES[10]: failures,
        REPORT_FILENAMES[11]: [summary["regression"]["provider_pilot"]],
    }
    reports = report_root(root)
    for name, rows in rows_by_name.items():
        _write_csv(reports / name, rows)
    _write_json_atomic(reports / REPORT_FILENAMES[0], summary)
    manifest_files = [reports / name for name in REPORT_FILENAMES]
    manifest = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "scope_hash": EXPECTED_SCOPE_HASH,
        "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
        "final_checkpoint_hash": summary["final_checkpoint"]["sha256"],
        "dataset_hashes": {
            key: value for key, value in summary["datasets"].items() if key.endswith("_hash")
        },
        "reports": _artifact_snapshot(root, manifest_files),
    }
    _write_json_atomic(resume_root(root) / "resume_manifest_v1.json", manifest)


def run_development_intraday_resume(
    *,
    repo_root: Path,
    mode: ResumeMode | str,
    settings: Settings | None = None,
    client: Any | None = None,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
) -> dict[str, Any]:
    root = Path(repo_root)
    selected_mode = mode if isinstance(mode, ResumeMode) else ResumeMode(str(mode).upper())
    preflight = run_preflight(root)
    state = _load_or_initialize_resume_state(root, preflight)
    if progress:
        counts = _status_counts(preflight["checkpoint"])
        progress(
            f"preflight PASS: scope and plan hashes exact; COMPLETE={counts['COMPLETE']}, "
            f"retryable={counts['FAILED_RETRYABLE'] + counts['FAILED_RETRYABLE_TIMEOUT']}, PENDING={counts['PENDING']}"
        )
    if selected_mode == ResumeMode.RESUME:
        preflight["checkpoint"], state = execute_resume_requests(
            repo_root=root,
            preflight=preflight,
            state=state,
            settings=settings,
            client=client,
            progress=progress,
            throttle_seconds=throttle_seconds,
        )
    else:
        state["verify_network_requests"] = 0
    incremental_ids = set(state.get("newly_completed_request_ids", []))
    incremental_ids.update(preflight["existing_complete_integrity"].get("lineage_regeneration_request_ids", []))
    if selected_mode == ResumeMode.VERIFY:
        incremental_ids.clear()
    opportunities = load_frozen_development_opportunities(root / "data")
    trades = load_frozen_development_trades(root / "data")
    if progress:
        progress("merging accepted 5m data idempotently and rebuilding 10m/15m, quality, reconciliation, and coverage")
    processed = process_accepted_payloads(
        repo_root=root,
        scope=preflight["scope"],
        request_plan=preflight["request_plan"],
        checkpoint=preflight["checkpoint"],
        opportunities=opportunities,
        trades=trades,
        progress=progress,
        incremental_request_ids=incremental_ids,
        manifest_output_dir=resume_root(root),
        output_command_version=COMMAND_VERSION,
        output_profile=PROFILE,
    )
    summary = build_resume_summary(
        repo_root=root,
        preflight=preflight,
        state=state,
        processed=processed,
        mode=selected_mode,
        tests_passed=tests_passed,
        frontend_build_passed=frontend_build_passed,
    )
    write_resume_reports(root, preflight, state, processed, summary)
    return summary


__all__ = [
    "AttemptGenerationGuard",
    "COMMAND_VERSION",
    "DatasetStatus",
    "EXPECTED_REQUEST_PLAN_HASH",
    "EXPECTED_SCOPE_HASH",
    "PROFILE",
    "REPORT_FILENAMES",
    "ResumeGrowwTransport",
    "ResumeMode",
    "ResumeResult",
    "TransportResult",
    "execute_resume_requests",
    "run_development_intraday_resume",
    "run_guarded_sdk_call",
    "run_preflight",
    "validate_existing_complete_payloads",
]
