from pathlib import Path

from app.platform.repositories import JsonFilePlatformRepository
from app.research_api.service import ResearchApplicationService
from app.research_workbench.service import ResearchWorkbenchService


def build_research_application_service(platform_root: Path) -> ResearchApplicationService:
    repository = JsonFilePlatformRepository(Path(platform_root))
    workbench = ResearchWorkbenchService.from_repository(repository)
    return ResearchApplicationService(workbench)


__all__ = ("build_research_application_service",)
