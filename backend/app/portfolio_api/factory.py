from pathlib import Path

from app.portfolio_api.service import PortfolioApplicationService
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.portfolio_os.service import PortfolioOSService


def build_portfolio_application_service(platform_root: Path) -> PortfolioApplicationService:
    repository = JsonFilePortfolioOSRepository(Path(platform_root) / "portfolio_os")
    portfolio_os = PortfolioOSService.from_repository(repository)
    return PortfolioApplicationService(portfolio_os)


__all__ = ("build_portfolio_application_service",)
