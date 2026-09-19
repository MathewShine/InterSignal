from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.market_api.workspace_models import INTERSIGNAL_MARKET_STREAM_V1, MarketTickView
from app.providers.market_data import MarketTickObservation


@dataclass(slots=True)
class MarketLiveCache:
    """Process-local normalized market state; no vendor payload is retained."""

    quotes: dict[str, MarketTickView] = field(default_factory=dict)
    last_tick_at: datetime | None = None
    breadth: dict[str, Any] | None = None
    sectors: dict[str, dict[str, Any]] = field(default_factory=dict)

    def update(self, tick: MarketTickObservation) -> MarketTickView:
        view = MarketTickView(
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            segment=tick.segment,
            symbol=tick.symbol,
            timestamp=tick.timestamp,
            ltp=tick.ltp,
            change=tick.change,
            change_pct=tick.change_pct,
            open=tick.open,
            high=tick.high,
            low=tick.low,
            close=tick.close,
            volume=tick.volume,
            bid=tick.bid,
            ask=tick.ask,
            source=tick.source,
            freshness=tick.freshness,
        )
        self.quotes[tick.instrument_id.upper()] = view
        self.quotes[tick.symbol.upper()] = view
        self.last_tick_at = tick.timestamp
        return view


class MarketStreamHub:
    """Fans normalized ticks to bounded browser subscriptions."""

    MAX_CLIENT_SUBSCRIPTIONS = 25
    MAX_QUEUE_SIZE = 100

    def __init__(self, *, cache: MarketLiveCache | None = None) -> None:
        self.cache = cache or MarketLiveCache()
        self._clients: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._references: Counter[str] = Counter()

    def register(self, client_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._clients[client_id] = queue
        self._subscriptions[client_id] = set()
        return queue

    def unregister(self, client_id: str) -> tuple[str, ...]:
        symbols = tuple(self._subscriptions.pop(client_id, set()))
        self._clients.pop(client_id, None)
        for symbol in symbols:
            self._references[symbol] -= 1
            if self._references[symbol] <= 0:
                self._references.pop(symbol, None)
        return symbols

    def subscribe(self, client_id: str, symbols: tuple[str, ...]) -> tuple[str, ...]:
        current = self._subscriptions.setdefault(client_id, set())
        canonical = tuple(dict.fromkeys(value.strip().upper() for value in symbols if value.strip()))
        if len(current | set(canonical)) > self.MAX_CLIENT_SUBSCRIPTIONS:
            raise ValueError("MARKET_STREAM_CLIENT_LIMIT")
        added = tuple(value for value in canonical if value not in current)
        for symbol in added:
            current.add(symbol)
            self._references[symbol] += 1
        return added

    def unsubscribe(self, client_id: str, symbols: tuple[str, ...]) -> tuple[str, ...]:
        current = self._subscriptions.setdefault(client_id, set())
        removed: list[str] = []
        for symbol in dict.fromkeys(value.strip().upper() for value in symbols):
            if symbol not in current:
                continue
            current.remove(symbol)
            self._references[symbol] -= 1
            if self._references[symbol] <= 0:
                self._references.pop(symbol, None)
            removed.append(symbol)
        return tuple(removed)

    def provider_subscriptions(self) -> tuple[str, ...]:
        return tuple(sorted(self._references))

    async def publish_observation(self, tick: MarketTickObservation) -> MarketTickView:
        view = self.cache.update(tick)
        payload = view.model_dump(mode="json")
        for client_id, queue in tuple(self._clients.items()):
            subscriptions = self._subscriptions.get(client_id, set())
            if view.symbol.upper() not in subscriptions and view.instrument_id.upper() not in subscriptions:
                continue
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)
        return view

    @staticmethod
    def acknowledgement(action: str, symbols: tuple[str, ...]) -> dict[str, Any]:
        return {
            "version": INTERSIGNAL_MARKET_STREAM_V1,
            "event": "SUBSCRIPTION_STATE",
            "action": action,
            "symbols": list(symbols),
        }


__all__ = ("MarketLiveCache", "MarketStreamHub")
