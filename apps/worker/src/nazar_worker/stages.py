"""Stage adapter boundary.

Every pipeline stage is implemented by an adapter that reads declared inputs from the job
workspace and writes declared, checksummed outputs atomically. Adapters never touch the
database or the browser; the worker loop turns their results into contract events.

Stage 1 (scaffold) registers no adapters. `STAGE_PLAN` records the intended component and
the milestone that delivers each one so the UI and docs can state status honestly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nazar_contracts import ArtifactManifest, StageName


@dataclass(frozen=True)
class StagePlan:
    stage: StageName
    component: str
    milestone: int
    optional: bool


STAGE_PLAN: tuple[StagePlan, ...] = (
    StagePlan(StageName.PREPROCESSING, "FFmpeg + OpenCV", 2, optional=False),
    StagePlan(StageName.GEOMETRY, "Fast3R (or documented fallback)", 3, optional=False),
    StagePlan(StageName.DEPTH_PRIORS, "Metric3D-v2", 5, optional=True),
    StagePlan(StageName.DYNAMIC_ANALYSIS, "YOLO + SAM2", 6, optional=True),
    StagePlan(StageName.SENSOR_OPTIMIZATION, "GTSAM (telemetry only)", 5, optional=True),
    StagePlan(StageName.DENSE_RECONSTRUCTION, "Open3D + InstantSplat", 7, optional=False),
    StagePlan(StageName.SURFACE_PROCESSING, "Poisson / SuGaR + GDAL/PyProj", 7, optional=True),
    StagePlan(StageName.ANALYSIS, "Confidence + measurements", 8, optional=False),
    StagePlan(StageName.EXPORTING, "PLY / GLB / LAS + report", 8, optional=False),
)


@dataclass(frozen=True)
class StageContext:
    job_id: str
    workspace: Path
    test_pipeline: bool


class StageAdapter(Protocol):
    stage: StageName

    def run(self, ctx: StageContext) -> list[ArtifactManifest]:
        """Run the stage. Raise to fail it; return manifests of artifacts written."""
        ...


ADAPTERS: dict[StageName, StageAdapter] = {}
