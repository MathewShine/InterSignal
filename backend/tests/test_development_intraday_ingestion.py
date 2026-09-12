from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.development_ingestion import (
    BoundedIngestionResult,
    CheckpointStatus,
    CoverageResult,
    DevelopmentDataQualityResult,
    DevelopmentProviderReliabilityResult,
    FullHistoryRecommendation,
    HardCaps,
    RunMode,
    _quality_classification,
    _write_gzip_csv_deterministic,
    build_opportunity_coverage,
    build_plan,
    build_trade_coverage,
    execute_requests,
    expand_required_sessions,
    freeze_plan,
    group_request_windows,
    hard_cap_checks,
    initialize_checkpoint,
    load_frozen_development_opportunities,
    load_frozen_development_trades,
    map_instruments,
    mapping_is_usable,
    opportunity_session_dates,
    rank_symbols,
    select_symbols,
    validate_scope_and_plan,
)
from app.research.intraday.models import IntradayBarQuality
from app.research.intraday.normalization import normalize_rows
from app.research.intraday.provider_pilot import InstrumentMapping, SessionUsability, _reconciliation_row
from app.research.intraday.quality import assess_session_quality
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED, canonical_hash
from app.strategy.momentum_candidates import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
MASTER_PATH = REPO_ROOT / "backend/.venv/Lib/site-packages/growwapi/instruments.csv"


class FakeClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_MIN_5 = "5minute"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def get_historical_candles(self, **_: object) -> dict[str, object]:
        self.calls += 1
        if self.fail:
            raise TimeoutError("fixture timeout")
        return {"candles": [["2022-01-03T09:15:00", 100, 101, 99, 100.5, 1000]]}


def _mapping(symbol: str = "AAA") -> InstrumentMapping:
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
    )


def _mini_scope_plan() -> tuple[dict[str, object], dict[str, object]]:
    request = {
        "request_id": "DEV-INTRADAY-C05-0001-AAA-20220103",
        "symbol": "AAA",
        "provider_instrument": "NSE-AAA",
        "provider_instrument_id": "123",
        "start_date": "2022-01-03",
        "end_date": "2022-01-03",
        "interval": "5m",
        "expected_sessions": ["2022-01-03"],
        "expected_rows": 75,
        "sequence_no": 1,
    }
    scope_body = {
        "selected_symbols": ["AAA"],
        "instrument_mappings": [_mapping().snapshot()],
        "required_symbol_sessions": [{"symbol": "AAA", "trading_date": "2022-01-03"}],
    }
    scope = {**scope_body, "scope_hash": canonical_hash(scope_body), "created_at": "FIXTURE"}
    plan_body = {
        "scope_hash": scope["scope_hash"],
        "requests": [request],
    }
    request_plan = {
        **plan_body,
        "request_plan_hash": canonical_hash(plan_body),
        "created_at": "FIXTURE",
    }
    return scope, request_plan


def _opportunity(symbol: str = "AAA", decision: str = "2022-01-03") -> dict[str, str]:
    return {
        "symbol": symbol,
        "isin": "TESTISIN",
        "decision_date": decision,
        "next_session_date": "2022-01-04",
        "session_date_1": "2022-01-04",
        "session_date_2": "2022-01-05",
        "session_date_3": "2022-01-06",
        "session_date_4": "2022-01-07",
        "source_score_band": "HIGH",
        "setup_quality": "STRONG",
        "candidate_category": "BOTH",
        "effective_reward_risk": "2",
        "same_bar_ambiguous": "False",
    }


def _session_bars() -> tuple[NseCashSessionCalendar, list[object]]:
    trading_date = date(2022, 1, 3)
    calendar = NseCashSessionCalendar.from_trading_dates([trading_date])
    start = datetime(2022, 1, 3, 9, 15, tzinfo=ASIA_KOLKATA)
    rows = [
        {
            "instrument_id": "123",
            "symbol": "AAA",
            "isin": "TESTISIN",
            "exchange": "NSE",
            "trading_date": trading_date,
            "interval": "5m",
            "bar_start": start + timedelta(minutes=index * 5),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": Decimal("100.5") + index,
            "volume": 1000 + index,
        }
        for index in range(75)
    ]
    return calendar, normalize_rows(
        rows,
        calendar=calendar,
        source_provider="FIXTURE",
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        allow_naive_exchange_local=True,
    )


def test_command_enums_and_governance_contract() -> None:
    assert [str(value) for value in RunMode] == ["PLAN_ONLY", "INGEST", "RESUME", "VERIFY", "REPLAY_FAILED"]
    assert set(str(value) for value in CheckpointStatus) == {
        "PENDING",
        "IN_PROGRESS",
        "COMPLETE",
        "FAILED_RETRYABLE",
        "FAILED_RETRYABLE_TIMEOUT",
        "FAILED_FINAL",
        "FAILED_FINAL_TIMEOUT",
        "SKIPPED",
    }
    assert SEALED == "SEALED"
    assert BoundedIngestionResult.PASS_WITH_LIMITATIONS == "PASS_WITH_LIMITATIONS"
    assert CoverageResult.MODERATE == "MODERATE"
    assert DevelopmentDataQualityResult.CLEAN == "CLEAN"
    assert DevelopmentProviderReliabilityResult.CLEAN == "CLEAN"
    assert FullHistoryRecommendation.MORE_PILOT_DATA_REQUIRED == "MORE_PILOT_DATA_REQUIRED"


def test_actual_frozen_development_source_and_trade_ledgers_are_loaded_not_rebuilt() -> None:
    opportunities = load_frozen_development_opportunities(DATA_DIR)
    trades = load_frozen_development_trades(DATA_DIR)
    assert len(opportunities) == 2_068
    assert len(trades) == 478
    assert min(row["decision_date"] for row in opportunities) >= "2022-01-01"
    assert max(row["decision_date"] for row in opportunities) <= "2024-12-31"


def test_development_only_session_guard_drops_validation_dates() -> None:
    row = _opportunity()
    row["session_date_4"] = "2025-01-02"
    values = opportunity_session_dates(row)
    assert date(2025, 1, 2) not in values
    assert date(2022, 1, 3) in values and date(2022, 1, 4) in values


def test_hard_caps_are_independent_and_enforced() -> None:
    baseline = dict(
        symbol_count=100,
        normalized_rows=5_000_000,
        request_count=5_000,
        raw_storage_gib=Decimal("2"),
        wallclock_hours=Decimal("3"),
    )
    assert all(hard_cap_checks(**baseline).values())
    mutations = {
        "symbol_count": 101,
        "normalized_rows": 5_000_001,
        "request_count": 5_001,
        "raw_storage_gib": Decimal("2.0001"),
        "wallclock_hours": Decimal("3.0001"),
    }
    for key, value in mutations.items():
        observed = hard_cap_checks(**(baseline | {key: value}))
        assert sum(not passed for passed in observed.values()) == 1


def test_non_performance_selection_and_deterministic_ranking() -> None:
    rows = [_opportunity("BBB"), _opportunity("AAA"), _opportunity("AAA")]
    rows[0]["same_bar_ambiguous"] = "True"
    trades = [{"symbol": "BBB"}]
    mappings = [_mapping("AAA"), _mapping("BBB")]
    first = rank_symbols(rows, trades, mappings)
    second = rank_symbols(list(reversed(rows)), trades, list(reversed(mappings)))
    assert first == second
    assert [row["symbol"] for row in first] == ["AAA", "BBB"]
    source = inspect.getsource(rank_symbols).lower()
    for forbidden in ("realized_r", "gross_pnl", "net_pnl", "exit_type", "win_rate", "cagr"):
        assert forbidden not in source
    assert all(row["selection_uses_performance_fields"] is False for row in first)


def test_symbol_selection_respects_target_cap_and_mapping() -> None:
    rankings = [
        {"symbol": f"S{index:03d}", "opportunity_count": 1, "mapping_available": index != 0}
        for index in range(150)
    ]
    selected = select_symbols(rankings, total_opportunities=150, target_pct=Decimal("80"), max_symbols=100)
    assert len(selected) == 100
    assert "S000" not in selected


def test_session_expansion_deduplication_and_request_windows() -> None:
    first = _opportunity("AAA")
    second = _opportunity("AAA", "2022-01-04")
    second.update(
        next_session_date="2022-01-05",
        session_date_1="2022-01-05",
        session_date_2="2022-02-10",
        session_date_3="2022-02-11",
        session_date_4="2022-02-14",
    )
    sessions = expand_required_sessions([first, second], ["AAA"])
    assert len(sessions["AAA"]) == len(set(sessions["AAA"]))
    requests = group_request_windows(sessions, {"AAA": _mapping()})
    assert len(requests) == 2
    assert all(
        (date.fromisoformat(row["end_date"]) - date.fromisoformat(row["start_date"])).days < 30
        for row in requests
    )
    assert sum(len(row["expected_sessions"]) for row in requests) == len(sessions["AAA"])


def test_exact_actual_plan_is_bounded_deterministic_and_non_performance() -> None:
    first = build_plan(repo_root=REPO_ROOT, instrument_master_path=MASTER_PATH)
    second = build_plan(repo_root=REPO_ROOT, instrument_master_path=MASTER_PATH)
    scope = first["scope"]
    assert scope["scope_hash"] == second["scope"]["scope_hash"]
    assert first["request_plan"]["request_plan_hash"] == second["request_plan"]["request_plan_hash"]
    assert len(scope["selected_symbols"]) == 100
    assert scope["selected_symbol_opportunities"] == 1_118
    assert len(scope["required_symbol_sessions"]) == 4_829
    assert scope["estimated_requests"] == 705
    assert scope["estimated_normalized_rows"] == 362_175
    assert scope["estimated_opportunity_coverage_pct"] < Decimal("80")
    assert all(scope["hard_cap_checks"].values())
    assert scope["performance_fields_used_in_selection"] is False
    assert all(date.fromisoformat(row["end_date"]) <= date(2024, 12, 31) for row in first["request_plan"]["requests"])


def test_instrument_mapping_requires_exact_symbol_and_flags_point_in_time_limit() -> None:
    master = [
        {
            "exchange": "NSE",
            "segment": "CASH",
            "instrument_type": "EQ",
            "trading_symbol": "AAA",
            "groww_symbol": "NSE-AAA",
            "exchange_token": "123",
            "isin": "TESTISIN",
        },
        {
            "exchange": "NSE",
            "segment": "CASH",
            "instrument_type": "EQ",
            "trading_symbol": "AAA-LIKE",
            "groww_symbol": "NSE-AAA-LIKE",
            "exchange_token": "999",
            "isin": "OTHER",
        },
    ]
    rows = map_instruments(["AAA", "MISSING"], {"AAA": "TESTISIN", "MISSING": None}, master)
    assert rows[0].provider_instrument_id == "123"
    assert rows[0].mapping_status == "ISIN_VERIFIED_CURRENT_TOKEN"
    assert mapping_is_usable(rows[0])
    assert rows[1].mapping_status == "UNRESOLVED" and not mapping_is_usable(rows[1])
    assert rows[0].valid_from == rows[0].valid_to == "UNKNOWN"


def test_scope_and_plan_hashes_detect_tampering_and_validation_window() -> None:
    scope, request_plan = _mini_scope_plan()
    validate_scope_and_plan(scope, request_plan)
    bad_scope = dict(scope)
    bad_scope["selected_symbols"] = ["TAMPERED"]
    with pytest.raises(ValueError, match="scope hash"):
        validate_scope_and_plan(bad_scope, request_plan)
    bad_plan = json.loads(json.dumps(request_plan))
    bad_plan["requests"][0]["end_date"] = "2025-01-01"
    body = {key: value for key, value in bad_plan.items() if key not in {"request_plan_hash", "created_at"}}
    bad_plan["request_plan_hash"] = canonical_hash(body)
    with pytest.raises(ValueError, match="validation-window"):
        validate_scope_and_plan(scope, bad_plan)


def test_scope_freeze_is_immutable(tmp_path: Path) -> None:
    scope, request_plan = _mini_scope_plan()
    plan = {"scope": scope, "request_plan": request_plan}
    first = freeze_plan(tmp_path, plan)
    assert all(path.exists() for path in first)
    changed = json.loads(json.dumps(scope))
    changed["scope_hash"] = "0" * 64
    with pytest.raises(ValueError, match="Immutable"):
        freeze_plan(tmp_path, {"scope": changed, "request_plan": request_plan})


def test_checkpoint_statuses_and_identity() -> None:
    scope, request_plan = _mini_scope_plan()
    checkpoint = initialize_checkpoint(scope, request_plan)
    assert checkpoint["scope_hash"] == scope["scope_hash"]
    assert checkpoint["request_plan_hash"] == request_plan["request_plan_hash"]
    assert {row["status"] for row in checkpoint["requests"].values()} == {"PENDING"}


def test_ingest_resume_raw_immutability_and_idempotency(tmp_path: Path) -> None:
    scope, request_plan = _mini_scope_plan()
    freeze_plan(tmp_path, {"scope": scope, "request_plan": request_plan})
    checkpoint = initialize_checkpoint(scope, request_plan)
    client = FakeClient()
    completed = execute_requests(
        repo_root=tmp_path,
        scope=scope,
        request_plan=request_plan,
        checkpoint=checkpoint,
        mode=RunMode.INGEST,
        client=client,
        throttle_seconds=0,
    )
    request_state = next(iter(completed["requests"].values()))
    assert request_state["status"] == "COMPLETE"
    raw_path = Path(request_state["raw_path"])
    first_hash = file_sha256(raw_path)
    resumed = execute_requests(
        repo_root=tmp_path,
        scope=scope,
        request_plan=request_plan,
        checkpoint=completed,
        mode=RunMode.RESUME,
        client=client,
        throttle_seconds=0,
    )
    assert client.calls == 1
    assert file_sha256(raw_path) == first_hash
    assert resumed["requests"] == completed["requests"]


def test_failed_request_replay_targets_only_retryable_ids(tmp_path: Path) -> None:
    scope, request_plan = _mini_scope_plan()
    freeze_plan(tmp_path, {"scope": scope, "request_plan": request_plan})
    checkpoint = initialize_checkpoint(scope, request_plan)
    failed = execute_requests(
        repo_root=tmp_path,
        scope=scope,
        request_plan=request_plan,
        checkpoint=checkpoint,
        mode=RunMode.INGEST,
        client=FakeClient(fail=True),
        throttle_seconds=0,
    )
    assert next(iter(failed["requests"].values()))["status"] == "FAILED_RETRYABLE"
    replay_client = FakeClient()
    replayed = execute_requests(
        repo_root=tmp_path,
        scope=scope,
        request_plan=request_plan,
        checkpoint=failed,
        mode=RunMode.REPLAY_FAILED,
        client=replay_client,
        throttle_seconds=0,
    )
    assert replay_client.calls == 1
    assert next(iter(replayed["requests"].values()))["status"] == "COMPLETE"


def test_deterministic_partition_compression_and_hash(tmp_path: Path) -> None:
    rows = [{"symbol": "AAA", "bar_start": "2022-01-03T09:15:00+05:30", "close": "100"}]
    first = tmp_path / "first.csv.gz"
    second = tmp_path / "second.csv.gz"
    _write_gzip_csv_deterministic(first, rows)
    _write_gzip_csv_deterministic(second, rows)
    assert file_sha256(first) == file_sha256(second)


def test_canonical_normalization_strict_quality_and_reconciliation() -> None:
    calendar, bars = _session_bars()
    quality = assess_session_quality(bars, calendar=calendar)
    assert quality.strict_usable and quality.actual_bars == 75
    assert _quality_classification([{"actual_bars": 75, "usability": "USABLE_STRICT"}]) == "CLEAN"
    from app.research.intraday.models import DailyBarReference

    reference = DailyBarReference(
        "AAA",
        date(2022, 1, 3),
        bars[0].open,
        max(row.high for row in bars),
        min(row.low for row in bars),
        bars[-1].close,
        sum(row.volume or 0 for row in bars),
        "FIXTURE",
    )
    assert _reconciliation_row(bars, reference)["classification"] == "MATCH"
    broken = replace(bars[0], high=Decimal("1"), quality_flags=(str(IntradayBarQuality.OHLC_INVALID),))
    assert not assess_session_quality([broken, *bars[1:]], calendar=calendar).strict_usable


def test_opportunity_and_trade_structural_coverage_without_performance() -> None:
    opportunity = _opportunity()
    session_by_key = {
        ("AAA", value): {"actual_bars": 75, "usability": str(SessionUsability.USABLE_STRICT)}
        for value in ("2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06", "2022-01-07")
    }
    ca = {(symbol, date.fromisoformat(value)): "SAFE" for symbol, value in session_by_key}
    coverage = build_opportunity_coverage([opportunity], session_by_key, ca)[0]
    assert coverage["execution_path_reconstructable"]
    assert coverage["confirmation_fields_available"]
    trade = {"trade_id": "T1", "symbol": "AAA", "decision_date": "2022-01-03", "entry_date": "2022-01-04"}
    trade_coverage = build_trade_coverage([trade], [opportunity], session_by_key, ca)[0]
    assert trade_coverage["full_hold_path_strict_usable"]
    assert trade_coverage["performance_evaluated"] is False


def test_no_strategy_or_outcome_mutation_contract_and_baseline_immutability() -> None:
    source = Path(inspect.getsourcefile(build_plan)).read_text(encoding="utf-8")
    assert "simulate_portfolio" not in source
    assert "build_strategy" not in source
    assert "place_order" not in source
    before = build_plan(repo_root=REPO_ROOT, instrument_master_path=MASTER_PATH)
    after = build_plan(repo_root=REPO_ROOT, instrument_master_path=MASTER_PATH)
    assert before["scope"]["scope_hash"] == after["scope"]["scope_hash"]


def test_validation_is_still_sealed_and_manifest_has_no_validation_request() -> None:
    lock = json.loads(
        (DATA_DIR / "research/temporal_validation/v1/governance/validation_lock_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["validation_state"] == "SEALED"
    assert lock["validation_run_count"] == 0
    plan = build_plan(repo_root=REPO_ROOT, instrument_master_path=MASTER_PATH)
    assert all(row["end_date"] <= "2024-12-31" for row in plan["request_plan"]["requests"])
