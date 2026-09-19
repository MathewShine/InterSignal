from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.providers.groww.auth import GrowwAuthService
from app.providers.groww.instruments import GrowwInstrumentCache
from app.providers.market_data import MarketTickObservation


class GrowwFeedState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class GrowwFeedManager:
    """Owns the provider feed lifecycle; browser clients never receive this object."""

    MAX_PROVIDER_SUBSCRIPTIONS = 1000

    def __init__(
        self,
        *,
        auth_service: GrowwAuthService,
        instrument_cache: GrowwInstrumentCache,
        feed_cls: type | None = None,
        on_tick: Callable[[MarketTickObservation], Awaitable[None] | None] | None = None,
        on_state_change: Callable[[GrowwFeedState], Awaitable[None] | None] | None = None,
        max_reconnect_attempts: int = 5,
        base_reconnect_delay: float = 1.0,
    ) -> None:
        self.auth_service = auth_service
        self.instrument_cache = instrument_cache
        self.feed_cls = feed_cls
        self.on_tick = on_tick
        self.on_state_change = on_state_change
        self.max_reconnect_attempts = max_reconnect_attempts
        self.base_reconnect_delay = base_reconnect_delay
        self.state = GrowwFeedState.NOT_CONFIGURED if not auth_service.is_configured else GrowwFeedState.DISCONNECTED
        self.last_message_at: datetime | None = None
        self._feed: Any | None = None
        self._references: Counter[str] = Counter()
        self._event_loop: asyncio.AbstractEventLoop | None = None

    @property
    def subscription_count(self) -> int:
        return len(self._references)

    async def connect(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        if not self.auth_service.is_configured:
            await self._transition(GrowwFeedState.NOT_CONFIGURED)
            return
        await self._transition(GrowwFeedState.CONNECTING)
        try:
            client = await asyncio.to_thread(self.auth_service.get_client)
            feed_cls = self.feed_cls
            if feed_cls is None:
                from growwapi import GrowwFeed

                feed_cls = GrowwFeed
            # The SDK constructor opens its own event loop; keep that work off
            # the FastAPI loop so the provider connection remains isolated.
            self._feed = await asyncio.to_thread(feed_cls, client)
            await self._transition(GrowwFeedState.CONNECTED)
        except Exception:
            await self._transition(GrowwFeedState.FAILED)

    async def subscribe(self, instrument_ids: tuple[str, ...]) -> tuple[str, ...]:
        self._event_loop = asyncio.get_running_loop()
        unique = tuple(dict.fromkeys(value.strip().upper() for value in instrument_ids if value.strip()))
        if self._feed is None:
            await self.connect()
        resolved = tuple(
            value
            for value in unique
            if (instrument := self.instrument_cache.find(value)) is not None and instrument.exchange_token
        )
        new_ids = tuple(value for value in resolved if self._references[value] == 0)
        if self.subscription_count + len(new_ids) > self.MAX_PROVIDER_SUBSCRIPTIONS:
            raise ValueError("GROWW_FEED_SUBSCRIPTION_LIMIT")
        for value in resolved:
            self._references[value] += 1
        if self.state != GrowwFeedState.CONNECTED or not new_ids:
            return resolved
        rows = self._provider_rows(new_ids)
        if rows and hasattr(self._feed, "subscribe_ltp"):
            await asyncio.to_thread(self._feed.subscribe_ltp, rows, on_data_received=self._on_data_received)
        if rows and hasattr(self._feed, "subscribe_market_depth"):
            await asyncio.to_thread(self._feed.subscribe_market_depth, rows, on_data_received=self._on_data_received)
        return resolved

    async def unsubscribe(self, instrument_ids: tuple[str, ...]) -> None:
        removed: list[str] = []
        for value in dict.fromkeys(item.strip().upper() for item in instrument_ids):
            if self._references[value] <= 1:
                self._references.pop(value, None)
                removed.append(value)
            else:
                self._references[value] -= 1
        if self._feed is None or not removed:
            return
        rows = self._provider_rows(tuple(removed))
        if rows and hasattr(self._feed, "unsubscribe_ltp"):
            await asyncio.to_thread(self._feed.unsubscribe_ltp, rows)
        if rows and hasattr(self._feed, "unsubscribe_market_depth"):
            await asyncio.to_thread(self._feed.unsubscribe_market_depth, rows)

    async def reconnect(self, connector: Callable[[], Awaitable[None]] | None = None) -> bool:
        if self.state == GrowwFeedState.CONNECTED:
            await self._transition(GrowwFeedState.DISCONNECTED)
        await self._transition(GrowwFeedState.RECONNECTING)
        operation = connector or self.connect
        for attempt in range(self.max_reconnect_attempts):
            if attempt:
                await asyncio.sleep(min(self.base_reconnect_delay * (2 ** (attempt - 1)), 30.0))
            await operation()
            if self.state == GrowwFeedState.CONNECTED:
                return True
        await self._transition(GrowwFeedState.FAILED)
        return False

    async def _transition(self, state: GrowwFeedState) -> None:
        if self.state == state:
            return
        self.state = state
        if self.on_state_change:
            result = self.on_state_change(state)
            if asyncio.iscoroutine(result):
                await result

    async def ingest(self, payload: dict[str, Any]) -> MarketTickObservation | None:
        tick = self.normalize_tick(payload)
        if tick is None:
            return None
        self.last_message_at = tick.timestamp
        if self.on_tick:
            result = self.on_tick(tick)
            if asyncio.iscoroutine(result):
                await result
        return tick

    def normalize_tick(self, payload: dict[str, Any]) -> MarketTickObservation | None:
        symbol = str(payload.get("symbol") or payload.get("trading_symbol") or "").strip().upper()
        exchange = str(payload.get("exchange") or "NSE").strip().upper()
        segment = str(payload.get("segment") or "CASH").strip().upper()
        ltp = self._decimal(payload.get("ltp") or payload.get("last_price") or payload.get("value"))
        if not symbol or ltp is None:
            return None
        timestamp = self._timestamp(payload.get("tsInMillis") or payload.get("timestamp"))
        return MarketTickObservation(
            instrument_id=str(payload.get("instrument_id") or f"{exchange}:{segment}:{symbol}"),
            exchange=exchange,
            segment=segment,
            symbol=symbol,
            timestamp=timestamp,
            ltp=ltp,
            change=self._decimal(payload.get("change") or payload.get("day_change")),
            change_pct=self._decimal(payload.get("change_pct") or payload.get("day_change_perc")),
            open=self._decimal(payload.get("open")),
            high=self._decimal(payload.get("high")),
            low=self._decimal(payload.get("low")),
            close=self._decimal(payload.get("close")),
            volume=self._integer(payload.get("volume")),
            bid=self._decimal(payload.get("bid")),
            ask=self._decimal(payload.get("ask")),
            source="GROWW_FEED",
            freshness="FRESH",
        )

    def _provider_rows(self, instrument_ids: tuple[str, ...]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for instrument_id in instrument_ids:
            instrument = self.instrument_cache.find(instrument_id)
            if instrument and instrument.exchange_token:
                rows.append(
                    {
                        "exchange": instrument.exchange,
                        "segment": instrument.segment,
                        "exchange_token": instrument.exchange_token,
                    }
                )
        return rows

    def _on_data_received(self, payload: Any) -> None:
        if not isinstance(payload, dict) or self._event_loop is None or self._event_loop.is_closed():
            return
        if any(key in payload for key in ("ltp", "last_price", "value")):
            asyncio.run_coroutine_threadsafe(self.ingest(payload), self._event_loop)
            return
        try:
            snapshot = self._feed.get_all_feed() if self._feed and hasattr(self._feed, "get_all_feed") else {}
        except Exception:
            return
        token = payload.get("feed_key") or payload.get("exchange_token") or payload.get("token")
        instrument = self.instrument_cache.find_by_exchange_token(token)
        for row in self._feed_rows(snapshot):
            normalized = dict(row)
            if instrument:
                normalized.setdefault("instrument_id", instrument.instrument_id)
                normalized.setdefault("symbol", instrument.symbol)
                normalized.setdefault("exchange", instrument.exchange)
                normalized.setdefault("segment", instrument.segment)
            asyncio.run_coroutine_threadsafe(self.ingest(normalized), self._event_loop)

    @classmethod
    def _feed_rows(cls, value: Any) -> tuple[dict[str, Any], ...]:
        if isinstance(value, dict) and any(key in value for key in ("ltp", "last_price", "value")):
            return (value,)
        rows: list[dict[str, Any]] = []
        if isinstance(value, dict):
            for child in value.values():
                rows.extend(cls._feed_rows(child))
        elif isinstance(value, (list, tuple)):
            for child in value:
                rows.extend(cls._feed_rows(child))
        return tuple(rows)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        parsed = GrowwFeedManager._decimal(value)
        return int(parsed) if parsed is not None else None

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            divisor = 1000 if value > 10_000_000_000 else 1
            return datetime.fromtimestamp(value / divisor, tz=timezone.utc)
        return datetime.now(timezone.utc)


__all__ = ("GrowwFeedManager", "GrowwFeedState")
