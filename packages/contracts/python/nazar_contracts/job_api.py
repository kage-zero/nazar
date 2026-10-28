"""Request/response bodies for the job API (browser) and the worker protocol (ADR-0003).

The event stream (`events.py`) is the source of truth for what happened; a `Job` snapshot
is derived from it so a client can render the current state without replaying history.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nazar_contracts.artifacts import (
    ArtifactKind,
    ArtifactManifest,
    Bounds3D,
    CoordinateFrame,
    FrameRange,
    Matrix4,
    Provenance,
)
from nazar_contracts.events import EventType, StageProgressData, WarningData
from nazar_contracts.jobs import JobStatus, StageName


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PipelineMode(StrEnum):
    """Which stage implementations a job uses.

    - `test`: deterministic test pipeline. Emits small real-format fixture artifacts through
      the real API and event contracts. Never presented as a reconstruction of the input.
    - `standard`: real stages (Fast3R on the GPU when the worker has it, else the CPU
      classical-geometry baseline).
    """

    TEST = "test"
    STANDARD = "standard"


class GeometryBackend(StrEnum):
    """What a worker's standard pipeline would use for geometry right now."""

    FAST3R = "fast3r"
    CPU_BASELINE = "cpu-baseline"


class StageRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageState(_Model):
    stage: StageName
    state: StageRunState
    reason: str | None = Field(default=None, description="Why it was skipped or failed.")
    duration_s: float | None = None
    progress: StageProgressData | None = None


class Job(_Model):
    """Current snapshot of a job, rebuilt from its event log."""

    id: str
    mission_id: str
    status: JobStatus
    pipeline: PipelineMode
    attempt: int = Field(ge=1)
    last_seq: int = Field(ge=0, description="Cursor of the newest event; resume after it.")
    stages: list[StageState]
    artifacts: list[ArtifactManifest] = Field(description="Newest revision of each artifact.")
    warnings: list[WarningData]
    error: str | None = None
    retryable: bool = False
    created_at: datetime
    updated_at: datetime


class JobCreate(_Model):
    """Start reconstruction of the mission's validated video."""

    pipeline: PipelineMode


# --- Worker protocol -------------------------------------------------------------------


class WorkerLeaseRequest(_Model):
    worker_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    modes: list[PipelineMode] = Field(min_length=1)
    geometry: GeometryBackend | None = Field(
        default=None,
        description="Geometry backend for standard jobs on this worker (absent: not reported).",
    )


class WorkerLease(_Model):
    lease_id: str = Field(description="Send as `X-Nazar-Lease` on every call for this job.")
    job_id: str
    mission_id: str
    pipeline: PipelineMode
    attempt: int
    lease_expires_at: datetime
    video_asset_id: str
    keyframe_count: int = Field(ge=0)
    video_sha256: str
    telemetry_asset_id: str | None = Field(
        default=None,
        description="Accepted telemetry pinned when the job was created; fetch it from "
        "`inputs/telemetry`.",
    )


class WorkerHeartbeat(_Model):
    cancel_requested: bool
    lease_expires_at: datetime


class WorkerEvent(_Model):
    """An event reported by the worker. The API assigns `seq`, `ts` and `status`.

    `key` makes delivery idempotent: re-sending an event with a key the job already has is a
    no-op, so the worker can safely retry after a dropped connection.
    """

    key: str = Field(min_length=1, max_length=96)
    type: EventType
    stage: StageName | None = None
    data: dict[str, Any] | None = None


class WorkerEventBatch(_Model):
    events: list[WorkerEvent] = Field(min_length=1, max_length=100)


class WorkerEventAck(_Model):
    status: JobStatus
    last_seq: int
    cancel_requested: bool


class ArtifactCreate(_Model):
    """Declared before upload; bytes are verified against `byte_size` and the checksum."""

    key: str = Field(min_length=1, max_length=96, description="Idempotency key.")
    kind: ArtifactKind
    media_type: str = Field(max_length=100)
    byte_size: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame: CoordinateFrame | None = None
    transform_to_frame: Matrix4 | None = None
    bounds: Bounds3D | None = None
    point_count: int | None = Field(default=None, ge=0)
    lod: int | None = Field(default=None, ge=0)
    source_frames: FrameRange | None = None
    provenance: Provenance
    final: bool = Field(
        default=False, description="False for previews that a later revision may supersede."
    )


class ArtifactCreated(_Model):
    id: str
    revision: int
    uploaded: bool = Field(description="True when the bytes were already received (retry).")
