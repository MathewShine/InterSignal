from __future__ import annotations

from pathlib import Path

from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.service import GovernanceService
from app.home.service import HomeApplicationService
from app.home.sources import (
    GovernanceAuditHomeSource,
    PlatformActivityHomeSource,
    PlatformDataHealthHomeSource,
    PortfolioOSHomeSource,
    ResearchWorkbenchHomeSource,
)
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.portfolio_os.service import PortfolioOSService
from app.research_workbench.service import ResearchWorkbenchService


class _UnavailableSource:
    def read(self):
        raise RuntimeError("Home source is unavailable")


def build_home_application_service(platform_root: Path) -> HomeApplicationService:
    root = Path(platform_root)
    platform_repository = None
    portfolio_repository = None
    research_service = None
    portfolio_service = None
    governance_service = None

    try:
        platform_repository = JsonFilePlatformRepository(root)
        research_service = ResearchWorkbenchService.from_repository(
            platform_repository
        )
    except Exception:
        research_service = None

    try:
        portfolio_repository = JsonFilePortfolioOSRepository(root / "portfolio_os")
        portfolio_service = PortfolioOSService.from_repository(portfolio_repository)
    except Exception:
        portfolio_service = None

    try:
        governance_repository = JsonFileGovernanceRepository(root / "governance")
        registry_events = (
            tuple(platform_repository.list_events())
            if platform_repository is not None
            else ()
        )
        portfolio_events = (
            tuple(
                event
                for portfolio in sorted(
                    portfolio_repository.list_portfolios(),
                    key=lambda row: row.portfolio_id,
                )
                for event in portfolio_repository.list_portfolio_events(
                    portfolio.portfolio_id
                )
            )
            if portfolio_repository is not None
            else ()
        )
        kwargs: dict[str, object] = {
            "registry_events": registry_events,
            "portfolio_events": portfolio_events,
        }
        if platform_repository is not None:
            kwargs.update(
                valid_artifact_ids={
                    row.artifact_id for row in platform_repository.list_artifacts()
                },
                valid_evidence_ids={
                    row.evidence_id for row in platform_repository.list_evidence()
                },
                valid_lineage_node_ids={
                    row.node_id for row in platform_repository.list_lineage_nodes()
                },
            )
        governance_service = GovernanceService.from_repository(
            governance_repository,
            **kwargs,
        )
    except Exception:
        governance_service = None

    research_source = (
        ResearchWorkbenchHomeSource(research_service)
        if research_service is not None
        else _UnavailableSource()
    )
    portfolio_source = (
        PortfolioOSHomeSource(portfolio_service)
        if portfolio_service is not None
        else _UnavailableSource()
    )
    governance_source = (
        GovernanceAuditHomeSource(governance_service)
        if governance_service is not None
        else _UnavailableSource()
    )
    data_health_source = (
        PlatformDataHealthHomeSource(
            research=research_service,
            portfolio=portfolio_service,
            governance=governance_service,
        )
        if all(
            service is not None
            for service in (research_service, portfolio_service, governance_service)
        )
        else _UnavailableSource()
    )
    activity_source = (
        PlatformActivityHomeSource(governance_service)
        if governance_service is not None
        else _UnavailableSource()
    )
    return HomeApplicationService(
        research=research_source,
        portfolio=portfolio_source,
        governance=governance_source,
        data_health=data_health_source,
        activity=activity_source,
    )


__all__ = ("build_home_application_service",)
