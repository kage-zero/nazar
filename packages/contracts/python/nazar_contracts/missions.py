"""Accounts, missions and uploaded assets (video, optional telemetry)."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Email = Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class UserPublic(BaseModel):
    id: str
    email: str


class AuthState(BaseModel):
    """`setup_required` is true only while no operator account exists."""

    setup_required: bool
    user: UserPublic | None


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: Annotated[str, Field(min_length=10, max_length=256)]


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]


class AssetKind(StrEnum):
    VIDEO = "video"
    TELEMETRY = "telemetry"


class AssetStatus(StrEnum):
    UPLOADING = "uploading"
    VALIDATING = "validating"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AssetKind
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    byte_size: Annotated[int, Field(gt=0)]


class ProcessingProgress(BaseModel):
    """Server-side processing phase. Counts are null when the work is not countable."""

    phase: str
    completed: int | None = None
    total: int | None = None


class Asset(BaseModel):
    id: str
    mission_id: str
    kind: AssetKind
    filename: str
    byte_size: int
    received_bytes: int
    status: AssetStatus
    error: str | None
    progress: ProcessingProgress | None
    sha256: str | None
    created_at: datetime
    updated_at: datetime


class Mission(BaseModel):
    id: str
    name: str
    created_at: datetime
    video: Asset | None
    telemetry: Asset | None = None
