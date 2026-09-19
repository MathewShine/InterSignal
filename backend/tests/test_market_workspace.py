from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.market_api.workspace_service import RANGE_INTERVALS


def client(**values: object) -> TestClient:
    return TestClient(create_app(Settings(**values)))


def test_seeded_market_workspace_search_quote_candles_and_closed_state() -> None:
    api = client(market_data_provider="seeded")

    search = api.get("/api/market/instruments/search", params={"q": "RELIANCE"})
    quote = api.get("/api/market/instruments/RELIANCE/quote")
    candles = api.get("/api/market/instruments/RELIANCE/candles", params={"range": "1M"})
    status = api.get("/api/market/provider/status")

    assert search.status_code == quote.status_code == candles.status_code == status.status_code == 200
    assert search.json()["version"] == "INTERSIGNAL_MARKET_SEARCH_V1"
    assert any(row["symbol"] == "RELIANCE" for row in search.json()["items"])
    assert quote.json()["quote"]["market_session"] == "CLOSED"
    assert quote.json()["quote"]["ltp"] is not None
    assert candles.json()["version"] == "INTERSIGNAL_MARKET_CANDLES_V1"
    assert candles.json()["interval"] == "1d"
    assert candles.json()["candles"]
    assert {"timestamp", "open", "high", "low", "close", "volume"} <= candles.json()["candles"][0].keys()
    assert status.json()["mode"] == "SEEDED"
    assert status.json()["market_session"] == "CLOSED"
    assert all(response.headers["cache-control"] == "no-store" for response in (search, quote, candles, status))


def test_live_range_defaults_use_provider_supported_intraday_intervals() -> None:
    assert RANGE_INTERVALS == {
        "1D": "5m", "5D": "15m", "1M": "30m",
        "3M": "1h", "6M": "4h", "1Y": "4h",
    }


def test_workspace_indices_sectors_and_details_are_isolated() -> None:
    api = client(market_data_provider="seeded")

    indices = api.get("/api/market/indices").json()
    index_detail = api.get("/api/market/indices/NIFTY_500").json()
    sectors = api.get("/api/market/sectors").json()
    sector_id = sectors["items"][0]["sector_id"]
    sector_detail = api.get(f"/api/market/sectors/{sector_id}").json()

    assert {row["symbol"] for row in indices["items"]} == {"NIFTY_50", "NIFTY_500"}
    assert index_detail["breadth"] is not None
    assert sectors["items"]
    assert sector_detail["item"]["sector_id"] == sector_id
    assert sector_detail["constituents"] or sector_detail["reason"] is None


def test_market_websocket_exposes_only_normalized_subscription_protocol() -> None:
    api = client(market_data_provider="seeded")

    with api.websocket_connect("/api/market/stream") as socket:
        status = socket.receive_json()
        socket.send_json({"action": "subscribe", "instruments": ["RELIANCE"]})
        subscribed = socket.receive_json()
        socket.send_json({"action": "unsubscribe", "instruments": ["RELIANCE"]})
        unsubscribed = socket.receive_json()

    assert status == {
        "version": "INTERSIGNAL_MARKET_STREAM_V1",
        "event": "PROVIDER_STATUS",
        "provider": "INTERSIGNAL_RECORDED_NSE",
        "mode": "SEEDED",
        "stream_state": "NOT_AVAILABLE",
    }
    assert subscribed["action"] == "subscribed"
    assert subscribed["symbols"] == ["RELIANCE"]
    assert unsubscribed["action"] == "unsubscribed"
    assert "groww" not in str(subscribed).lower()


def test_groww_missing_credentials_is_controlled_and_never_falls_back() -> None:
    api = client(
        market_data_provider="groww",
        groww_api_access_token="",
        groww_api_key="",
        groww_api_secret="",
        groww_totp_token="",
        groww_totp_secret="",
    )

    status = api.get("/api/market/provider/status").json()
    quote = api.get("/api/market/instruments/RELIANCE/quote").json()

    assert status["provider"] == "GROWW"
    assert status["mode"] == "UNAVAILABLE"
    assert status["configured"] is False
    assert status["reason"] == "GROWW_NOT_CONFIGURED"
    assert status["credential_ready"] is False
    assert quote["status"] == "UNAVAILABLE"
    assert quote["provider"] == "GROWW"
    assert quote["reason"] in {"GROWW_NOT_CONFIGURED", "INSTRUMENT_QUOTE_UNAVAILABLE"}
