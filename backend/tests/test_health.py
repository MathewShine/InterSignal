from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.main import create_app
from tests.conftest import clear_supabase_env


def make_client(monkeypatch):
    clear_supabase_env(monkeypatch)
    monkeypatch.setenv("APP_NAME", "InterSignal API")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_returns_service_status(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "InterSignal API",
        "version": "0.1.0",
        "environment": "test",
    }


def test_database_health_allows_missing_supabase_credentials(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/health/database")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_configured"
    assert body["configured"] is False


def test_versioned_health_route_is_available(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
