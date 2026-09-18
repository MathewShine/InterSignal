from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from app.main import create_app
from app.market_api.models import INTERSIGNAL_MARKET_SNAPSHOT_V1
from app.market_api.service import MarketIntelligenceService
from app.platform.hashing import file_sha256
from app.providers.market_data import MarketDataProvider, MarketProviderMode


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"
FIXED_NOW = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)


def _client() -> TestClient:
    return TestClient(create_app())


class _FailingProvider(MarketDataProvider):
    @property
    def provider_name(self) -> str:
        return "FAILING_TEST_PROVIDER"

    @property
    def mode(self) -> MarketProviderMode:
        return MarketProviderMode.DELAYED

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ()

    @staticmethod
    def _fail():
        raise RuntimeError("private provider stack detail")

    def get_index_snapshot(self):
        return self._fail()

    def get_universe_snapshot(self):
        return self._fail()

    def get_sector_snapshot(self):
        return self._fail()

    def get_breadth_snapshot(self):
        return self._fail()

    def get_volume_snapshot(self):
        return self._fail()

    def get_market_status(self):
        return self._fail()

    def get_freshness(self):
        return self._fail()


def test_market_snapshot_contract_is_versioned_india_first_and_truthful() -> None:
    response = _client().get("/api/market/snapshot")
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert payload["version"] == INTERSIGNAL_MARKET_SNAPSHOT_V1
    assert payload["market"] == {
        "country": "INDIA",
        "exchange": "NSE",
        "primary_index": "NIFTY_500",
        "reference_indices": ["NIFTY_50"],
    }
    assert payload["provider"]["mode"] == "SEEDED"
    assert payload["provider"]["provider_name"] == "INTERSIGNAL_RECORDED_NSE"
    assert {row["symbol"] for row in payload["indices"]} == {"NIFTY_500", "NIFTY_50"}
    assert payload["universe"]["name"] == "NIFTY 500"
    assert payload["universe"]["membership_kind"] == "CURRENT_EFFECTIVE_ONLY"
    assert payload["session"]["status"] == "CLOSED"
    assert payload["freshness"]["freshness_status"] in {"FRESH", "AGING", "STALE"}
    assert payload["meta"]["read_only"] is True
    assert payload["meta"]["strategy_output"] is False
    assert payload["meta"]["market_regime_engine"] is False
    assert payload["meta"]["broker_integration"] == "NOT_CONNECTED"
    assert any(row["limitation_id"] == "LIMIT-LIVE-SOURCE-NOT-CONFIGURED" for row in payload["limitations"])


def test_market_sections_expose_availability_quality_and_nullable_unsupported_metrics() -> None:
    payload = _client().get("/api/market/snapshot").json()

    assert set(payload["availability"]) == {"indices", "universe", "breadth", "sectors", "volume", "session"}
    assert all(row["status"] in {"AVAILABLE", "PARTIAL", "UNAVAILABLE"} for row in payload["availability"].values())
    if payload["breadth"] is not None:
        assert payload["breadth"]["above_vwap_pct"] is None
        assert payload["breadth"]["quality"]["coverage_count"] <= payload["breadth"]["quality"]["expected_count"]
        assert payload["breadth"]["advancers"] + payload["breadth"]["decliners"] + payload["breadth"]["unchanged"] == payload["breadth"]["quality"]["coverage_count"]
    assert payload["sectors"]
    assert all("return_pct" in row and "quality" in row for row in payload["sectors"])
    if payload["volume"] is not None:
        assert payload["volume"]["traded_value_unit"] == "INR_LAKH"
        assert payload["volume"]["quality"]["coverage_count"] <= payload["volume"]["quality"]["expected_count"]


def test_provider_failure_returns_controlled_unavailable_snapshot_without_details() -> None:
    snapshot = MarketIntelligenceService(
        provider=_FailingProvider(),
        clock=lambda: FIXED_NOW,
    ).get_snapshot()
    rendered = snapshot.model_dump_json().lower()

    assert snapshot.status == "UNAVAILABLE"
    assert all(detail.status == "UNAVAILABLE" for _, detail in snapshot.availability)
    assert len(snapshot.meta.unavailable_sections) == 6
    assert "private provider stack detail" not in rendered
    assert "traceback" not in rendered
    assert {row.section for row in snapshot.limitations} >= {
        "freshness", "indices", "universe", "breadth", "sectors", "volume", "session"
    }


def test_market_route_is_get_only_documented_fast_and_contains_no_secrets() -> None:
    client = _client()
    started = perf_counter()
    response = client.get("/api/market/snapshot")
    elapsed = perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 0.5
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/market/snapshot").status_code == 405
    assert "/api/market/snapshot" in client.get("/openapi.json").json()["paths"]
    rendered = response.text.lower()
    forbidden = (
        "api_key", "apikey", "secret", "auth_token", "access_token", "totp",
        "broker_credentials", "c:\\users\\", "/users/", ".env", "source_file",
    )
    assert not any(value in rendered for value in forbidden)
    assert not any(value in rendered.upper() for value in ('"BUY"', '"SELL"', '"LONG"', '"SHORT"', '"ENTRY"', '"EXIT"', '"TARGET"', '"STOP"'))


def test_market_get_does_not_mutate_platform_or_recorded_source_files() -> None:
    source_files = [
        PROJECT_ROOT / "data/reference/nse/indices/normalized/benchmark_daily.csv",
        PROJECT_ROOT / "data/reference/nse/indices/normalized/sector_index_daily.csv",
        PROJECT_ROOT / "data/reference/nse/indices/normalized/stock_sector_mapping.csv",
        PROJECT_ROOT / "data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        PROJECT_ROOT / "data/reference/nse/calendar/nse_cash_trading_calendar.csv",
    ]
    platform_files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    files = platform_files + source_files
    before = {path: file_sha256(path) for path in files}

    response = _client().get("/api/market/snapshot")

    assert response.status_code == 200
    assert {path: file_sha256(path) for path in files} == before
