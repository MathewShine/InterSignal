from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.portfolio_api.factory import build_portfolio_application_service
from app.portfolio_api.models import (
    PortfolioActivityResponse,
    PortfolioHoldingsResponse,
    PortfolioOverviewResponse,
    PortfolioPerformanceResponse,
)
from app.portfolio_api.service import PortfolioApplicationService
from app.portfolio_os.errors import PortfolioNotFound


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def get_portfolio_application_service(request: Request) -> PortfolioApplicationService:
    return build_portfolio_application_service(request.app.state.settings.home_data_root)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _not_found(error: PortfolioNotFound) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Portfolio not found.",
    )


@router.get("/overview", response_model=PortfolioOverviewResponse)
def portfolio_overview(
    response: Response,
    portfolio_id: str | None = Query(default=None),
    service: PortfolioApplicationService = Depends(get_portfolio_application_service),
) -> PortfolioOverviewResponse:
    _no_store(response)
    try:
        return service.get_overview(portfolio_id)
    except PortfolioNotFound as error:
        raise _not_found(error) from error


@router.get("/holdings", response_model=PortfolioHoldingsResponse)
def portfolio_holdings(
    response: Response,
    portfolio_id: str | None = Query(default=None),
    service: PortfolioApplicationService = Depends(get_portfolio_application_service),
) -> PortfolioHoldingsResponse:
    _no_store(response)
    try:
        return service.get_holdings(portfolio_id)
    except PortfolioNotFound as error:
        raise _not_found(error) from error


@router.get("/activity", response_model=PortfolioActivityResponse)
def portfolio_activity(
    response: Response,
    portfolio_id: str | None = Query(default=None),
    service: PortfolioApplicationService = Depends(get_portfolio_application_service),
) -> PortfolioActivityResponse:
    _no_store(response)
    try:
        return service.get_activity(portfolio_id)
    except PortfolioNotFound as error:
        raise _not_found(error) from error


@router.get("/performance", response_model=PortfolioPerformanceResponse)
def portfolio_performance(
    response: Response,
    portfolio_id: str | None = Query(default=None),
    service: PortfolioApplicationService = Depends(get_portfolio_application_service),
) -> PortfolioPerformanceResponse:
    _no_store(response)
    try:
        return service.get_performance(portfolio_id)
    except PortfolioNotFound as error:
        raise _not_found(error) from error


__all__ = ("get_portfolio_application_service", "router")
