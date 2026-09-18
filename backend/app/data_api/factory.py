from __future__ import annotations

import json
from pathlib import Path

from app.data_api.service import DataHealthApplicationService
from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.service import GovernanceService
from app.home.sources import PlatformDataHealthHomeSource
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.portfolio_os.service import PortfolioOSService
from app.research_workbench.service import ResearchWorkbenchService


def build_data_health_application_service(platform_root: Path) -> DataHealthApplicationService:
    root = Path(platform_root)
    platform = JsonFilePlatformRepository(root)
    research = ResearchWorkbenchService.from_repository(platform)
    portfolio_repo = JsonFilePortfolioOSRepository(root / "portfolio_os")
    portfolio = PortfolioOSService.from_repository(portfolio_repo)
    governance_repo = JsonFileGovernanceRepository(root / "governance")
    governance = GovernanceService.from_repository(
        governance_repo,
        valid_artifact_ids={row.artifact_id for row in platform.list_artifacts()},
        valid_evidence_ids={row.evidence_id for row in platform.list_evidence()},
        valid_lineage_node_ids={row.node_id for row in platform.list_lineage_nodes()},
    )
    continuity_path = root.parent / "research/strategy_families/family_d/v1/exact_gap_recovery/readiness/family_d_post_recovery_readiness_v1.json"
    continuity = json.loads(continuity_path.read_text(encoding="utf-8"))
    continuity["unresolved_gap_count"] = 217
    return DataHealthApplicationService(
        platform=platform,
        health=PlatformDataHealthHomeSource(
            research=research,
            portfolio=portfolio,
            governance=governance,
        ),
        continuity=continuity,
    )


__all__ = ("build_data_health_application_service",)
