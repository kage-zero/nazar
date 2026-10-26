"""Readiness checks. Each check reports presence/connectivity only - never a secret value."""

import logging
import uuid

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nazar_api.db import get_engine
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


def check_readiness(settings: Settings) -> ReadinessResponse:
    checks = [
        _database(settings),
        _storage(settings),
        _secret("NAZAR_SECRET_KEY", settings.secret_key, "Signs artifact links and sessions"),
        _secret("NAZAR_WORKER_TOKEN", settings.worker_token, "Authenticates the GPU worker"),
        _secret(
            "NAZAR_BOOTSTRAP_ADMIN_EMAIL", settings.bootstrap_admin_email, "First operator account"
        ),
        _secret(
            "NAZAR_BOOTSTRAP_ADMIN_PASSWORD",
            settings.bootstrap_admin_password,
            "First operator password",
        ),
        ReadinessCheck(
            name="worker",
            status=CheckStatus.NOT_IMPLEMENTED,
            detail="Job queue and worker heartbeat arrive in Milestone 4.",
            required=False,
        ),
        ReadinessCheck(
            name="gpu",
            status=CheckStatus.NOT_IMPLEMENTED,
            detail="GPU readiness is reported by the worker heartbeat (Milestone 1/4).",
            required=False,
        ),
    ]
    ready = all(c.status is CheckStatus.OK for c in checks if c.required)
    return ReadinessResponse(ready=ready, checks=checks)
