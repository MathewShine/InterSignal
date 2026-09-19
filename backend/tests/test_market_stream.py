from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from app.market_api.live import MarketLiveCache, MarketStreamHub
from app.providers.groww.feed import GrowwFeedManager, GrowwFeedState
from app.providers.groww.instruments import GrowwInstrumentCache
from app.providers.market_data import MarketTickObservation


class FakeAuth:
    is_configured = True

    def get_client(self):
        return object()


class FakeFeed:
    def __init__(self, client) -> None:
        self.client = client
        self.subscribed = []
        self.unsubscribed = []

    def subscribe_ltp(self, rows, on_data_received=None):
        self.subscribed.extend(rows)

    def subscribe_market_depth(self, rows, on_data_received=None):
        return None

    def unsubscribe_ltp(self, rows):
        self.unsubscribed.extend(rows)

    def unsubscribe_market_depth(self, rows):
        return None


ROWS = ({"exchange": "NSE", "exchange_token": "2885", "trading_symbol": "RELIANCE", "groww_symbol": "NSE-RELIANCE", "name": "Reliance Industries", "instrument_type": "EQ", "segment": "CASH"},)


def test_stream_hub_subscribe_tick_unsubscribe_and_cache() -> None:
    async def scenario() -> None:
        cache = MarketLiveCache()
        hub = MarketStreamHub(cache=cache)
        queue = hub.register("client")
        assert hub.subscribe("client", ("RELIANCE",)) == ("RELIANCE",)
        tick = MarketTickObservation(
            instrument_id="NSE:CASH:RELIANCE", exchange="NSE", segment="CASH", symbol="RELIANCE",
            timestamp=datetime(2026, 9, 18, 5, 30, tzinfo=timezone.utc), ltp=Decimal("2890.15"), source="SIMULATED_NORMALIZED_TICK",
        )
        await hub.publish_observation(tick)
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["event"] == "INSTRUMENT_UPDATE"
        assert event["symbol"] == "RELIANCE"
        assert event["ltp"] == "2890.15"
        assert cache.quotes["RELIANCE"].ltp == Decimal("2890.15")
        assert hub.unsubscribe("client", ("RELIANCE",)) == ("RELIANCE",)
        assert hub.provider_subscriptions() == ()

    asyncio.run(scenario())


def test_groww_feed_connect_subscribe_normalize_unsubscribe_and_reconnect() -> None:
    async def scenario() -> None:
        received = []
        manager = GrowwFeedManager(
            auth_service=FakeAuth(),
            instrument_cache=GrowwInstrumentCache("unused.csv", fixture_rows=ROWS),
            feed_cls=FakeFeed,
            on_tick=lambda tick: received.append(tick),
            base_reconnect_delay=0,
        )
        await manager.connect()
        assert manager.state == GrowwFeedState.CONNECTED
        await manager.subscribe(("NSE:CASH:RELIANCE",))
        tick = await manager.ingest({"symbol": "RELIANCE", "exchange": "NSE", "segment": "CASH", "ltp": "2890.15", "timestamp": 1789709400000})
        assert tick is not None and tick.ltp == Decimal("2890.15")
        assert received[0].source == "GROWW_FEED"
        await manager.unsubscribe(("NSE:CASH:RELIANCE",))
        assert manager.subscription_count == 0
        assert await manager.reconnect() is True

    asyncio.run(scenario())


def test_feed_without_credentials_is_controlled() -> None:
    class MissingAuth:
        is_configured = False

    async def scenario() -> None:
        manager = GrowwFeedManager(auth_service=MissingAuth(), instrument_cache=GrowwInstrumentCache("unused.csv", fixture_rows=ROWS))
        await manager.connect()
        assert manager.state == GrowwFeedState.NOT_CONFIGURED

    asyncio.run(scenario())
