import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from nazar_api import __version__
from nazar_api.db import get_engine
from nazar_api.deps import SettingsDep
from nazar_api.logging import configure_logging
from nazar_api.migrate import upgrade_to_head
from nazar_api.models import User
from nazar_api.processing import AssetProcessor
from nazar_api.readiness import check_readiness
from nazar_api.routes import auth, missions
from nazar_api.security import CSRF_HEADER, LoginThrottle, hash_password
from nazar_api.settings import Settings, get_settings
from nazar_contracts import HealthResponse, ReadinessResponse

log = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class RequireRequestHeader:
    """Reject state-changing /api requests that lack the `X-Nazar-Request` header (CSRF)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and scope["path"].startswith("/api/")
            and (CSRF_HEADER.encode(), b"1") not in scope["headers"]
        ):
            body = b'{"detail":"Missing X-Nazar-Request header."}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _bootstrap_admin(settings: Settings, session: Session) -> None:
    """Headless alternative to first-run setup: create the operator from env if none exists."""
    email, password = settings.bootstrap_admin_email, settings.bootstrap_admin_password
    if not email or password is None:
        return
    if session.scalar(select(func.count()).select_from(User)):
        return
    session.add(User(email=email.lower(), password_hash=hash_password(password.get_secret_value())))
    session.commit()
    log.info("bootstrap operator account created")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    upgrade_to_head(settings)
    engine = get_engine(settings.sqlalchemy_url)
    with Session(engine) as session:
        _bootstrap_admin(settings, session)
    processor = AssetProcessor(settings, engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resumed = processor.resume_pending()
        if resumed:
            log.info("resumed pending validations", extra={"count": resumed})
        yield
        processor.shutdown()

    app = FastAPI(
        title="NAZAR API",
        version=__version__,
        description="Single-pass drone video to progressive 3D reconstruction.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.processor = processor
    app.state.login_throttle = LoginThrottle()
    app.dependency_overrides[get_settings] = lambda: settings
    app.add_middleware(RequireRequestHeader)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", CSRF_HEADER],
        allow_credentials=True,
    )
    app.include_router(auth.router)
    app.include_router(missions.router)

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
        """Readiness: database, storage, required configuration, accounts, worker, GPU."""
        return check_readiness(s)

    return app
