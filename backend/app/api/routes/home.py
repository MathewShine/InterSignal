from fastapi import APIRouter, Depends, Request, Response

from app.home.factory import build_home_application_service
from app.home.models import HomeSnapshot
from app.home.service import HomeApplicationService


router = APIRouter(prefix="/home", tags=["home"])


def get_home_application_service(request: Request) -> HomeApplicationService:
    return build_home_application_service(request.app.state.settings.home_data_root)


@router.get(
    "/snapshot",
    response_model=HomeSnapshot,
    summary="Read the aggregated Intelligence Home snapshot",
)
def home_snapshot(
    response: Response,
    service: HomeApplicationService = Depends(get_home_application_service),
) -> HomeSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return service.get_snapshot()


__all__ = ("get_home_application_service", "router")
