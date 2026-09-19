from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from app.market_api.session_models import (
    MarketObservationEvent,
    MarketObservationSession,
    MarketSessionSnapshot,
)


SENSITIVE_KEYS = ("authorization", "cookie", "password", "secret", "token", "totp", "api_key", "api-key")


def sanitize_evidence(value: Any) -> Any:
    """Return JSON-safe evidence with credential-bearing fields removed."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if any(marker in str(key).lower() for marker in SENSITIVE_KEYS) else sanitize_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_evidence(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if "authorization:" in lowered or "bearer " in lowered or "set-cookie:" in lowered:
            return "[REDACTED]"
        return value
    return value


class MarketSessionRepository(Protocol):
    def save(self, session: MarketObservationSession) -> None: ...

    def get(self, session_id: str) -> MarketObservationSession | None: ...

    def list(self, *, limit: int = 100) -> tuple[MarketObservationSession, ...]: ...


class MarketObservationRepository(Protocol):
    def append_event(self, event: MarketObservationEvent) -> None: ...

    def list_events(self, session_id: str, *, limit: int = 1000) -> tuple[MarketObservationEvent, ...]: ...

    def append_snapshot(self, snapshot: MarketSessionSnapshot) -> None: ...

    def list_snapshots(self, session_id: str, *, limit: int = 1000) -> tuple[MarketSessionSnapshot, ...]: ...

    def write_report(self, filename: str, payload: dict[str, Any]) -> Path: ...


class JsonlMarketObservationStore(MarketSessionRepository, MarketObservationRepository):
    """Append-only local evidence store with restart-safe session reconstruction."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.sessions_path = self.root / "market_sessions.jsonl"
        self.events_path = self.root / "market_observation_events.jsonl"
        self.snapshots_path = self.root / "market_session_snapshots.jsonl"
        self.reports_path = self.root / "reports"
        self._lock = RLock()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(sanitize_evidence(payload), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            handle.flush()

    @staticmethod
    def _records(path: Path) -> Iterable[dict[str, Any]]:
        if not path.exists():
            return ()
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        return tuple(rows)

    def save(self, session: MarketObservationSession) -> None:
        with self._lock:
            self._ensure_root()
            self._append(self.sessions_path, session.model_dump(mode="json"))

    def get(self, session_id: str) -> MarketObservationSession | None:
        with self._lock:
            matched = [row for row in self._records(self.sessions_path) if row.get("session_id") == session_id]
        return MarketObservationSession.model_validate(matched[-1]) if matched else None

    def list(self, *, limit: int = 100) -> tuple[MarketObservationSession, ...]:
        latest: dict[str, dict[str, Any]] = {}
        with self._lock:
            for row in self._records(self.sessions_path):
                if row.get("session_id"):
                    latest[str(row["session_id"])] = row
        sessions = sorted(
            (MarketObservationSession.model_validate(row) for row in latest.values()),
            key=lambda item: item.started_at,
            reverse=True,
        )
        return tuple(sessions[: max(limit, 0)])

    def append_event(self, event: MarketObservationEvent) -> None:
        with self._lock:
            self._ensure_root()
            self._append(self.events_path, event.model_dump(mode="json"))

    def list_events(self, session_id: str, *, limit: int = 1000) -> tuple[MarketObservationEvent, ...]:
        with self._lock:
            rows = [row for row in self._records(self.events_path) if row.get("session_id") == session_id]
        return tuple(MarketObservationEvent.model_validate(row) for row in rows[-max(limit, 0) :])

    def append_snapshot(self, snapshot: MarketSessionSnapshot) -> None:
        with self._lock:
            self._ensure_root()
            self._append(self.snapshots_path, snapshot.model_dump(mode="json"))

    def list_snapshots(self, session_id: str, *, limit: int = 1000) -> tuple[MarketSessionSnapshot, ...]:
        with self._lock:
            rows = [row for row in self._records(self.snapshots_path) if row.get("session_id") == session_id]
        return tuple(MarketSessionSnapshot.model_validate(row) for row in rows[-max(limit, 0) :])

    def write_report(self, filename: str, payload: dict[str, Any]) -> Path:
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("MARKET_SESSION_REPORT_FILENAME_INVALID")
        with self._lock:
            self.reports_path.mkdir(parents=True, exist_ok=True)
            destination = self.reports_path / filename
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(sanitize_evidence(payload), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
            return destination


__all__ = (
    "JsonlMarketObservationStore",
    "MarketObservationRepository",
    "MarketSessionRepository",
    "sanitize_evidence",
)
