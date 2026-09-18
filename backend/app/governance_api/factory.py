from pathlib import Path

from app.governance_api.service import GovernanceApplicationService
from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.service import GovernanceService
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository


def build_governance_application_service(platform_root: Path) -> GovernanceApplicationService:
    root = Path(platform_root)
    platform = JsonFilePlatformRepository(root)
    portfolio = JsonFilePortfolioOSRepository(root / "portfolio_os")
    repository = JsonFileGovernanceRepository(root / "governance")
    portfolio_events = tuple(
        event
        for row in sorted(portfolio.list_portfolios(), key=lambda item: item.portfolio_id)
        for event in portfolio.list_portfolio_events(row.portfolio_id)
    )
    governance = GovernanceService.from_repository(
        repository,
        registry_events=tuple(platform.list_events()),
        portfolio_events=portfolio_events,
        valid_artifact_ids={row.artifact_id for row in platform.list_artifacts()},
        valid_evidence_ids={row.evidence_id for row in platform.list_evidence()},
        valid_lineage_node_ids={row.node_id for row in platform.list_lineage_nodes()},
    )
    return GovernanceApplicationService(governance, repository)


__all__ = ("build_governance_application_service",)
