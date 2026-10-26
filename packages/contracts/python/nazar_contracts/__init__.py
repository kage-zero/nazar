"""Shared NAZAR contracts.

These Pydantic models are the single source of truth for the API/event contract.
`packages/contracts/scripts/export_schema.py` exports them to JSON Schema, and
`scripts/generate-ts.mjs` turns that schema into the TypeScript types the web app uses.
"""

from nazar_contracts.artifacts import (
    ArtifactKind,
    ArtifactManifest,
    Bounds3D,
    CoordinateFrame,
    FrameRange,
    FrameType,
    Provenance,
    ScaleStatus,
)
from nazar_contracts.events import EVENT_SCHEMA_VERSION, EventType, JobEvent
from nazar_contracts.health import CheckStatus, HealthResponse, ReadinessCheck, ReadinessResponse
from nazar_contracts.jobs import (
    PIPELINE_STAGES,
    TERMINAL_STATUSES,
    JobStatus,
    StageName,
    can_transition,
)

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "PIPELINE_STAGES",
    "TERMINAL_STATUSES",
    "ArtifactKind",
    "ArtifactManifest",
    "Bounds3D",
    "CheckStatus",
    "CoordinateFrame",
    "EventType",
    "FrameRange",
    "FrameType",
    "HealthResponse",
    "JobEvent",
    "JobStatus",
    "Provenance",
    "ReadinessCheck",
    "ReadinessResponse",
    "ScaleStatus",
    "StageName",
    "can_transition",
]
