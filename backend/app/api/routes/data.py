from fastapi import APIRouter, Depends, Request, Response

from app.data_api.factory import build_data_health_application_service
from app.data_api.models import (
    DataLimitationsResponse,
    DataLineageResponse,
    DataOverviewResponse,
    DataSourcesResponse,
)
from app.data_api.service import DataHealthApplicationService


router = APIRouter(prefix="/data", tags=["data"])


def get_data_health_application_service(request: Request) -> DataHealthApplicationService:
    return build_data_health_application_service(request.app.state.settings.home_data_root)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/overview", response_model=DataOverviewResponse)
def data_overview(response: Response, service: DataHealthApplicationService = Depends(get_data_health_application_service)) -> DataOverviewResponse:
    _no_store(response)
    return service.get_overview()


@router.get("/sources", response_model=DataSourcesResponse)
def data_sources(response: Response, service: DataHealthApplicationService = Depends(get_data_health_application_service)) -> DataSourcesResponse:
    _no_store(response)
    return service.get_sources()


@router.get("/lineage", response_model=DataLineageResponse)
def data_lineage(response: Response, service: DataHealthApplicationService = Depends(get_data_health_application_service)) -> DataLineageResponse:
    _no_store(response)
    return service.get_lineage()


@router.get("/limitations", response_model=DataLimitationsResponse)
def data_limitations(response: Response, service: DataHealthApplicationService = Depends(get_data_health_application_service)) -> DataLimitationsResponse:
    _no_store(response)
    return service.get_limitations()


__all__ = ("get_data_health_application_service", "router")
