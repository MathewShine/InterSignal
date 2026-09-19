from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.market_api.session_models import (
    MarketCoverageSummary,
    MarketInstrumentObservation,
    MarketObservationEvent,
    MarketObservationEventType,
    MarketObservationSession,
    MarketSessionSnapshot,
    MarketSessionState,
    MarketSessionSummary,
    MarketSessionVerdict,
    TickRecordingMode,
)
from app.market_api.session_repository import MarketObservationRepository, MarketSessionRepository, sanitize_evidence
from app.providers.market_data import MarketTickObservation


DEFAULT_MONITORED_INSTRUMENTS = (
    "NIFTY 50",
    "NIFTY 500",
    "BANK NIFTY",
    "FINNIFTY",
    "RELIANCE",
    "TCS",
    "HDFCBANK",
)
INDEX_KEYS = {"NIFTY50", "NIFTY500", "BANKNIFTY", "NIFTYBANK", "FINNIFTY", "NIFTYFINSERVICE"}
CONNECTED_STATES = {"CONNECTED"}
DISCONNECTED_STATES = {"DISCONNECTED", "FAILED", "NOT_CONFIGURED"}


def _key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


class MarketSessionManager:
    """Orchestrates durable, read-only evidence from normalized market observations."""

    def __init__(
        self,
        *,
        provider: Any,
        feed_manager: Any | None,
        live_cache: Any,
        session_repository: MarketSessionRepository,
        observation_repository: MarketObservationRepository,
        recording_mode: TickRecordingMode = TickRecordingMode.SELECTED,
        selected_instruments: tuple[str, ...] = DEFAULT_MONITORED_INSTRUMENTS,
        sample_interval_seconds: float = 5,
        summary_interval_seconds: float = 60,
        stale_threshold_seconds: float = 30,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.feed_manager = feed_manager
        self.live_cache = live_cache
        self.session_repository = session_repository
        self.observation_repository = observation_repository
        self.recording_mode = TickRecordingMode(recording_mode)
        self.selected_instruments = tuple(dict.fromkeys(item.strip() for item in selected_instruments if item.strip()))
        self.sample_interval_seconds = max(float(sample_interval_seconds), 0)
        self.summary_interval_seconds = max(float(summary_interval_seconds), 1)
        self.stale_threshold_seconds = max(float(stale_threshold_seconds), 1)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._session: MarketObservationSession | None = None
        self._instrument_states: dict[str, MarketInstrumentObservation] = {}
        self._active_subscriptions: set[str] = set()
        self._subscription_targets: dict[str, str] = {}
        self._observed_keys: set[str] = set()
        self._last_recorded: dict[str, datetime] = {}
        self._last_values: dict[str, Decimal] = {}
        self._last_provider_state: str | None = None
        self._disconnect_started_at: datetime | None = None
        self._downtime_seconds = 0.0
        self._stale_started_at: datetime | None = None
        self._stale_durations: list[float] = []
        self._had_open_session = False
        self._monitor_task: asyncio.Task[None] | None = None

    @property
    def active(self) -> bool:
        return bool(self._session and self._session.status not in {MarketSessionState.COMPLETED, MarketSessionState.FAILED})

    def current(self) -> MarketObservationSession | None:
        if self._session:
            return self._session.model_copy(deep=True)
        sessions = self.session_repository.list(limit=1)
        return sessions[0] if sessions else None

    def get(self, session_id: str) -> MarketObservationSession | None:
        if self._session and self._session.session_id == session_id:
            return self._session.model_copy(deep=True)
        return self.session_repository.get(session_id)

    def list(self, *, limit: int = 100) -> tuple[MarketObservationSession, ...]:
        return self.session_repository.list(limit=limit)

    async def start(self) -> MarketObservationSession:
        if self.active and self._session:
            return self._session.model_copy(deep=True)
        now = self._now()
        market_state = self._exchange_state()
        initial_state = {
            "OPEN": MarketSessionState.RUNNING,
            "PRE_OPEN": MarketSessionState.PRE_OPEN,
            "CLOSED": MarketSessionState.CLOSED,
        }.get(market_state, MarketSessionState.CREATED)
        self._reset_runtime_state()
        self._session = MarketObservationSession(
            session_id=uuid4().hex,
            market_date=now.date(),
            provider=str(getattr(self.provider, "provider_name", "UNAVAILABLE")),
            provider_mode=str(getattr(getattr(self.provider, "mode", None), "value", "UNAVAILABLE")),
            started_at=now,
            exchange_session_state=market_state,
            status=initial_state,
            stream_state=self._feed_state(),
            instrument_count=len(self.selected_instruments),
            coverage_summary=self._coverage(),
        )
        self.session_repository.save(self._session)
        self._append_event(MarketObservationEventType.SESSION_CREATED, metadata={"recording_mode": self.recording_mode.value})
        if market_state == "OPEN":
            self._had_open_session = True
            self._append_event(MarketObservationEventType.SESSION_OPEN)
        elif market_state == "CLOSED":
            self._append_event(MarketObservationEventType.SESSION_CLOSED, reason_code="MARKET_ALREADY_CLOSED")
        await self.record_provider_state(self._feed_state())
        if self.feed_manager:
            try:
                self._subscription_targets = self._resolve_subscription_targets()
                subscriptions = await self.feed_manager.subscribe(tuple(self._subscription_targets.values()))
                self._active_subscriptions.update(str(item) for item in subscriptions)
                self._session.stream_state = self._feed_state()
                await self.record_provider_state(self._session.stream_state)
                self._append_event(
                    MarketObservationEventType.SUBSCRIBED,
                    payload_summary={
                        "instruments": list(self.selected_instruments),
                        "resolved_instruments": list(subscriptions),
                        "count": len(subscriptions),
                    },
                )
                if self._session.stream_state == "CONNECTED":
                    self._append_event(MarketObservationEventType.STREAM_READY)
            except Exception as error:
                self.record_provider_error("SUBSCRIPTION_FAILURE", detail=type(error).__name__)
        else:
            self._subscription_targets = {item: item for item in self.selected_instruments}
            self._active_subscriptions.update(self.selected_instruments)
            self._append_event(
                MarketObservationEventType.SUBSCRIBED,
                payload_summary={"instruments": list(self.selected_instruments), "count": len(self.selected_instruments)},
                reason_code="RECORDED_PROVIDER",
            )
        self._refresh_session()
        self._start_monitor()
        return self._session.model_copy(deep=True)

    async def stop(self, *, reason_code: str = "MANUAL_STOP") -> MarketSessionSummary:
        if not self._session:
            latest = self.current()
            if not latest:
                raise ValueError("MARKET_SESSION_NOT_STARTED")
            self._session = latest
        if self._session.status == MarketSessionState.COMPLETED:
            return self.summary(self._session.session_id)
        await self._release_subscriptions(reason_code=reason_code)
        return self._finalize(reason_code=reason_code)

    async def observe_tick(self, tick: MarketTickObservation) -> None:
        if not self.active or not self._session:
            return
        received_at = self._now()
        identity = tick.symbol.upper()
        identity_key = _key(identity)
        self._observed_keys.add(identity_key)
        self._observed_keys.add(_key(tick.instrument_id))
        state = self._instrument_states.get(identity_key) or MarketInstrumentObservation(instrument_id=identity)
        state.update_count += 1
        state.first_update_at = state.first_update_at or received_at
        state.last_update_at = received_at
        state.last_source_timestamp = tick.timestamp
        self._instrument_states[identity_key] = state
        self._session.tick_count += 1
        self._session.first_tick_at = self._session.first_tick_at or received_at
        self._session.last_tick_at = received_at
        self._session.last_market_event_at = received_at
        if self._stale_started_at is not None:
            duration = max((received_at - self._stale_started_at).total_seconds(), 0)
            self._stale_durations.append(duration)
            self._append_event(
                MarketObservationEventType.STALE_DATA_RECOVERED,
                instrument_id=identity,
                reason_code="NORMALIZED_TICK_RESUMED",
                metadata={"stale_duration_seconds": round(duration, 3)},
            )
            self._stale_started_at = None
            if self._session.status == MarketSessionState.DEGRADED:
                self._session.status = MarketSessionState.RUNNING
        if self._should_record_tick(tick, received_at):
            event_type = MarketObservationEventType.INDEX_UPDATE if identity_key in INDEX_KEYS else MarketObservationEventType.TICK_RECEIVED
            self._append_event(
                event_type,
                instrument_id=identity,
                source_timestamp=tick.timestamp,
                freshness=tick.freshness,
                payload_summary={"ltp": str(tick.ltp), "source": tick.source},
            )
            self._last_recorded[identity_key] = received_at
            self._last_values[identity_key] = tick.ltp
            self._refresh_session(save=True)
        else:
            self._refresh_session(save=False)

    async def record_provider_state(self, state: str, *, reason_code: str | None = None, retry_number: int | None = None) -> None:
        if not self.active or not self._session:
            return
        now = self._now()
        normalized = str(state or "UNKNOWN").upper()
        previous = self._last_provider_state
        state_changed = previous != normalized
        self._session.last_provider_heartbeat_at = now
        self._session.stream_state = normalized
        if normalized in CONNECTED_STATES:
            if self._disconnect_started_at:
                downtime = max((now - self._disconnect_started_at).total_seconds(), 0)
                self._downtime_seconds += downtime
                self._session.reconnect_count += 1
                self._append_event(
                    MarketObservationEventType.PROVIDER_RECONNECTED,
                    reason_code=reason_code or "PROVIDER_CONNECTION_RESTORED",
                    metadata={"downtime_seconds": round(downtime, 3), "retry_number": retry_number},
                )
                self._disconnect_started_at = None
            elif previous not in CONNECTED_STATES:
                self._append_event(MarketObservationEventType.PROVIDER_CONNECTED)
        elif normalized in DISCONNECTED_STATES and previous is not None and previous not in DISCONNECTED_STATES:
            self._disconnect_started_at = now
            self._session.disconnect_count += 1
            self._append_event(MarketObservationEventType.PROVIDER_DISCONNECTED, reason_code=reason_code or normalized)
        self._last_provider_state = normalized
        self._refresh_session(save=state_changed)

    def record_rate_limited(self, reason_code: str = "PROVIDER_RATE_LIMITED") -> None:
        if not self.active or not self._session:
            return
        self._session.error_count += 1
        self._append_event(MarketObservationEventType.RATE_LIMITED, reason_code=reason_code)
        self._refresh_session(save=True)

    def record_provider_error(self, reason_code: str, *, detail: str | None = None) -> None:
        if not self.active or not self._session:
            return
        self._session.error_count += 1
        self._append_event(
            MarketObservationEventType.PROVIDER_ERROR,
            reason_code=reason_code,
            metadata={"error_type": detail} if detail else {},
        )
        self._refresh_session(save=True)

    def check_stale(self, *, now: datetime | None = None, market_state: str | None = None, expected_stream: bool = True) -> bool:
        if not self.active or not self._session:
            return False
        observed_at = now or self._now()
        state = (market_state or self._session.exchange_session_state).upper()
        if state != "OPEN" or not expected_stream:
            return False
        baseline = self._session.last_tick_at or self._session.started_at
        age = max((observed_at - baseline).total_seconds(), 0)
        if age <= self.stale_threshold_seconds or self._stale_started_at is not None:
            return False
        self._stale_started_at = baseline
        self._session.stale_interval_count += 1
        self._session.status = MarketSessionState.DEGRADED
        for instrument in self._instrument_states.values():
            instrument.stale_periods += 1
        self._append_event(
            MarketObservationEventType.STALE_DATA_DETECTED,
            reason_code="NO_NORMALIZED_TICK_WITHIN_THRESHOLD",
            metadata={"last_tick_age_seconds": round(age, 3), "threshold_seconds": self.stale_threshold_seconds},
        )
        self._refresh_session(save=True)
        return True

    def capture_summary(self, *, now: datetime | None = None) -> MarketSessionSnapshot:
        if not self._session:
            raise ValueError("MARKET_SESSION_NOT_STARTED")
        observed_at = now or self._now()
        age = None
        if self._session.last_tick_at:
            age = max((observed_at - self._session.last_tick_at).total_seconds(), 0)
        breadth_available = bool(getattr(self.live_cache, "breadth", None))
        sector_available = bool(getattr(self.live_cache, "sectors", None))
        if not breadth_available:
            try:
                breadth_available = self.provider.get_breadth_snapshot() is not None
            except Exception:
                breadth_available = False
        if not sector_available:
            try:
                sector_available = bool(self.provider.get_sector_snapshot())
            except Exception:
                sector_available = False
        snapshot = MarketSessionSnapshot(
            session_id=self._session.session_id,
            timestamp=observed_at,
            provider_state="CONNECTED" if bool(getattr(self.provider, "connected", False)) else "UNAVAILABLE",
            stream_state=self._feed_state(),
            last_tick_age_seconds=age,
            index_states=tuple(value.model_copy(deep=True) for key, value in self._instrument_states.items() if key in INDEX_KEYS),
            subscription_count=len(self._active_subscriptions),
            coverage=self._coverage(),
            breadth_available=breadth_available,
            sector_available=sector_available,
            error_count=self._session.error_count,
            reconnect_count=self._session.reconnect_count,
        )
        self.observation_repository.append_snapshot(snapshot)
        self._session.summary_snapshot_count += 1
        self._append_event(
            MarketObservationEventType.SUMMARY_SNAPSHOT,
            payload_summary={
                "coverage_pct": snapshot.coverage.coverage_pct,
                "breadth_available": breadth_available,
                "sector_available": sector_available,
            },
        )
        if breadth_available:
            self._append_event(MarketObservationEventType.BREADTH_UPDATE, payload_summary={"available": True})
        else:
            self._append_event(MarketObservationEventType.BREADTH_UPDATE, reason_code="BREADTH_UNAVAILABLE")
        if sector_available:
            self._append_event(MarketObservationEventType.SECTOR_UPDATE, payload_summary={"available": True})
        else:
            self._append_event(MarketObservationEventType.SECTOR_UPDATE, reason_code="SECTOR_AGGREGATION_UNAVAILABLE")
        self._refresh_session(save=True)
        return snapshot

    def summary(self, session_id: str) -> MarketSessionSummary:
        session = self.get(session_id)
        if not session:
            raise ValueError("MARKET_SESSION_NOT_FOUND")
        events = self.observation_repository.list_events(session_id)
        snapshots = self.observation_repository.list_snapshots(session_id)
        end = session.ended_at or self._now()
        duration = max((end - session.started_at).total_seconds(), 0)
        downtime = self._downtime_seconds if self._session and self._session.session_id == session_id else sum(
            float(event.metadata.get("downtime_seconds") or 0)
            for event in events
            if event.event_type == MarketObservationEventType.PROVIDER_RECONNECTED
        )
        criteria = self._criteria(session, events)
        limitations: list[str] = []
        if not any(event.event_type == MarketObservationEventType.SESSION_OPEN for event in events):
            limitations.append("MARKET_NOT_OPEN_DURING_OBSERVATION")
        if not snapshots or not any(item.breadth_available for item in snapshots):
            limitations.append("BREADTH_NOT_OBSERVED")
        if not snapshots or not any(item.sector_available for item in snapshots):
            limitations.append("SECTOR_AGGREGATION_NOT_OBSERVED")
        return MarketSessionSummary(
            session=session,
            duration_seconds=duration,
            uptime_pct=max(0, min(100, (duration - downtime) / duration * 100)) if duration else 100,
            observed_instruments=session.coverage_summary.observed_instruments,
            coverage=session.coverage_summary,
            summary_snapshot_count=session.summary_snapshot_count,
            criteria=criteria,
            limitations=tuple(limitations),
        )

    def report_path(self, session_id: str) -> Path:
        summary = self.summary(session_id)
        events = self.observation_repository.list_events(session_id)
        payload = {
            "version": summary.version,
            "session_identity": {
                "session_id": summary.session.session_id,
                "market": summary.session.market,
                "market_date": summary.session.market_date.isoformat(),
                "provider": summary.session.provider,
                "provider_mode": summary.session.provider_mode,
            },
            "criteria": summary.criteria,
            "result": summary.session.verdict.value if summary.session.verdict else None,
            "metrics": summary.model_dump(mode="json"),
            "warnings": list(summary.session.warnings),
            "failures": list(summary.session.failures),
            "timeline_summary": [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "instrument_id": event.instrument_id,
                    "reason_code": event.reason_code,
                }
                for event in events
            ],
            "limitations": list(summary.limitations),
        }
        filename = f"market_session_{summary.session.market_date.isoformat()}_{session_id}.json"
        return self.observation_repository.write_report(filename, sanitize_evidence(payload))

    def _finalize(self, *, reason_code: str) -> MarketSessionSummary:
        if not self._session:
            raise ValueError("MARKET_SESSION_NOT_STARTED")
        now = self._now()
        if self._stale_started_at:
            self._stale_durations.append(max((now - self._stale_started_at).total_seconds(), 0))
            self._stale_started_at = None
        if self._disconnect_started_at:
            self._downtime_seconds += max((now - self._disconnect_started_at).total_seconds(), 0)
            self._disconnect_started_at = None
        self._session.ended_at = now
        self._session.status = MarketSessionState.COMPLETED
        self._session.coverage_summary = self._coverage()
        self._session.monitored_instruments = tuple(self._instrument_states.values())
        events = self.observation_repository.list_events(self._session.session_id)
        criteria = self._criteria(self._session, events)
        failures = tuple(name for name, passed in criteria.items() if not passed)
        warnings: list[str] = []
        if self._session.reconnect_count:
            warnings.append("PROVIDER_RECONNECTED_DURING_SESSION")
        if not self._had_open_session:
            warnings.append("MARKET_NOT_OPEN_DURING_OBSERVATION")
        if self._session.error_count:
            warnings.append("OPERATIONAL_ERRORS_RECORDED")
        self._session.failures = failures
        self._session.warnings = tuple(warnings)
        self._session.verdict = (
            MarketSessionVerdict.FAIL
            if failures
            else MarketSessionVerdict.PASS_WITH_WARNINGS
            if warnings
            else MarketSessionVerdict.PASS
        )
        self._append_event(
            MarketObservationEventType.SESSION_COMPLETED,
            reason_code=reason_code,
            payload_summary={"verdict": self._session.verdict.value},
        )
        self.session_repository.save(self._session)
        self.report_path(self._session.session_id)
        if self._monitor_task and self._monitor_task is not asyncio.current_task():
            self._monitor_task.cancel()
        return self.summary(self._session.session_id)

    def _criteria(self, session: MarketObservationSession, events: tuple[MarketObservationEvent, ...]) -> dict[str, bool]:
        types = {event.event_type for event in events}
        market_opened = MarketObservationEventType.SESSION_OPEN in types
        subscribed_count = max(
            (
                int(event.payload_summary.get("count") or 0)
                for event in events
                if event.event_type == MarketObservationEventType.SUBSCRIBED
            ),
            default=0,
        )
        max_stale = max(self._stale_durations, default=0)
        if not self._session or self._session.session_id != session.session_id:
            durations = [
                float(event.metadata.get("stale_duration_seconds") or 0)
                for event in events
                if event.event_type == MarketObservationEventType.STALE_DATA_RECOVERED
            ]
            max_stale = max(durations, default=0)
        return {
            "provider_connected": MarketObservationEventType.PROVIDER_CONNECTED in types,
            "stream_ready": MarketObservationEventType.STREAM_READY in types or session.provider_mode == "SEEDED",
            "required_instruments_subscribed": bool(session.instrument_count) and subscribed_count >= session.instrument_count,
            "first_tick_received_during_open_session": (not market_opened) or session.first_tick_at is not None,
            "no_sustained_stale_interval": max_stale <= self.stale_threshold_seconds,
            "reconnect_succeeded_if_required": session.disconnect_count == 0 or session.reconnect_count >= session.disconnect_count,
            "session_finalized": session.ended_at is not None and session.status == MarketSessionState.COMPLETED,
            "read_only_domain": session.read_only,
        }

    def _should_record_tick(self, tick: MarketTickObservation, received_at: datetime) -> bool:
        if self.recording_mode == TickRecordingMode.NONE:
            return False
        identity_key = _key(tick.symbol)
        if self.recording_mode == TickRecordingMode.SELECTED and not self._is_selected(tick.symbol, tick.instrument_id):
            return False
        if self.recording_mode == TickRecordingMode.ALL:
            return True
        last = self._last_recorded.get(identity_key)
        return last is None or (received_at - last).total_seconds() >= self.sample_interval_seconds

    def _is_selected(self, *values: str) -> bool:
        candidate_keys = {_key(value) for value in values}
        for selected in self.selected_instruments:
            selected_key = _key(selected)
            if selected_key in candidate_keys or any(selected_key in candidate for candidate in candidate_keys):
                return True
            if selected_key == "BANKNIFTY" and "NIFTYBANK" in candidate_keys:
                return True
            if selected_key == "NIFTY50" and "NIFTY" in candidate_keys:
                return True
        return False

    def _coverage(self) -> MarketCoverageSummary:
        expected = self.selected_instruments
        active = tuple(
            item
            for item in expected
            if any(_key(self._subscription_targets.get(item, item)) == _key(value) for value in self._active_subscriptions)
        )
        observed = tuple(item for item in expected if any(_key(item) in value or value in _key(item) for value in self._observed_keys))
        missing = tuple(item for item in expected if item not in active)
        coverage_pct = len(observed) / len(expected) * 100 if expected else 100
        return MarketCoverageSummary(
            expected_instruments=expected,
            active_instruments=active,
            observed_instruments=observed,
            missing_instruments=missing,
            coverage_pct=coverage_pct,
        )

    def _append_event(
        self,
        event_type: MarketObservationEventType,
        *,
        instrument_id: str | None = None,
        source_timestamp: datetime | None = None,
        freshness: str | None = None,
        payload_summary: dict[str, Any] | None = None,
        reason_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._session:
            return
        now = self._now()
        self.observation_repository.append_event(
            MarketObservationEvent(
                event_id=uuid4().hex,
                session_id=self._session.session_id,
                timestamp=now,
                event_type=event_type,
                provider=self._session.provider,
                instrument_id=instrument_id,
                source_timestamp=source_timestamp,
                received_at=now,
                freshness=freshness,
                payload_summary=sanitize_evidence(payload_summary or {}),
                reason_code=reason_code,
                metadata=sanitize_evidence(metadata or {}),
            )
        )

    def _refresh_session(self, *, save: bool = True) -> None:
        if not self._session:
            return
        self._session.instrument_count = len(self.selected_instruments)
        self._session.coverage_summary = self._coverage()
        self._session.monitored_instruments = tuple(self._instrument_states.values())
        if save:
            self.session_repository.save(self._session)

    def _exchange_state(self) -> str:
        try:
            status = self.provider.get_market_status()
            return str(getattr(status, "status", "UNKNOWN")).upper()
        except Exception:
            return "UNKNOWN"

    def _feed_state(self) -> str:
        state = getattr(self.feed_manager, "state", None)
        if state is not None:
            return str(getattr(state, "value", state)).upper()
        return "CONNECTED" if bool(getattr(self.provider, "connected", False)) else "NOT_AVAILABLE"

    def _reset_runtime_state(self) -> None:
        self._instrument_states = {}
        self._active_subscriptions = set()
        self._subscription_targets = {}
        self._observed_keys = set()
        self._last_recorded = {}
        self._last_values = {}
        self._last_provider_state = None
        self._disconnect_started_at = None
        self._downtime_seconds = 0
        self._stale_started_at = None
        self._stale_durations = []
        self._had_open_session = False

    def _resolve_subscription_targets(self) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for selected in self.selected_instruments:
            target = selected
            try:
                candidates = self.provider.search_instruments(selected, limit=20)
            except Exception:
                candidates = ()
            for candidate in candidates:
                values = (
                    str(getattr(candidate, "symbol", "")),
                    str(getattr(candidate, "display_name", "")),
                    str(getattr(candidate, "instrument_id", "")),
                    str(getattr(candidate, "groww_symbol", "")),
                )
                if any(self._selection_matches(selected, value) for value in values if value):
                    target = str(getattr(candidate, "instrument_id", "") or getattr(candidate, "symbol", selected))
                    break
            resolved[selected] = target
        return resolved

    @staticmethod
    def _selection_matches(selected: str, candidate: str) -> bool:
        selected_key = _key(selected)
        candidate_key = _key(candidate)
        aliases = {
            "NIFTY50": {"NIFTY", "NIFTY50"},
            "NIFTY500": {"NIFTY500"},
            "BANKNIFTY": {"BANKNIFTY", "NIFTYBANK"},
            "FINNIFTY": {"FINNIFTY", "NIFTYFINSERVICE", "NIFTYFINANCIALSERVICES"},
        }
        return (
            selected_key == candidate_key
            or selected_key in candidate_key
            or candidate_key in aliases.get(selected_key, set())
            or selected_key in aliases.get(candidate_key, set())
        )

    def _start_monitor(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            return
        try:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
        except RuntimeError:
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        last_summary = self._now()
        try:
            while self.active and self._session:
                await asyncio.sleep(min(5, self.summary_interval_seconds))
                now = self._now()
                exchange_state = self._exchange_state()
                previous_exchange = self._session.exchange_session_state
                self._session.exchange_session_state = exchange_state
                await self.record_provider_state(self._feed_state())
                if exchange_state == "OPEN" and previous_exchange != "OPEN":
                    self._had_open_session = True
                    self._session.status = MarketSessionState.RUNNING
                    self._append_event(MarketObservationEventType.SESSION_OPEN)
                self.check_stale(now=now, market_state=exchange_state, expected_stream=self._feed_state() == "CONNECTED")
                if (now - last_summary).total_seconds() >= self.summary_interval_seconds:
                    self.capture_summary(now=now)
                    last_summary = now
                if exchange_state == "CLOSED" and self._had_open_session:
                    self._session.status = MarketSessionState.CLOSED
                    self._append_event(MarketObservationEventType.SESSION_CLOSED)
                    await self._release_subscriptions(reason_code="EXCHANGE_SESSION_CLOSED")
                    self._finalize(reason_code="EXCHANGE_SESSION_CLOSED")
                    break
        except asyncio.CancelledError:
            raise

    async def _release_subscriptions(self, *, reason_code: str) -> None:
        if self.feed_manager and self._active_subscriptions:
            try:
                await self.feed_manager.unsubscribe(tuple(self._active_subscriptions))
            except Exception as error:
                self.record_provider_error("UNSUBSCRIBE_FAILURE", detail=type(error).__name__)
        if self._active_subscriptions:
            self._append_event(
                MarketObservationEventType.UNSUBSCRIBED,
                payload_summary={"instruments": sorted(self._active_subscriptions)},
                reason_code=reason_code,
            )
        self._active_subscriptions.clear()


__all__ = ("DEFAULT_MONITORED_INSTRUMENTS", "MarketSessionManager")
