from fastapi import APIRouter, Request

from app.db.supabase import SupabaseClientFactory
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse, include_in_schema=False)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/database", response_model=DatabaseHealthResponse)
async def database_health(request: Request) -> DatabaseHealthResponse:
    settings = request.app.state.settings
    factory = SupabaseClientFactory(settings)
    health = factory.check_connection()

    return DatabaseHealthResponse(
        status=health.status,
        service="Supabase",
        configured=health.configured,
        detail=health.detail,
    )
