from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.api.routes.home import get_home_application_service
from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.service import GovernanceService
from app.home.models import (
    INTERSIGNAL_HOME_SNAPSHOT_V1,
    AttentionSeverity,
    AvailabilityStatus,
    HomeSnapshot,
)
from app.home.service import HomeApplicationService
from app.home.sources import (
    GovernanceAuditHomeSource,
    PlatformActivityHomeSource,
    PlatformDataHealthHomeSource,
    PortfolioOSHomeSource,
    ResearchWorkbenchHomeSource,
)
from app.main import create_app
from app.platform.hashing import file_sha256
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.repositories import (
    InMemoryPortfolioOSRepository,
    JsonFilePortfolioOSRepository,
)
from app.portfolio_os.service import PortfolioOSService
from app.research_workbench.service import ResearchWorkbenchService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = PROJECT_ROOT / "data/platform"
FIXED_TIME = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


class _FailingSource:
    def read(self):
        raise RuntimeError("sensitive implementation detail")


def _domain_services() -> tuple[
    ResearchWorkbenchService,
    PortfolioOSService,
    GovernanceService,
]:
    platform = JsonFilePlatformRepository(PLATFORM_ROOT)
    portfolio_repository = JsonFilePortfolioOSRepository(
        PLATFORM_ROOT / "portfolio_os"
    )
    governance_repository = JsonFileGovernanceRepository(
        PLATFORM_ROOT / "governance"
    )
    research = ResearchWorkbenchService.from_repository(platform)
    portfolio = PortfolioOSService.from_repository(portfolio_repository)
    portfolio_events = tuple(
        event
        for row in portfolio.list_portfolios()
        for event in portfolio.get_portfolio_events(row.portfolio_id)
    )
    governance = GovernanceService.from_repository(
        governance_repository,
        registry_events=tuple(platform.list_events()),
        portfolio_events=portfolio_events,
        valid_artifact_ids={row.artifact_id for row in platform.list_artifacts()},
        valid_evidence_ids={row.evidence_id for row in platform.list_evidence()},
        valid_lineage_node_ids={row.node_id for row in platform.list_lineage_nodes()},
    )
    return research, portfolio, governance


def _sources() -> dict[str, object]:
    research, portfolio, governance = _domain_services()
    return {
        "research": ResearchWorkbenchHomeSource(research),
        "portfolio": PortfolioOSHomeSource(portfolio),
        "governance": GovernanceAuditHomeSource(governance),
        "data_health": PlatformDataHealthHomeSource(
            research=research,
            portfolio=portfolio,
            governance=governance,
        ),
        "activity": PlatformActivityHomeSource(governance),
    }


def _service(**overrides: object) -> HomeApplicationService:
    sources = {**_sources(), **overrides}
    return HomeApplicationService(
        research=sources["research"],
        portfolio=sources["portfolio"],
        governance=sources["governance"],
        data_health=sources["data_health"],
        activity=sources["activity"],
        clock=lambda: FIXED_TIME,
    )


@pytest.fixture(scope="module")
def snapshot() -> HomeSnapshot:
    return _service().get_snapshot()


def test_contract_version_shape_and_determinism(snapshot: HomeSnapshot) -> None:
    assert snapshot.version == INTERSIGNAL_HOME_SNAPSHOT_V1
    assert snapshot.generated_at == FIXED_TIME
    assert snapshot == _service().get_snapshot()
    assert set(snapshot.model_dump()) == {
        "version",
        "generated_at",
        "mode",
        "availability",
        "market",
        "portfolio",
        "research",
        "data_health",
        "governance",
        "attention",
        "recent_activity",
        "meta",
    }
    statuses = {
        snapshot.availability.market.status,
        snapshot.availability.research.status,
        snapshot.availability.portfolio.status,
        snapshot.availability.governance.status,
        snapshot.availability.data_health.status,
        snapshot.availability.activity.status,
    }
    assert statuses <= set(AvailabilityStatus)


def test_research_projection_uses_canonical_workbench_truth(
    snapshot: HomeSnapshot,
) -> None:
    research = snapshot.research
    assert research.status == AvailabilityStatus.AVAILABLE
    assert research.programme_status == "PAUSED"
    assert research.family_count == 7
    assert research.production_candidate_count == 0
    assert research.validated_production_strategy_count == 0
    assert research.strategy_v2_status == "NOT_CREATED"
    assert [row.id for row in research.reusable_evidence] == [
        "EDGE-EVIDENCE-C-COMPRESSION-001"
    ]
    assert research.reusable_evidence[0].production_strategy is False
    assert {
        row.family: row.reason_code for row in research.blocked_research
    } == {"D": "DATA_BLOCKED", "F": "SOURCE_BLOCKED"}


def test_portfolio_projection_is_seeded_synthetic_context(
    snapshot: HomeSnapshot,
) -> None:
    portfolio = snapshot.portfolio
    assert portfolio.status == AvailabilityStatus.AVAILABLE
    assert portfolio.has_portfolio is True
    assert portfolio.portfolio_count == 2
    assert portfolio.source_type == "SYNTHETIC"
    assert portfolio.valuation is not None
    assert portfolio.cash is not None
    assert portfolio.invested_value is not None
    assert portfolio.invested_pct is not None
    assert portfolio.holding_count == 1
    assert portfolio.sector_exposure
    assert portfolio.valuation_timestamp is not None


def test_portfolio_projection_supports_an_empty_store() -> None:
    service = PortfolioOSService.from_repository(InMemoryPortfolioOSRepository())
    result = PortfolioOSHomeSource(service).read()
    assert result.status == AvailabilityStatus.AVAILABLE
    assert result.reason == "NO_PORTFOLIO_CONFIGURED"
    assert result.has_portfolio is False
    assert result.portfolio_count == 0
    assert result.source_type == "NONE"


def test_governance_projection_preserves_readiness(
    snapshot: HomeSnapshot,
) -> None:
    governance = snapshot.governance
    assert governance.status == AvailabilityStatus.AVAILABLE
    assert governance.paper_readiness == "NOT_READY"
    assert governance.live_readiness == "NOT_READY"
    assert governance.broker_readiness == "NOT_READY"
    assert governance.production_readiness == "NOT_READY"
    assert governance.blocking_violation_count == 0
    assert governance.pending_authorization_count == 1
    assert set(governance.policy_summary.values()) == {"PASS"}


def test_data_health_projection_uses_integrity_and_blocked_research(
    snapshot: HomeSnapshot,
) -> None:
    data_health = snapshot.data_health
    assert data_health.status == AvailabilityStatus.PARTIAL
    assert data_health.lineage_integrity == "HEALTHY"
    assert data_health.broken_reference_count == 0
    assert data_health.daily_history_status == "AVAILABLE"
    assert data_health.corporate_actions_status == "AVAILABLE_WITH_CAVEATS"
    assert data_health.intraday_status == "BLOCKED_FOR_RESEARCH_USE"
    assert data_health.catalyst_status == "SOURCE_BLOCKED"
    assert data_health.data_limitations


def test_attention_and_activity_are_operational_and_deterministic(
    snapshot: HomeSnapshot,
) -> None:
    assert [row.id for row in snapshot.attention] == [
        "research-family-d-blocked",
        "research-family-f-blocked",
        "governance-paper-not-ready",
        "research-programme-paused",
        "governance-broker-not-ready",
        "portfolio-synthetic-source",
    ]
    assert {row.severity for row in snapshot.attention} <= set(AttentionSeverity)
    assert all(
        row.metadata["investment_recommendation"] is False
        for row in snapshot.attention
    )
    assert snapshot.recent_activity
    assert list(snapshot.recent_activity) == sorted(
        snapshot.recent_activity,
        key=lambda row: (row.occurred_at, row.id),
        reverse=True,
    )


@pytest.mark.parametrize(
    ("failed_source", "expected_reason"),
    (
        ("research", "RESEARCH_SOURCE_UNAVAILABLE"),
        ("portfolio", "PORTFOLIO_SOURCE_UNAVAILABLE"),
        ("governance", "GOVERNANCE_SOURCE_UNAVAILABLE"),
    ),
)
def test_one_domain_failure_keeps_other_sections_available(
    failed_source: str,
    expected_reason: str,
) -> None:
    snapshot = _service(**{failed_source: _FailingSource()}).get_snapshot()
    section = getattr(snapshot, failed_source)
    assert section.status == AvailabilityStatus.UNAVAILABLE
    assert section.reason == expected_reason
    for other in {"research", "portfolio", "governance"} - {failed_source}:
        assert getattr(snapshot, other).status == AvailabilityStatus.AVAILABLE
    assert "sensitive implementation detail" not in snapshot.model_dump_json()


def test_partial_failure_is_still_http_200() -> None:
    app = create_app()
    app.dependency_overrides[get_home_application_service] = lambda: _service(
        research=_FailingSource()
    )
    response = TestClient(app).get("/api/home/snapshot")
    assert response.status_code == 200
    assert response.json()["research"] == {
        "status": "UNAVAILABLE",
        "reason": "RESEARCH_SOURCE_UNAVAILABLE",
        "programme_status": "UNAVAILABLE",
        "family_count": 0,
        "production_candidate_count": 0,
        "validated_production_strategy_count": 0,
        "strategy_v2_status": "UNAVAILABLE",
        "reusable_evidence": [],
        "blocked_research": [],
        "latest_research_state": "UNAVAILABLE",
    }
    assert response.json()["portfolio"]["status"] == "AVAILABLE"
    assert response.json()["governance"]["status"] == "AVAILABLE"


def test_api_contract_cache_header_and_openapi() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/home/snapshot")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["version"] == INTERSIGNAL_HOME_SNAPSHOT_V1
    assert payload["market"] == {
        "status": "UNAVAILABLE",
        "reason": "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
        "source": "NOT_CONFIGURED",
    }
    assert payload["research"]["family_count"] == 7
    assert payload["governance"]["paper_readiness"] == "NOT_READY"
    assert payload["data_health"]["lineage_integrity"] == "HEALTHY"
    assert payload["meta"]["auth_enforcement"] == "NOT_IMPLEMENTED"
    assert "/api/home/snapshot" in client.get("/openapi.json").json()["paths"]


def test_endpoint_is_read_only() -> None:
    files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    before_hashes = {path: file_sha256(path) for path in files}
    before_counts = {
        "registry": len(
            JsonFilePlatformRepository(PLATFORM_ROOT).list_events()
        ),
        "portfolio": sum(
            len(repository.list_portfolio_events(row.portfolio_id))
            for repository in [
                JsonFilePortfolioOSRepository(PLATFORM_ROOT / "portfolio_os")
            ]
            for row in repository.list_portfolios()
        ),
        "audit": len(
            JsonFileGovernanceRepository(
                PLATFORM_ROOT / "governance"
            ).list_audit_events()
        ),
    }
    response = TestClient(create_app()).get("/api/home/snapshot")
    assert response.status_code == 200
    after_files = sorted(path for path in PLATFORM_ROOT.rglob("*") if path.is_file())
    assert after_files == files
    assert {path: file_sha256(path) for path in after_files} == before_hashes
    assert len(JsonFilePlatformRepository(PLATFORM_ROOT).list_events()) == before_counts[
        "registry"
    ]
    portfolio_repository = JsonFilePortfolioOSRepository(
        PLATFORM_ROOT / "portfolio_os"
    )
    assert sum(
        len(portfolio_repository.list_portfolio_events(row.portfolio_id))
        for row in portfolio_repository.list_portfolios()
    ) == before_counts["portfolio"]
    assert len(
        JsonFileGovernanceRepository(
            PLATFORM_ROOT / "governance"
        ).list_audit_events()
    ) == before_counts["audit"]


def test_response_has_no_secrets_or_private_paths() -> None:
    payload = TestClient(create_app()).get("/api/home/snapshot").text.lower()
    forbidden = (
        "api_key",
        "access_token",
        "authorization_token",
        "broker_secret",
        "client_secret",
        "private key",
        "totp",
        "c:\\users\\",
        "/users/",
        ".env",
    )
    assert not any(value in payload for value in forbidden)


def test_local_endpoint_performance_is_below_goal() -> None:
    client = TestClient(create_app())
    client.get("/api/home/snapshot")
    started = perf_counter()
    response = client.get("/api/home/snapshot")
    elapsed = perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 0.5
