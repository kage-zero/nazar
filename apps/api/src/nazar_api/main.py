from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nazar_api import __version__
from nazar_api.logging import configure_logging
from nazar_api.readiness import check_readiness
from nazar_api.settings import Settings, get_settings
from nazar_contracts import HealthResponse, ReadinessResponse

SettingsDep = Annotated[Settings, Depends(get_settings)]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="NAZAR API",
        version=__version__,
        description="Single-pass drone video to progressive 3D reconstruction.",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health(s: SettingsDep) -> HealthResponse:
        """Liveness: the API process is up. Says nothing about dependencies."""
        return HealthResponse(
            status="ok",
            service="nazar-api",
            version=__version__,
            environment=s.env,
            time=datetime.now(UTC),
        )

    @app.get("/api/ready", response_model=ReadinessResponse, tags=["system"])
    def ready(s: SettingsDep) -> ReadinessResponse:
        """Readiness: database, storage, required configuration, worker, GPU."""
        return check_readiness(s)

    return app
