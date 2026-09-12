from __future__ import annotations

import inspect
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.research.intraday.development_ingestion import (
    CheckpointStatus,
    _read_raw_record,
    _write_checkpoint,
    _write_immutable_raw,
    initialize_checkpoint,
    manifest_root,
    raw_root,
)
from app.research.intraday.provider_pilot import InstrumentMapping
from app.research.intraday.resume_ingestion import (
    COMMAND_VERSION,
    CONNECT_TIMEOUT_SECONDS,
    EXPECTED_INITIAL_COUNTS,
    EXPECTED_REQUEST_PLAN_HASH,
    EXPECTED_RETRYABLE_REQUEST_ID,
    EXPECTED_SCOPE_HASH,
    MAX_RETRIES,
    MAX_RESUME_WALLCLOCK_SECONDS,
    PROFILE,
    READ_TIMEOUT_SECONDS,
    REPORT_FILENAMES,
    REQUEST_TIMEOUT_CIRCUIT_BREAKER,
    TOTAL_TIMEOUT_SECONDS,
    AttemptGenerationGuard,
    GuardedWallClockTimeout,
    ResumeGrowwTransport,
    ResumeMode,
    ResumeRequestFailure,
    ResumeResult,
    _status_counts,
    execute_resume_requests,
    run_guarded_sdk_call,
)
from app.research.temporal_validation.config import canonical_hash
from app.strategy.momentum_candidates import file_sha256


class FakeClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_MIN_5 = "5minute"

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict[str, object]] = []

    def get_historical_candles(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise ConnectionError("fixture network failure")
        return {"candles": [["2022-01-03T09:15:00", 100, 101, 99, 100.5, 1000]]}


def _mapping(symbol: str) -> dict[str, object]:
    return InstrumentMapping(
        symbol,
        "TESTISIN",
        f"NSE-{symbol}",
        "123",
        "NSE",
        "TEST",
        "UNKNOWN",
        "UNKNOWN",
        "ISIN_VERIFIED_CURRENT_TOKEN",
    ).snapshot()


def _request(index: int, symbol: str) -> dict[str, object]:
    return {
        "request_id": f"DEV-INTRADAY-C05-{index:04d}-{symbol}-20220103",
        "symbol": symbol,
        "provider_instrument": f"NSE-{symbol}",
        "provider_instrument_id": "123",
        "start_date": "2022-01-03",
        "end_date": "2022-01-03",
        "interval": "5m",
        "expected_sessions": ["2022-01-03"],
        "expected_rows": 75,
        "sequence_no": index,
    }


def _fixture_preflight(root: Path, count: int = 1) -> tuple[dict[str, object], dict[str, object]]:
    symbols = [f"S{index}" for index in range(1, count + 1)]
    requests = [_request(index, symbol) for index, symbol in enumerate(symbols, start=1)]
    scope = {
        "scope_hash": EXPECTED_SCOPE_HASH,
        "selected_symbols": symbols,
        "instrument_mappings": [_mapping(symbol) for symbol in symbols],
        "required_symbol_sessions": [
            {"symbol": symbol, "trading_date": "2022-01-03"} for symbol in symbols
        ],
    }
    request_plan = {
        "scope_hash": EXPECTED_SCOPE_HASH,
        "request_plan_hash": EXPECTED_REQUEST_PLAN_HASH,
        "requests": requests,
    }
    checkpoint = initialize_checkpoint(scope, request_plan)
    checkpoint["scope_hash"] = EXPECTED_SCOPE_HASH
    checkpoint["request_plan_hash"] = EXPECTED_REQUEST_PLAN_HASH
    _write_checkpoint(root, checkpoint)
    preflight = {
        "scope": scope,
        "request_plan": request_plan,
        "checkpoint": checkpoint,
        "initial_manifest": {
            "checkpoint_source_sha256": file_sha256(manifest_root(root) / "ingestion_checkpoint_v1.json")
        },
    }
    state = {
        "initial_eligible_request_ids": [row["request_id"] for row in requests],
        "initial_retryable_request_ids": [],
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
        "zero_fetch_resume_verified": False,
    }
    return preflight, state


def test_resume_contract_constants_are_frozen() -> None:
    assert COMMAND_VERSION == "DEVELOPMENT_INTRADAY_INGESTION_RESUME_V1"
    assert PROFILE == "NSE_CASH_5M_DEVELOPMENT_BOUNDED_RESUME_V1"
    assert EXPECTED_SCOPE_HASH == "dcf4cc8587c923fd08e6299f472cd8f37add3baae54498351eb53fe76da75fe3"
    assert EXPECTED_REQUEST_PLAN_HASH == "cd871adf88bc571339b0c3ca7efcb066d88ab8b63ceae5d0804a411fd8e7dfaf"
    assert EXPECTED_INITIAL_COUNTS == {"COMPLETE": 164, "FAILED_RETRYABLE": 1, "PENDING": 540, "FAILED_FINAL": 0}
    assert EXPECTED_RETRYABLE_REQUEST_ID.endswith("0165-CHOLAFIN-20230914")


def test_transport_v1_1_configuration_is_exact_and_legacy_values_are_blocked() -> None:
    assert (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS, TOTAL_TIMEOUT_SECONDS, MAX_RETRIES) == (10, 20, 30, 2)
    assert REQUEST_TIMEOUT_CIRCUIT_BREAKER == 3
    assert MAX_RESUME_WALLCLOCK_SECONDS == 10_800
    with pytest.raises(RuntimeError, match="CONFIGURATION_REQUIRED"):
        ResumeGrowwTransport(
            client=FakeClient(),
            guard=AttemptGenerationGuard(),
            on_attempt=lambda *_: None,
            max_attempts=3,
            deadline_monotonic=time.perf_counter() + 10,
            total_timeout_seconds=31,
        )


def test_guard_returns_current_result_and_allows_one_commit() -> None:
    guard = AttemptGenerationGuard()
    result, attempt_id, generation = run_guarded_sdk_call(
        lambda: {"candles": []},
        guard=guard,
        request_id="REQ",
        retry_no=0,
        timeout_seconds=0.5,
    )
    assert result == {"candles": []}
    assert generation == 1 and "generation-1" in attempt_id
    assert guard.claim_commit(attempt_id)
    assert not guard.claim_commit(attempt_id)
    assert guard.commit_violations == 1


def test_timeout_invalidates_attempt_and_discards_late_sdk_result() -> None:
    guard = AttemptGenerationGuard()
    release = threading.Event()
    with pytest.raises(GuardedWallClockTimeout) as caught:
        run_guarded_sdk_call(
            lambda: release.wait(1) or {"candles": []},
            guard=guard,
            request_id="REQ",
            retry_no=0,
            timeout_seconds=0.01,
        )
    release.set()
    for _ in range(50):
        if guard.late_results_discarded:
            break
        time.sleep(0.002)
    assert guard.late_results_discarded == 1
    assert not guard.claim_commit(caught.value.attempt_id)


def test_transport_retries_twice_and_forwards_connect_read_timeout() -> None:
    client = FakeClient(failures=2)
    metrics: list[dict[str, object]] = []
    transport = ResumeGrowwTransport(
        client=client,
        guard=AttemptGenerationGuard(),
        on_attempt=lambda row, _status: metrics.append(row),
        max_attempts=3,
        deadline_monotonic=time.perf_counter() + 10,
        throttle_seconds=0,
        sleeper=lambda _seconds: None,
    )
    response, _attempt_id = transport.fetch(
        mapping=InstrumentMapping(**_mapping("AAA")), request=_request(1, "AAA")
    )
    assert response["candles"] and len(client.calls) == 3
    assert [row["retry_number"] for row in metrics] == [0, 1, 2]
    assert all(call["timeout"] == (10, 20) for call in client.calls)


def test_transport_exhaustion_is_bounded_to_three_attempts() -> None:
    client = FakeClient(failures=5)
    transport = ResumeGrowwTransport(
        client=client,
        guard=AttemptGenerationGuard(),
        on_attempt=lambda *_: None,
        max_attempts=3,
        deadline_monotonic=time.perf_counter() + 10,
        throttle_seconds=0,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(ResumeRequestFailure) as caught:
        transport.fetch(mapping=InstrumentMapping(**_mapping("AAA")), request=_request(1, "AAA"))
    assert caught.value.category == "TRANSIENT_NETWORK"
    assert len(client.calls) == 3


def test_execute_resume_processes_only_eligible_and_second_resume_fetches_zero(tmp_path: Path) -> None:
    preflight, state = _fixture_preflight(tmp_path, 2)
    first_id, second_id = [row["request_id"] for row in preflight["request_plan"]["requests"]]
    preflight["checkpoint"]["requests"][first_id]["status"] = str(CheckpointStatus.SKIPPED)
    client = FakeClient()
    checkpoint, state = execute_resume_requests(
        repo_root=tmp_path,
        preflight=preflight,
        state=state,
        client=client,
        throttle_seconds=0,
    )
    assert len(client.calls) == 1
    assert checkpoint["requests"][first_id]["status"] == "SKIPPED"
    assert checkpoint["requests"][second_id]["status"] == "COMPLETE"
    first_hash = file_sha256(raw_root(tmp_path) / f"{second_id}.json")
    checkpoint, state = execute_resume_requests(
        repo_root=tmp_path,
        preflight={**preflight, "checkpoint": checkpoint},
        state=state,
        client=client,
        throttle_seconds=0,
    )
    assert len(client.calls) == 1
    assert file_sha256(raw_root(tmp_path) / f"{second_id}.json") == first_hash
    assert state["zero_fetch_resume_verified"]


def test_raw_payload_is_write_once_hash_checked_and_indexed_before_complete(tmp_path: Path) -> None:
    preflight, state = _fixture_preflight(tmp_path)
    checkpoint, _state = execute_resume_requests(
        repo_root=tmp_path,
        preflight=preflight,
        state=state,
        client=FakeClient(),
        throttle_seconds=0,
    )
    request_id = preflight["request_plan"]["requests"][0]["request_id"]
    path = raw_root(tmp_path) / f"{request_id}.json"
    record = _read_raw_record(path, EXPECTED_SCOPE_HASH)
    assert record["request_id"] == request_id
    assert checkpoint["requests"][request_id]["raw_hash"] == record["raw_hash"]
    index = json.loads((tmp_path / "data/research/intraday/v1/development_bounded/resume_05b/raw_index_resume_v1.json").read_text())
    assert index["rows"][0]["request_id"] == request_id
    with pytest.raises(FileExistsError):
        _write_immutable_raw(path, record)


class _TimeoutTransport:
    def __init__(self, **kwargs: object) -> None:
        self.guard = kwargs["guard"]
        self.on_attempt = kwargs["on_attempt"]
        self.calls = 0

    def fetch(self, *, request: dict[str, object], **_: object) -> tuple[dict[str, object], str]:
        self.calls += 1
        request_id = str(request["request_id"])
        attempt_id, generation = self.guard.begin(request_id, 2)
        self.on_attempt(
            {
                "request_id": request_id,
                "attempt_id": attempt_id,
                "attempt_generation": generation,
                "retry_number": 2,
                "status": "FAILED",
                "response_category": "TIMEOUT",
                "latency_ms": 30_000,
                "transport_version": "GROWW_RETRIEVAL_TRANSPORT_V1_1",
            },
            str(CheckpointStatus.FAILED_RETRYABLE_TIMEOUT),
        )
        raise ResumeRequestFailure("TIMEOUT")


def test_request_level_circuit_breaker_stops_after_three_final_timeouts(tmp_path: Path) -> None:
    preflight, state = _fixture_preflight(tmp_path, 5)
    checkpoint, state = execute_resume_requests(
        repo_root=tmp_path,
        preflight=preflight,
        state=state,
        client=FakeClient(),
        throttle_seconds=0,
        transport_factory=_TimeoutTransport,
    )
    counts = _status_counts(checkpoint)
    assert counts["FAILED_FINAL_TIMEOUT"] == 3
    assert counts["PENDING"] == 2
    assert state["circuit_breaker_triggered"]
    assert state["resume_result"] == "PARTIAL_CIRCUIT_BREAKER"


def test_resume_runtime_cap_stops_before_historical_fetch(tmp_path: Path) -> None:
    preflight, state = _fixture_preflight(tmp_path)
    client = FakeClient()
    checkpoint, state = execute_resume_requests(
        repo_root=tmp_path,
        preflight=preflight,
        state=state,
        client=client,
        throttle_seconds=0,
        max_wallclock_seconds=-1,
    )
    assert not client.calls
    assert _status_counts(checkpoint)["PENDING"] == 1
    assert state["runtime_cap_triggered"]
    assert state["resume_result"] == "PARTIAL_RUNTIME_LIMIT"


def test_checkpoint_atomic_write_leaves_valid_json(tmp_path: Path) -> None:
    preflight, _state = _fixture_preflight(tmp_path)
    checkpoint = preflight["checkpoint"]
    checkpoint["sentinel"] = "after"
    _write_checkpoint(tmp_path, checkpoint)
    observed = json.loads((manifest_root(tmp_path) / "ingestion_checkpoint_v1.json").read_text())
    assert observed["sentinel"] == "after"
    assert not list(manifest_root(tmp_path).glob("*.tmp"))


def test_reports_cover_every_required_machine_output() -> None:
    assert len(REPORT_FILENAMES) == 12
    assert REPORT_FILENAMES[0].endswith("summary.json")
    assert {"development_intraday_resume_05b_reconciliation.csv", "development_intraday_resume_05b_opportunity_coverage.csv", "development_intraday_resume_05b_pilot_validation.csv"} <= set(REPORT_FILENAMES)


def test_governance_source_has_no_strategy_portfolio_or_order_execution() -> None:
    from app.research.intraday import resume_ingestion

    source = Path(inspect.getsourcefile(resume_ingestion)).read_text(encoding="utf-8")
    assert "simulate_portfolio(" not in source
    assert "place_order(" not in source
    assert "StrategyV2" not in source
    assert "supabase.table" not in source
    assert "2025-" not in source and "2026-" not in source
    assert ResumeMode.VERIFY == "VERIFY"
