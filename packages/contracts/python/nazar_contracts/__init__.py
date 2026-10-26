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
from nazar_contracts.media import (
    PREFLIGHT_SCHEMA_VERSION,
    AnalysisInfo,
    FrameFlag,
    FrameSeries,
    Keyframe,
    KeyframeReason,
    PreflightReport,
    PreflightSummary,
    PreflightWarning,
    VideoProbe,
    WarningSeverity,
)
from nazar_contracts.missions import (
    Asset,
    AssetCreate,
    AssetKind,
    AssetStatus,
    AuthState,
    Credentials,
    Mission,
    MissionCreate,
    ProcessingProgress,
    UserPublic,
)

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "PIPELINE_STAGES",
    "PREFLIGHT_SCHEMA_VERSION",
    "TERMINAL_STATUSES",
    "AnalysisInfo",
    "ArtifactKind",
    "ArtifactManifest",
    "Asset",
    "AssetCreate",
    "AssetKind",
    "AssetStatus",
    "AuthState",
    "Bounds3D",
    "CheckStatus",
    "CoordinateFrame",
    "Credentials",
    "EventType",
    "FrameFlag",
    "FrameRange",
    "FrameSeries",
    "FrameType",
    "HealthResponse",
    "JobEvent",
    "JobStatus",
    "Keyframe",
    "KeyframeReason",
    "Mission",
    "MissionCreate",
    "PreflightReport",
    "PreflightSummary",
    "PreflightWarning",
    "ProcessingProgress",
    "Provenance",
    "ReadinessCheck",
    "ReadinessResponse",
    "ScaleStatus",
    "StageName",
    "UserPublic",
    "VideoProbe",
    "WarningSeverity",
    "can_transition",
]
