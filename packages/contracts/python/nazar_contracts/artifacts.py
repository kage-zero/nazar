"""Artifact manifest: what the browser learns about a partial or final output.

The manifest never contains a filesystem path or storage credential. Clients fetch bytes
through an authorised API route keyed by `id` and `revision`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Matrix4 = Annotated[list[float], Field(min_length=16, max_length=16)]


class ArtifactKind(StrEnum):
    KEYFRAMES = "keyframes"
    POINT_CLOUD_PREVIEW = "point_cloud_preview"
    POINT_CLOUD = "point_cloud"
    CAMERA_TRAJECTORY = "camera_trajectory"
    DEPTH_MAPS = "depth_maps"
    DYNAMIC_MASKS = "dynamic_masks"
    GAUSSIAN_SCENE = "gaussian_scene"
    MESH = "mesh"
    REPORT = "report"
    EXPORT = "export"


class FrameType(StrEnum):
    LOCAL_RECONSTRUCTION = "local_reconstruction"
    ENU = "enu"
    ECEF = "ecef"
    GEOGRAPHIC = "geographic"
    PROJECTED = "projected"


class ScaleStatus(StrEnum):
    UNKNOWN = "unknown"
    RELATIVE = "relative"
    METRIC_ESTIMATED = "metric_estimated"
    METRIC_SENSOR = "metric_sensor"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoordinateFrame(_Model):
    type: FrameType
    units: str = Field(description="Linear units of coordinates, e.g. 'metre' or 'unitless'.")
    scale_status: ScaleStatus
    crs: str | None = Field(default=None, description="EPSG/WKT identifier when georeferenced.")
    vertical_datum: str | None = None
    metres_per_unit: float | None = Field(
        default=None,
        description="Metres per coordinate unit when scale comes from a sensor alignment while "
        "coordinates stay in the local frame; null when scale is unknown or units are metres.",
    )
    axes: str = Field(
        default="right-handed; +X right, +Y up, -Z forward (OpenGL camera convention)",
        description="Axis convention of stored coordinates.",
    )


class Bounds3D(_Model):
    min: Vec3
    max: Vec3


class FrameRange(_Model):
    first_index: int = Field(ge=0)
    last_index: int = Field(ge=0)
    count: int = Field(ge=0)


class Provenance(_Model):
    producer: str = Field(description="Stage adapter that produced the artifact.")
    model: str | None = None
    model_version: str | None = None
    config_hash: str | None = None
    test_pipeline: bool = Field(
        description="True when produced by the deterministic test pipeline, not a real model."
    )


class ArtifactManifest(_Model):
    id: str
    job_id: str
    kind: ArtifactKind
    revision: int = Field(
        ge=1, description="Monotonic per (job, kind); stale revisions are ignored."
    )
    media_type: str
    byte_size: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame: CoordinateFrame | None = None
    transform_to_frame: Matrix4 | None = Field(
        default=None, description="Column-major 4x4 from artifact-local coords to `frame`."
    )
    bounds: Bounds3D | None = None
    point_count: int | None = Field(default=None, ge=0)
    lod: int | None = Field(default=None, ge=0)
    source_frames: FrameRange | None = None
    provenance: Provenance
    created_at: datetime
