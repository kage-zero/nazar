"""Health (liveness) and readiness contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class CheckStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    NOT_IMPLEMENTED = "not_implemented"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    time: datetime


class ReadinessCheck(BaseModel):
    name: str
    status: CheckStatus
    detail: str
    required: bool


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]
