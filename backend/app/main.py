from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.v1 import api_router
from app.config.settings import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
    )
    app.state.settings = app_settings

    if app_settings.frontend_url:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[app_settings.frontend_url],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
