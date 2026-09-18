from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from app.api.routes.research import get_research_application_service
from app.main import create_app
from app.platform.hashing import file_sha256
from app.platform.repositories import JsonFilePlatformRepository
from app.research_api.models import INTERSIGNAL_RESEARCH_WORKBENCH_V1
from app.research_api.service import ResearchApplicationService
from app.research_workbench.service import ResearchWorkbenchService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"
FIXED_TIME = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _service(workbench: object | None = None) -> ResearchApplicationService:
    canonical = workbench or ResearchWorkbenchService.from_repository(
        JsonFilePlatformRepository(PLATFORM_ROOT)
    )
    return ResearchApplicationService(canonical, clock=lambda: FIXED_TIME)  # type: ignore[arg-type]


def _client(service: ResearchApplicationService | None = None) -> TestClient:
    app = create_app()
    if service is not None:
        app.dependency_overrides[get_research_application_service] = lambda: service
    return TestClient(app)


def test_overview_is_versioned_backend_backed_and_programme_paused() -> None:
    payload = _client(_service()).get("/api/research/overview").json()
    assert payload["version"] == INTERSIGNAL_RESEARCH_WORKBENCH_V1
    assert payload["status"] == "AVAILABLE"
    assert payload["generated_at"] == "2026-09-18T12:00:00Z"
    assert payload["family_count"] == 7
    assert [row["family_id"] for row in payload["families"]] == list("ABCDEFG")
    assert payload["reusable_evidence_count"] == 1
    assert payload["blocked_study_count"] == 2
    assert payload["production_ready_count"] == 0
    assert payload["programme"] == {
        "status": "PAUSED",
        "cycle_status": "COMPLETE_NO_VALIDATED_STRATEGY",
        "validated_strategy_count": 0,
        "production_candidate_count": 0,
        "strategy_v2_status": "NOT_CREATED",
        "family_h_status": "NOT_PLANNED",
        "paper_readiness": "NOT_READY",
        "live_readiness": "NOT_READY",
        "primary_programme": "PRODUCT_PLATFORM_PROGRAM",
        "secondary_programme": "FORWARD_DATA_PROGRAM",
    }
    assert all(row["family_id"] != "H" for row in payload["families"])


def test_family_a_preserves_formal_and_post_remediation_distinction() -> None:
    payload = _client(_service()).get("/api/research/families/A").json()
    assert payload["family"]["current_status"] == "CLOSED_NOT_ADVANCED"
    assert payload["family"]["decision_status"] == "REJECTED_FOR_CURRENT_CYCLE"
    records = {row["validation_type"]: row for row in payload["validation"]}
    assert records["Formal one-shot"]["outcome"] == "INCONCLUSIVE"
    assert records["Formal one-shot"]["integrity"] == "IMPLEMENTATION_DEFECT"
    assert records["Formal one-shot"]["pristine_intent"] is True
    assert records["Post-remediation evaluation"]["outcome"] == "FAIL"
    assert records["Post-remediation evaluation"]["interpretation"] == "UNSUPPORTIVE"
    assert records["Post-remediation evaluation"]["integrity"] == "NON_PRISTINE"
    assert records["Post-remediation evaluation"]["pristine_intent"] is False
    rendered = str(payload)
    assert "2025–26 holdout contaminated" in rendered
    assert "formal validation failure" not in rendered.lower()


def test_family_c_d_f_and_g_semantics_are_explicit() -> None:
    client = _client(_service())
    overview = client.get("/api/research/overview").json()
    retained = overview["retained_evidence"]
    assert [row["evidence_id"] for row in retained] == [
        "EDGE-EVIDENCE-C-COMPRESSION-001"
    ]
    assert retained[0]["production_relevance"] == (
        "Reusable signal evidence · not production strategy"
    )
    families = {row["family_id"]: row for row in overview["families"]}
    assert "77.826%" in str(families["D"])
    assert "217" in str(families["D"])
    assert "not a strategy failure" in str(families["D"]).lower()
    assert families["F"]["current_status_label"] == (
        "Blocked pending authorized source"
    )
    assert "No performance study" in str(families["F"])
    assert "24.11%" in str(families["G"])
    assert "11.95%" in str(families["G"])
    assert "22.92%" in str(families["G"])
    assert "30.73%" in str(families["G"])


def test_all_research_routes_have_stable_contract_and_no_store() -> None:
    client = _client(_service())
    paths = (
        "/api/research/overview",
        "/api/research/families",
        "/api/research/families/A",
        "/api/research/evidence",
        "/api/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001",
        "/api/research/validation",
        "/api/research/blocked",
        "/api/research/timeline",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["version"] == INTERSIGNAL_RESEARCH_WORKBENCH_V1
        assert response.json()["meta"]["read_only"] is True
    openapi_paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/research/overview",
        "/api/research/families",
        "/api/research/families/{family_id}",
        "/api/research/evidence",
        "/api/research/evidence/{evidence_id}",
        "/api/research/validation",
        "/api/research/blocked",
        "/api/research/timeline",
    } <= set(openapi_paths)


def test_evidence_detail_exposes_safe_artifact_metadata_and_lineage() -> None:
    response = _client(_service()).get(
        "/api/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001"
    )
    payload = response.json()["evidence"]
    assert payload["supporting_artifacts"]
    assert payload["lineage"]["nodes"]
    assert payload["lineage"]["edges"]
    artifact = payload["supporting_artifacts"][0]
    assert set(artifact) == {
        "artifact_id",
        "name",
        "artifact_type",
        "version",
        "integrity",
        "created_at",
        "lineage_node_id",
    }
    serialized = response.text.lower()
    assert "path_or_reference" not in serialized
    assert "c:\\users\\" not in serialized
    assert "/users/" not in serialized
    assert ".env" not in serialized


def test_validation_and_blocked_lists_preserve_integrity_and_no_performance_claims() -> None:
    client = _client(_service())
    validation = client.get("/api/research/validation").json()["items"]
    family_a = [row for row in validation if row["family_id"] == "A"]
    assert [(row["outcome"], row["interpretation"]) for row in family_a] == [
        ("INCONCLUSIVE", "Inconclusive"),
        ("FAIL", "UNSUPPORTIVE"),
    ]
    blocked = {
        row["family_id"]: row
        for row in client.get("/api/research/blocked").json()["items"]
    }
    assert set(blocked) == {"D", "F"}
    assert blocked["D"]["impact"] == (
        "Cannot perform a trustworthy formal evaluation."
    )
    assert blocked["F"]["impact"] == (
        "Cannot execute a robust historical catalyst study."
    )


class _PartiallyFailingWorkbench:
    def __init__(self, delegate: ResearchWorkbenchService) -> None:
        self._delegate = delegate

    def get_programme_summary(self):
        raise RuntimeError("sensitive internal failure")

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


def test_overview_is_failure_isolated_and_sanitized() -> None:
    workbench = _PartiallyFailingWorkbench(
        ResearchWorkbenchService.from_repository(
            JsonFilePlatformRepository(PLATFORM_ROOT)
        )
    )
    response = _client(_service(workbench)).get("/api/research/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PARTIAL"
    assert payload["programme"] is None
    assert payload["family_count"] == 7
    assert payload["meta"]["unavailable_sections"] == ["programme"]
    assert "sensitive internal failure" not in response.text


def test_not_found_routes_are_sanitized() -> None:
    client = _client(_service())
    family = client.get("/api/research/families/H")
    evidence = client.get("/api/research/evidence/UNKNOWN")
    assert family.status_code == 404
    assert family.json() == {"detail": "Research family not found."}
    assert evidence.status_code == 404
    assert evidence.json() == {"detail": "Research evidence not found."}


def test_research_http_surface_is_read_only() -> None:
    files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    before = {path: file_sha256(path) for path in files}
    client = _client(_service())
    for path in (
        "/api/research/overview",
        "/api/research/families/A",
        "/api/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001",
        "/api/research/validation",
        "/api/research/blocked",
        "/api/research/timeline",
    ):
        assert client.get(path).status_code == 200
    after_files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    assert after_files == files
    assert {path: file_sha256(path) for path in after_files} == before
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/research/overview").status_code == 405


def test_overview_performance_avoids_endpoint_n_plus_one() -> None:
    client = _client(_service())
    client.get("/api/research/overview")
    started = perf_counter()
    response = client.get("/api/research/overview")
    assert response.status_code == 200
    assert perf_counter() - started < 1.0
