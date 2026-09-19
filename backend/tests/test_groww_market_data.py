from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Event

import pytest

from app.providers.groww import GrowwInstrumentCache, GrowwMarketDataProvider
from app.providers.groww.exceptions import GrowwRateLimitError
from app.providers.groww.market_data import _GrowwLiveRateLimiter


ROWS = (
    {
        "exchange": "BSE", "exchange_token": "500325", "trading_symbol": "RELIANCE",
        "groww_symbol": "BSE-RELIANCE", "name": "Reliance Industries", "instrument_type": "EQ",
        "segment": "CASH", "series": "A", "isin": "INE002A01018", "underlying_symbol": "",
        "expiry_date": "", "strike_price": "", "lot_size": "1", "tick_size": "0.05",
    },
    {
        "exchange": "NSE", "exchange_token": "2885", "trading_symbol": "RELIANCE",
        "groww_symbol": "NSE-RELIANCE", "name": "Reliance Industries", "instrument_type": "EQ",
        "segment": "CASH", "series": "EQ", "isin": "INE002A01018", "underlying_symbol": "",
        "expiry_date": "", "strike_price": "", "lot_size": "1", "tick_size": "0.05",
    },
    {
        "exchange": "NSE", "exchange_token": "26000", "trading_symbol": "NIFTY",
        "groww_symbol": "NSE-NIFTY", "name": "NIFTY 50", "instrument_type": "INDEX",
        "segment": "CASH", "series": "", "isin": "", "underlying_symbol": "NIFTY",
        "expiry_date": "", "strike_price": "", "lot_size": "", "tick_size": "0.05",
    },
)


class FakeClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_DAY = "1day"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_quote(self, **kwargs):
        self.calls.append(("quote", kwargs))
        return {"payload": {"last_price": "2890.15", "day_change": "12.10", "day_change_perc": "0.42", "ohlc": {"open": "2875", "high": "2905", "low": "2861", "close": "2878.05"}, "volume": 123456, "market_status": "OPEN", "timestamp": "2026-09-18T05:30:00Z", "market_depth": {"buy": [{"price": "2889.9", "quantity": 50}], "sell": [{"price": "2890.2", "quantity": 25}]}}}

    def get_ltp(self, **kwargs):
        self.calls.append(("ltp", kwargs))
        return {"payload": {
            symbol: "2890.15" if symbol.endswith("RELIANCE") else "23000"
            for symbol in kwargs["exchange_trading_symbols"]
        }}

    def get_ohlc(self, **kwargs):
        self.calls.append(("ohlc", kwargs))
        return {"payload": {
            symbol: {"open": "2875", "high": "2905", "low": "2861", "close": "2878.05"}
            for symbol in kwargs["exchange_trading_symbols"]
        }}

    def get_historical_candles(self, **kwargs):
        self.calls.append(("candles", kwargs))
        return {"payload": {"candles": [["2026-09-17T10:00:00Z", "2800", "2900", "2790", "2880", 1000, 44]]}}

    def get_option_chain(self, **kwargs):
        self.calls.append(("option_chain", kwargs))
        return {"payload": {"underlying_ltp": 25641.7, "strikes": {"23400": {"CE": {"trading_symbol": "NIFTY25N1823400CE", "ltp": 2200, "open_interest": 7, "volume": 5, "greeks": {"delta": 0.9936, "iv": 25.3409}}, "PE": {"trading_symbol": "NIFTY25N1823400PE", "ltp": 2.05, "open_interest": 7453, "volume": 9339, "greeks": {"delta": -0.0064, "iv": 25.3409}}}}}}


class FakeAuth:
    is_configured = True

    def __init__(self, client=None) -> None:
        self.client = client or FakeClient()

    def get_client(self):
        return self.client


def provider() -> GrowwMarketDataProvider:
    return GrowwMarketDataProvider(
        auth_service=FakeAuth(),
        instrument_cache=GrowwInstrumentCache("unused.csv", fixture_rows=ROWS),
        clock=lambda: datetime(2026, 9, 18, 6, tzinfo=timezone.utc),
    )


def test_groww_quote_ltp_ohlc_depth_and_cache_are_normalized() -> None:
    value = provider()
    first = value.get_quote("RELIANCE")
    second = value.get_quote("RELIANCE")
    ltp = value.get_ltp(("RELIANCE",))
    ohlc = value.get_ohlc(("RELIANCE",))

    assert first == second
    assert first is not None
    assert first.instrument.exchange == "NSE"
    assert first.ltp == Decimal("2890.15")
    assert first.open == Decimal("2875")
    assert first.buy_depth[0].quantity == 50
    assert first.sell_depth[0].price == Decimal("2890.2")
    assert ltp["NSE:CASH:RELIANCE"] == Decimal("2890.15")
    assert ohlc["NSE:CASH:RELIANCE"]["high"] == Decimal("2905")
    assert len([call for call in value.auth_service.client.calls if call[0] == "quote"]) == 1
    assert value.auth_service.client.calls[1][1]["exchange_trading_symbols"] == ("NSE_RELIANCE",)


def test_groww_concurrent_quote_requests_are_coalesced() -> None:
    class SlowClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.started = Event()
            self.release = Event()

        def get_quote(self, **kwargs):
            self.started.set()
            assert self.release.wait(timeout=2)
            return super().get_quote(**kwargs)

    client = SlowClient()
    value = GrowwMarketDataProvider(
        auth_service=FakeAuth(client),
        instrument_cache=GrowwInstrumentCache("unused.csv", fixture_rows=ROWS),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(value.get_quote, "RELIANCE")
        assert client.started.wait(timeout=1)
        second = executor.submit(value.get_quote, "RELIANCE")
        client.release.set()
        assert first.result(timeout=2) == second.result(timeout=2)

    assert len([call for call in client.calls if call[0] == "quote"]) == 1


def test_groww_rate_limit_is_local_and_upstream_429_is_not_retried() -> None:
    limiter = _GrowwLiveRateLimiter(per_second=1, per_minute=300)
    limiter.acquire()
    with pytest.raises(GrowwRateLimitError):
        limiter.acquire()

    class RateLimitedClient(FakeClient):
        def get_quote(self, **kwargs):
            self.calls.append(("quote", kwargs))
            error = RuntimeError("provider rejected request")
            error.status_code = 429
            raise error

    client = RateLimitedClient()
    value = GrowwMarketDataProvider(
        auth_service=FakeAuth(client),
        instrument_cache=GrowwInstrumentCache("unused.csv", fixture_rows=ROWS),
    )
    with pytest.raises(GrowwRateLimitError):
        value.get_quote("RELIANCE")
    assert len(client.calls) == 1


def test_groww_prefers_nse_chunks_long_ranges_and_infers_closed_session() -> None:
    value = provider()
    candles = value.get_candles(
        "RELIANCE", interval="4h",
        start=datetime(2025, 9, 1, tzinfo=timezone.utc),
        end=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    requests = [call for call in value.auth_service.client.calls if call[0] == "candles"]
    assert len(requests) == 3
    assert candles
    assert all(call[1]["exchange"] == "NSE" for call in requests)
    assert value._session_status(None, datetime(2026, 9, 17, 10, tzinfo=timezone.utc)) == "CLOSED"


def test_groww_market_context_batches_and_reuses_index_requests() -> None:
    value = provider()

    indices = value.get_index_snapshot()
    value.get_sector_snapshot()

    assert [row.symbol for row in indices] == ["NIFTY_50"]
    assert len([call for call in value.auth_service.client.calls if call[0] == "ltp"]) == 1
    assert len([call for call in value.auth_service.client.calls if call[0] == "ohlc"]) == 1


def test_groww_candles_and_instrument_search_are_normalized() -> None:
    value = provider()
    candles = value.get_candles(
        "RELIANCE", interval="1d",
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    assert value.search_instruments("Reliance")[0].instrument_id == "NSE:CASH:RELIANCE"
    assert candles[0].timestamp.tzinfo is not None
    assert candles[0].open == Decimal("2800")
    assert candles[0].close == Decimal("2880")
    assert candles[0].volume == 1000
    assert candles[0].open_interest == 44


def test_groww_option_chain_hides_raw_provider_shape() -> None:
    rows = provider().get_option_chain("NIFTY", "2026-09-24")

    assert rows == (
        {
            "strike": Decimal("23400"),
            "ce": {
                "trading_symbol": "NIFTY25N1823400CE", "ltp": Decimal("2200"),
                "open_interest": 7, "volume": 5, "delta": Decimal("0.9936"),
                "gamma": None, "theta": None, "vega": None, "rho": None, "iv": Decimal("25.3409"),
            },
            "pe": {
                "trading_symbol": "NIFTY25N1823400PE", "ltp": Decimal("2.05"),
                "open_interest": 7453, "volume": 9339, "delta": Decimal("-0.0064"),
                "gamma": None, "theta": None, "vega": None, "rho": None, "iv": Decimal("25.3409"),
            },
        },
    )
    assert "strikes" not in rows[0]
