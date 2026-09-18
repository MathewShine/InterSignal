from pathlib import Path

from fastapi.testclient import TestClient

from app.governance_api.models import INTERSIGNAL_GOVERNANCE_V1
from app.home.factory import build_home_application_service
from app.main import create_app
from app.platform.hashing import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"


def _client() -> TestClient:
    return TestClient(create_app())


def test_governance_overview_matches_canonical_state() -> None:
    payload = _client().get("/api/governance/overview").json()
    assert payload["version"] == INTERSIGNAL_GOVERNANCE_V1
    assert payload["status"] == "AVAILABLE"
    assert payload["meta"]["read_only"] is True
    summary = payload["summary"]
    assert summary["paper_readiness"] == "NOT_READY"
    assert summary["live_readiness"] == "NOT_READY"
    assert summary["broker_readiness"] == "NOT_READY"
    assert summary["broker_connection_state"] == "NOT_CONNECTED"
    assert summary["production_readiness"] == "NOT_READY"
    assert summary["blocking_violation_count"] == 0
    assert summary["pending_authorization_count"] == 1
    assert summary["passing_policy_count"] == summary["total_policy_count"] == 8
    assert summary["policy_passes_imply_readiness"] is False


def test_readiness_policies_and_authorization_are_real_records() -> None:
    client = _client()
    readiness = client.get("/api/governance/readiness").json()["items"]
    by_type = {row["readiness_type"]: row for row in readiness}
    for key in ("PAPER_TRADING_READINESS", "LIVE_TRADING_READINESS", "BROKER_READINESS", "PRODUCTION_READINESS"):
        assert by_type[key]["status"] == "NOT_READY"
        assert by_type[key]["failed_criteria"]
    policies = client.get("/api/governance/policies").json()
    assert policies["passing_count"] == policies["total_count"] == 8
    assert all(row["evaluation_status"] == "PASS" for row in policies["items"])
    authorizations = client.get("/api/governance/authorizations").json()
    assert authorizations["pending_count"] == 1
    assert authorizations["items"][0]["authorization_id"] == "AUTH-FAMILY-F-DATA-ACQUISITION-001"


def test_audit_uses_combined_real_events_and_honest_override_empty_state() -> None:
    payload = _client().get("/api/governance/audit").json()
    assert payload["total_count"] > 30
    assert payload["manual_overrides"] == []
    assert {row["source"] for row in payload["items"]} >= {"GOVERNANCE", "REGISTRY", "PORTFOLIO"}
    assert any(row["event_type"] == "AUTHORIZATION_REQUESTED" for row in payload["items"])


def test_home_and_governance_overview_are_consistent() -> None:
    home = build_home_application_service(PLATFORM_ROOT).get_snapshot().governance
    summary = _client().get("/api/governance/overview").json()["summary"]
    assert summary["paper_readiness"] == home.paper_readiness
    assert summary["live_readiness"] == home.live_readiness
    assert summary["broker_readiness"] == home.broker_readiness
    assert summary["production_readiness"] == home.production_readiness
    assert summary["blocking_violation_count"] == home.blocking_violation_count
    assert summary["pending_authorization_count"] == home.pending_authorization_count


def test_governance_routes_are_no_store_get_only_and_documented() -> None:
    client = _client()
    paths = ("/api/governance/overview", "/api/governance/readiness", "/api/governance/policies", "/api/governance/authorizations", "/api/governance/audit")
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["version"] == INTERSIGNAL_GOVERNANCE_V1
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405
    assert set(paths) <= set(client.get("/openapi.json").json()["paths"])


def test_governance_reads_do_not_mutate_files_or_expose_private_values() -> None:
    root = PLATFORM_ROOT / "governance"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    before = {path: file_sha256(path) for path in files}
    client = _client()
    for path in ("/api/governance/overview", "/api/governance/readiness", "/api/governance/policies", "/api/governance/authorizations", "/api/governance/audit"):
        rendered = client.get(path).text.lower()
        assert not any(value in rendered for value in ("c:\\users\\", "/users/", ".env", "totp", "access_token", "broker_secret", "path_or_reference"))
    assert {path: file_sha256(path) for path in files} == before
