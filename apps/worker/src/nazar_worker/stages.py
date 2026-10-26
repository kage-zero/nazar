"""Stage adapter boundary.

Every pipeline stage is implemented by an adapter that reads declared inputs from the job
workspace and writes declared, checksummed outputs atomically. Adapters never touch the
database or the browser; the worker loop turns their results into contract events.

`ADAPTERS` holds the real implementations (none yet); `test_pipeline.build_test_pipeline` builds the
deterministic test pipeline used by CI and demos. `STAGE_PLAN` records the intended component and
the milestone that delivers each one so the UI and docs can state status honestly.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from nazar_contracts import ArtifactCreate, ArtifactCreated, StageName, WorkerLease

WarningSeverity = Literal["info", "warning", "critical"]


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


class Cancelled(Exception):
    """Raised inside a stage when the user asked to cancel; the runner reports it."""


@dataclass(frozen=True)
class StageContext:
    """What an adapter may do. It never talks to the API or the database directly."""

    lease: WorkerLease
    progress: Callable[[str, int | None, int | None, str | None], None]
    warn: Callable[[str, str, WarningSeverity], None]
    publish: Callable[[ArtifactCreate, bytes], ArtifactCreated]
    preflight: Callable[[], dict[str, Any]]
    check_cancel: Callable[[], None]


class StageAdapter(Protocol):
    def skip_reason(self, lease: WorkerLease) -> str | None:
        """Why this stage cannot meaningfully run on this job's inputs, or None to run it.
        Asked before the stage starts: a started stage is never reported as skipped."""
        ...

    def run(self, ctx: StageContext) -> None:
        """Run the stage. Raise to fail the job."""
        ...


# Real stage implementations, keyed by stage. Empty until Milestone 3 lands geometry.
ADAPTERS: dict[StageName, StageAdapter] = {}
