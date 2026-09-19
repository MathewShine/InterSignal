from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.market_api.session_manager import MarketSessionManager
from app.market_api.session_models import (
    INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1,
    INTERSIGNAL_MARKET_SESSION_V1,
    MarketObservationEventType,
    MarketSessionState,
    MarketSessionVerdict,
    TickRecordingMode,
)
from app.market_api.session_repository import JsonlMarketObservationStore
from app.providers.market_data import MarketProviderMode, MarketTickObservation


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 21, 3, 44, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class FakeProvider:
    provider_name = "GROWW"
    mode = MarketProviderMode.LIVE
    connected = True

    def __init__(self, state: str = "OPEN") -> None:
        self.market_state = state

    def get_market_status(self) -> SimpleNamespace:
        return SimpleNamespace(status=self.market_state)


class FakeFeed:
    def __init__(self) -> None:
        self.state = SimpleNamespace(value="CONNECTED")
        self.subscriptions: tuple[str, ...] = ()

    async def subscribe(self, instruments: tuple[str, ...]) -> tuple[str, ...]:
        self.subscriptions = instruments
        return instruments

    async def unsubscribe(self, instruments: tuple[str, ...]) -> None:
        self.subscriptions = tuple(item for item in self.subscriptions if item not in instruments)


def tick(symbol: str = "RELIANCE", value: str = "2890.15", at: datetime | None = None) -> MarketTickObservation:
    return MarketTickObservation(
        instrument_id=f"NSE:CASH:{symbol}",
        exchange="NSE",
        segment="CASH",
        symbol=symbol,
        timestamp=at or datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc),
        ltp=Decimal(value),
        source="NORMALIZED_TEST_FEED",
        freshness="FRESH",
    )


def manager(tmp_path: Path, *, clock: Clock | None = None, market_state: str = "OPEN") -> MarketSessionManager:
    store = JsonlMarketObservationStore(tmp_path)
    return MarketSessionManager(
        provider=FakeProvider(market_state),
        feed_manager=FakeFeed(),
        live_cache=SimpleNamespace(breadth=None, sectors={}),
        session_repository=store,
        observation_repository=store,
        recording_mode=TickRecordingMode.SELECTED,
        selected_instruments=("RELIANCE", "TCS"),
        sample_interval_seconds=5,
        summary_interval_seconds=60,
        stale_threshold_seconds=30,
        now=(clock or Clock()).now,
    )


def test_session_creation_sampling_finalization_and_report(tmp_path: Path) -> None:
    clock = Clock()
    service = manager(tmp_path, clock=clock)

    started = asyncio.run(service.start())
    asyncio.run(service.observe_tick(tick(at=clock.now())))
    clock.advance(1)
    asyncio.run(service.observe_tick(tick(value="2891", at=clock.now())))
    clock.advance(5)
    asyncio.run(service.observe_tick(tick(value="2892", at=clock.now())))
    snapshot = service.capture_summary(now=clock.now())
    completed = asyncio.run(service.stop())

    events = service.observation_repository.list_events(started.session_id)
    tick_events = [event for event in events if event.event_type == MarketObservationEventType.TICK_RECEIVED]
    assert started.version == INTERSIGNAL_MARKET_SESSION_V1
    assert events[0].version == INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1
    assert len(tick_events) == 2
    assert snapshot.subscription_count == 2
    assert completed.session.status == MarketSessionState.COMPLETED
    assert completed.session.verdict == MarketSessionVerdict.PASS
    assert completed.session.tick_count == 3
    assert service.feed_manager.subscriptions == ()
    report = tmp_path / "reports" / f"market_session_{started.market_date.isoformat()}_{started.session_id}.json"
    assert report.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["result"] == "PASS"


def test_repository_survives_reload_and_sanitizes_evidence(tmp_path: Path) -> None:
    clock = Clock()
    service = manager(tmp_path, clock=clock)
    started = asyncio.run(service.start())
    service._append_event(  # exercise the append-only evidence boundary directly
        MarketObservationEventType.PROVIDER_ERROR,
        payload_summary={"Authorization": "Bearer should-not-persist", "safe": "kept"},
    )
    asyncio.run(service.stop())

    reloaded = JsonlMarketObservationStore(tmp_path)
    restored = reloaded.get(started.session_id)
    events = reloaded.list_events(started.session_id)
    raw = (tmp_path / "market_observation_events.jsonl").read_text(encoding="utf-8")
    assert restored is not None and restored.status == MarketSessionState.COMPLETED
    assert any(event.payload_summary.get("safe") == "kept" for event in events)
    assert "should-not-persist" not in raw
    assert "[REDACTED]" in raw


def test_stale_detection_recovery_and_closed_market_suppression(tmp_path: Path) -> None:
    clock = Clock()
    service = manager(tmp_path / "open", clock=clock)
    started = asyncio.run(service.start())
    clock.advance(31)
    assert service.check_stale(now=clock.now(), market_state="OPEN", expected_stream=True)
    assert service.current().status == MarketSessionState.DEGRADED
    clock.advance(1)
    asyncio.run(service.observe_tick(tick(at=clock.now())))
    assert service.current().status == MarketSessionState.RUNNING
    types = [event.event_type for event in service.observation_repository.list_events(started.session_id)]
    assert MarketObservationEventType.STALE_DATA_DETECTED in types
    assert MarketObservationEventType.STALE_DATA_RECOVERED in types
    asyncio.run(service.stop())

    closed = manager(tmp_path / "closed", clock=Clock(), market_state="CLOSED")
    asyncio.run(closed.start())
    assert not closed.check_stale(now=closed._now() + timedelta(hours=1), market_state="CLOSED", expected_stream=True)
    assert closed.current().stale_interval_count == 0
    asyncio.run(closed.stop())


def test_disconnect_and_reconnect_create_explicit_evidence(tmp_path: Path) -> None:
    clock = Clock()
    service = manager(tmp_path, clock=clock)
    started = asyncio.run(service.start())
    asyncio.run(service.record_provider_state("DISCONNECTED", reason_code="SOCKET_CLOSED"))
    clock.advance(3)
    asyncio.run(service.record_provider_state("CONNECTED", retry_number=1))
    asyncio.run(service.stop())

    events = service.observation_repository.list_events(started.session_id)
    disconnected = next(event for event in events if event.event_type == MarketObservationEventType.PROVIDER_DISCONNECTED)
    reconnected = next(event for event in events if event.event_type == MarketObservationEventType.PROVIDER_RECONNECTED)
    assert disconnected.reason_code == "SOCKET_CLOSED"
    assert reconnected.metadata["retry_number"] == 1
    assert reconnected.metadata["downtime_seconds"] == 3


def test_session_api_is_durable_and_read_only(tmp_path: Path) -> None:
    settings = Settings(
        market_data_provider="seeded",
        market_session_data_root=tmp_path,
        market_observation_instruments="NIFTY 50,NIFTY 500",
    )
    with TestClient(create_app(settings)) as api:
        started = api.post("/api/market/session/start")
        current = api.get("/api/market/session/current")
        stopped = api.post("/api/market/session/stop")
        session_id = started.json()["session_id"]
        history = api.get("/api/market/sessions")
        detail = api.get(f"/api/market/sessions/{session_id}")
        events = api.get(f"/api/market/sessions/{session_id}/events")
        summary = api.get(f"/api/market/sessions/{session_id}/summary")

    assert all(response.status_code == 200 for response in (started, current, stopped, history, detail, events, summary))
    assert current.json()["session"]["read_only"] is True
    assert detail.json()["status"] == "COMPLETED"
    assert events.json()["items"]
    assert summary.json()["session"]["verdict"] == "FAIL"
    assert summary.json()["criteria"]["provider_connected"] is False
    assert not any(key in stopped.text.lower() for key in ("paper_order", "portfolio_write", "strategy_output"))
