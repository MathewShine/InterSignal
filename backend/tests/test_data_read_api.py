from pathlib import Path

from fastapi.testclient import TestClient

from app.data_api.models import INTERSIGNAL_DATA_HEALTH_V1
from app.home.factory import build_home_application_service
from app.main import create_app
from app.platform.hashing import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"


def _client() -> TestClient:
    return TestClient(create_app())


def test_data_overview_matches_persisted_platform_truth() -> None:
    payload = _client().get("/api/data/overview").json()
    assert payload["version"] == INTERSIGNAL_DATA_HEALTH_V1
    assert payload["status"] == "AVAILABLE"
    assert payload["meta"]["read_only"] is True
    assert payload["meta"]["runtime_fixtures"] is False
    sources = {row["source_id"]: row for row in payload["sources"]}
    assert sources["daily-history"]["status"] == "AVAILABLE"
    assert sources["corporate-actions"]["status"] == "AVAILABLE_WITH_CAVEATS"
    assert sources["intraday-continuity"]["status"] == "BLOCKED_FOR_RESEARCH_USE"
    assert sources["intraday-continuity"]["coverage_pct"].startswith("77.826177")
    assert sources["intraday-continuity"]["gap_count"] == 217
    assert sources["catalyst-history"]["status"] == "SOURCE_BLOCKED"


def test_data_lineage_is_safe_healthy_and_reference_complete() -> None:
    payload = _client().get("/api/data/lineage").json()["lineage"]
    assert payload["integrity_status"] == "HEALTHY"
    assert payload["broken_reference_count"] == 0
    assert payload["node_count"] > 0
    assert payload["edge_count"] > 0
    assert payload["artifact_count"] > 0
    assert payload["nodes"]
    assert all("entity_key" not in row and "path" not in row for row in payload["nodes"])


def test_data_limitations_preserve_research_semantics() -> None:
    payload = _client().get("/api/data/limitations").json()
    rows = {row["limitation_id"]: row for row in payload["items"]}
    assert payload["total_count"] == 3
    assert "not a strategy failure" not in rows["LIMIT-INTRADAY-CONTINUITY"]["impact"].lower()
    assert "trustworthy formal evaluation" in rows["LIMIT-INTRADAY-CONTINUITY"]["impact"].lower()
    assert "not authorized" in rows["LIMIT-CATALYST-AUTHORIZATION"]["summary"].lower()


def test_home_and_data_overview_are_consistent() -> None:
    home = build_home_application_service(PLATFORM_ROOT).get_snapshot().data_health
    data = _client().get("/api/data/overview").json()
    sources = {row["source_id"]: row for row in data["sources"]}
    assert sources["daily-history"]["status"] == home.daily_history_status
    assert sources["corporate-actions"]["status"] == home.corporate_actions_status
    assert sources["intraday-continuity"]["status"] == home.intraday_status
    assert sources["catalyst-history"]["status"] == home.catalyst_status
    assert data["lineage"]["integrity_status"] == home.lineage_integrity
    assert data["lineage"]["broken_reference_count"] == home.broken_reference_count


def test_data_routes_are_no_store_get_only_and_documented() -> None:
    client = _client()
    paths = ("/api/data/overview", "/api/data/sources", "/api/data/lineage", "/api/data/limitations")
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["version"] == INTERSIGNAL_DATA_HEALTH_V1
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405
    assert set(paths) <= set(client.get("/openapi.json").json()["paths"])


def test_data_reads_do_not_mutate_files_or_expose_private_values() -> None:
    files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    files.append(
        PROJECT_ROOT
        / "data/research/strategy_families/family_d/v1/exact_gap_recovery/readiness/family_d_post_recovery_readiness_v1.json"
    )
    before = {path: file_sha256(path) for path in files}
    client = _client()
    for path in ("/api/data/overview", "/api/data/sources", "/api/data/lineage", "/api/data/limitations"):
        rendered = client.get(path).text.lower()
        assert not any(value in rendered for value in ("c:\\users\\", "/users/", ".env", "totp", "access_token", "broker_secret", "path_or_reference"))
    assert {path: file_sha256(path) for path in files} == before
