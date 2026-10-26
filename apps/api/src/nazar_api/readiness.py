"""Readiness checks. Each check reports presence/connectivity only - never a secret value."""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from nazar_api.db import get_engine
from nazar_api.models import User
from nazar_api.settings import Settings
from nazar_contracts import CheckStatus, ReadinessCheck, ReadinessResponse

log = logging.getLogger(__name__)


def _database(settings: Settings) -> ReadinessCheck:
    kind = "PostgreSQL" if settings.database_url else "SQLite (local default)"
    try:
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        with get_engine(settings.sqlalchemy_url).connect() as conn:
            conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        log.warning("database check failed", extra={"error": type(exc).__name__})
        return ReadinessCheck(
            name="database",
            status=CheckStatus.UNAVAILABLE,
            detail=f"{kind} is unreachable ({type(exc).__name__}).",
            required=True,
        )
    return ReadinessCheck(
        name="database", status=CheckStatus.OK, detail=f"{kind} reachable.", required=True
    )


def _storage(settings: Settings) -> ReadinessCheck:
    if settings.s3_endpoint_url:
        return ReadinessCheck(
            name="storage",
            status=CheckStatus.NOT_IMPLEMENTED,
            detail="S3-compatible storage is configured but its adapter is not implemented yet.",
            required=True,
        )
    probe = settings.storage_path / f".probe-{uuid.uuid4().hex}"
    try:
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        return ReadinessCheck(
            name="storage",
            status=CheckStatus.UNAVAILABLE,
            detail=f"Local storage directory is not writable ({type(exc).__name__}).",
            required=True,
        )
    return ReadinessCheck(
        name="storage", status=CheckStatus.OK, detail="Local storage writable.", required=True
    )


def _secret(name: str, value: SecretStr | str | None, purpose: str) -> ReadinessCheck:
    present = value is not None and (
        value.get_secret_value() if isinstance(value, SecretStr) else value
    )
    return ReadinessCheck(
        name=f"config:{name}",
        status=CheckStatus.OK if present else CheckStatus.NOT_CONFIGURED,
        detail=f"{purpose}. {'Present.' if present else 'Blank in .env.'}",
        required=True,
    )


def _accounts(settings: Settings) -> ReadinessCheck:
    try:
        with get_engine(settings.sqlalchemy_url).connect() as conn:
            users = conn.execute(select(func.count()).select_from(User)).scalar_one()
    except SQLAlchemyError as exc:
        return ReadinessCheck(
            name="accounts",
            status=CheckStatus.UNAVAILABLE,
            detail=f"Accounts table is unreadable ({type(exc).__name__}).",
            required=True,
        )
    if users:
        return ReadinessCheck(
            name="accounts",
            status=CheckStatus.OK,
            detail="Operator account exists.",
            required=True,
        )
    return ReadinessCheck(
        name="accounts",
        status=CheckStatus.NOT_CONFIGURED,
        detail="No operator account yet. Create one in the web app (first-run setup).",
        required=True,
    )


WORKER_FRESH_S = 60


def _worker(seen_at: datetime | None) -> ReadinessCheck:
    if seen_at is not None:
        age = (datetime.now(UTC) - seen_at).total_seconds()
        if age <= WORKER_FRESH_S:
            return ReadinessCheck(
                name="worker",
                status=CheckStatus.OK,
                detail=f"A worker contacted the API {age:.0f} s ago.",
                required=False,
            )
    return ReadinessCheck(
        name="worker",
        status=CheckStatus.NOT_CONFIGURED,
        detail="No worker has contacted the API in the last minute. Jobs wait in the queue "
        "until one does (locally: `pnpm worker`).",
        required=False,
    )


def check_readiness(
    settings: Settings, worker_seen_at: datetime | None = None
) -> ReadinessResponse:
    checks = [
        _database(settings),
        _storage(settings),
        _secret("NAZAR_SECRET_KEY", settings.secret_key, "Signs artifact links and sessions"),
        _secret("NAZAR_WORKER_TOKEN", settings.worker_token, "Authenticates the GPU worker"),
        _accounts(settings),
        _worker(worker_seen_at),
        ReadinessCheck(
            name="gpu",
            status=CheckStatus.NOT_IMPLEMENTED,
            detail="Workers do not report GPU details yet (needs Milestone 1 on the VDI).",
            required=False,
        ),
    ]
    ready = all(c.status is CheckStatus.OK for c in checks if c.required)
    return ReadinessResponse(ready=ready, checks=checks)
