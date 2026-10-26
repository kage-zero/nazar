"""Deterministic test pipeline (`pipeline=test`).

It exercises the real job machinery end to end — lease, stage events, artifact declaration,
checksummed upload, previews that are superseded by later revisions, completion — without a
GPU or model weights. Its geometry is a fixed synthetic scene (a stepped pyramid on a ground
plane), **not** a reconstruction of the uploaded video, and every artifact says so in its
provenance (`test_pipeline: true`) and in a PLY comment.
"""

import hashlib
import json
import math
import random
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from nazar_contracts import (
    ArtifactCreate,
    ArtifactKind,
    Bounds3D,
    CoordinateFrame,
    FrameRange,
    FrameType,
    Provenance,
    ScaleStatus,
    StageName,
    WorkerLease,
)
from nazar_worker.ply import Point, bounds, write_ply
from nazar_worker.stages import StageAdapter, StageContext

PRODUCER = "nazar-worker/test-pipeline"
FIXTURE_NOTE = "NAZAR test pipeline fixture - synthetic scene, not a reconstruction of the input"
LOCAL_FRAME = CoordinateFrame(
    type=FrameType.LOCAL_RECONSTRUCTION, units="unitless", scale_status=ScaleStatus.UNKNOWN
)
PROVENANCE = Provenance(producer=PRODUCER, model=None, test_pipeline=True)


def synthetic_scene(seed: int = 7) -> list[Point]:
    """About 20k points: a jittered ground plane and a four-tier stepped pyramid, coloured
    by height. Ordered by a shuffled index so any prefix is a uniform subsample (cheap LOD)."""
    rng = random.Random(seed)  # noqa: S311 - deterministic fixture, not security
    pts: list[Point] = []
    for i in range(120):
        for j in range(120):
            x, z = -6 + i * 0.1 + rng.uniform(-0.03, 0.03), -6 + j * 0.1 + rng.uniform(-0.03, 0.03)
            shade = 70 + rng.randint(0, 25)
            pts.append((x, rng.uniform(-0.01, 0.01), z, shade + 30, shade + 20, shade))
    tiers = [(3.0, 0.0), (2.2, 0.6), (1.4, 1.2), (0.6, 1.8)]
    for half, y0 in tiers:
        height = 0.6
        for _ in range(int(1600 * half)):
            # Top face and four side faces of each tier.
            face = rng.randrange(5)
            u, v = rng.uniform(-half, half), rng.uniform(0, height)
            if face == 0:
                x, y, z = u, y0 + height, rng.uniform(-half, half)
            elif face == 1:
                x, y, z = u, y0 + v, half
            elif face == 2:
                x, y, z = u, y0 + v, -half
            elif face == 3:
                x, y, z = half, y0 + v, u
            else:
                x, y, z = -half, y0 + v, u
            t = (y0 + v) / 2.4
            pts.append((x, y, z, int(200 + 40 * t), int(160 + 60 * t), int(90 + 40 * t)))
    rng.shuffle(pts)
    return pts


def _declare(
    key: str,
    kind: ArtifactKind,
    media_type: str,
    content: bytes,
    *,
    points: Sequence[Point] | None = None,
    lod: int | None = None,
    frames: FrameRange | None = None,
    final: bool = False,
) -> ArtifactCreate:
    box = None
    if points:
        lo, hi = bounds(points)
        box = Bounds3D(min=lo, max=hi)
    return ArtifactCreate(
        key=key,
        kind=kind,
        media_type=media_type,
        byte_size=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        frame=LOCAL_FRAME if points is not None or kind is ArtifactKind.CAMERA_TRAJECTORY else None,
        bounds=box,
        point_count=len(points) if points is not None else None,
        lod=lod,
        source_frames=frames,
        provenance=PROVENANCE,
        final=final,
    )


def _frames(ctx: StageContext) -> FrameRange | None:
    n = ctx.lease.keyframe_count
    return FrameRange(first_index=0, last_index=max(n - 1, 0), count=n) if n else None


class _Paced:
    """Stages sleep `step_s` between steps so a human can watch events arrive."""

    def __init__(self, step_s: float) -> None:
        self.step_s = step_s

    def skip_reason(self, lease: WorkerLease) -> str | None:
        return None

    def pause(self, ctx: StageContext) -> None:
        ctx.check_cancel()
        if self.step_s:
            time.sleep(self.step_s)
        ctx.check_cancel()


class Preprocessing(_Paced):
    """Reuses the real preflight produced at upload: no frames are decoded again."""

    def run(self, ctx: StageContext) -> None:
        report = ctx.preflight()
        keyframes = report.get("keyframes", [])
        ctx.progress(
            "Reusing preflight keyframes from upload validation",
            len(keyframes),
            len(keyframes),
            "keyframes",
        )
        self.pause(ctx)


class Geometry(_Paced):
    def __init__(self, step_s: float, scene: list[Point]) -> None:
        super().__init__(step_s)
        self.scene = scene

    def run(self, ctx: StageContext) -> None:
        total = len(self.scene)
        # Two preview revisions of growing density, so clients must replace, not append.
        for revision, share in ((1, 0.15), (2, 0.5)):
            self.pause(ctx)
            subset = self.scene[: int(total * share)]
            ply = write_ply(subset, [FIXTURE_NOTE])
            ctx.publish(
                _declare(
                    f"preview-{revision}",
                    ArtifactKind.POINT_CLOUD_PREVIEW,
                    "application/vnd.nazar.ply",
                    ply,
                    points=subset,
                    lod=2 - revision,
                    frames=_frames(ctx),
                ),
                ply,
            )
            ctx.progress("Synthetic preview points", len(subset), total, "points")


class Dense(_Paced):
    def __init__(self, step_s: float, scene: list[Point]) -> None:
        super().__init__(step_s)
        self.scene = scene

    def run(self, ctx: StageContext) -> None:
        self.pause(ctx)
        ply = write_ply(self.scene, [FIXTURE_NOTE])
        ctx.publish(
            _declare(
                "point-cloud",
                ArtifactKind.POINT_CLOUD,
                "application/vnd.nazar.ply",
                ply,
                points=self.scene,
                lod=0,
                frames=_frames(ctx),
                final=True,
            ),
            ply,
        )
        trajectory = _trajectory(max(ctx.lease.keyframe_count, 2))
        ctx.publish(
            _declare(
                "camera-trajectory",
                ArtifactKind.CAMERA_TRAJECTORY,
                "application/json",
                trajectory,
                frames=_frames(ctx),
                final=True,
            ),
            trajectory,
        )
        ctx.progress("Synthetic point cloud and camera path published", 2, 2, "artifacts")


def _trajectory(count: int) -> bytes:
    poses = []
    for i in range(count):
        a = 2 * math.pi * i / count
        poses.append(
            {
                "keyframe": i,
                "position": [round(9 * math.cos(a), 4), 5.0, round(9 * math.sin(a), 4)],
                "look_at": [0.0, 1.0, 0.0],
            }
        )
    doc = {
        "note": FIXTURE_NOTE,
        "frame": "local_reconstruction",
        "units": "unitless",
        "poses": poses,
    }
    return json.dumps(doc, indent=1).encode()


class Analysis(_Paced):
    def run(self, ctx: StageContext) -> None:
        self.pause(ctx)
        ctx.warn(
            "test_pipeline",
            "Test pipeline: the geometry is a fixed synthetic scene, not your video.",
            "warning",
        )


class Exporting(_Paced):
    def run(self, ctx: StageContext) -> None:
        self.pause(ctx)
        report = {
            "note": FIXTURE_NOTE,
            "job_id": ctx.lease.job_id,
            "attempt": ctx.lease.attempt,
            "video_sha256": ctx.lease.video_sha256,
            "keyframes": ctx.lease.keyframe_count,
            "pipeline": "test",
            "generated_at": datetime.now(UTC).isoformat(),
            "limitations": [
                "No reconstruction model ran; outputs are synthetic fixtures.",
                "Coordinates are in an arbitrary local frame with unknown scale.",
            ],
        }
        content = json.dumps(report, indent=2).encode()
        ctx.publish(
            _declare("report", ArtifactKind.REPORT, "application/json", content, final=True),
            content,
        )


class Skip:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def skip_reason(self, lease: WorkerLease) -> str | None:
        return self.reason

    def run(self, ctx: StageContext) -> None:
        raise AssertionError("a skipped stage never runs")


def build_test_pipeline(step_s: float = 0.0) -> dict[StageName, StageAdapter]:
    scene = synthetic_scene()
    return {
        StageName.PREPROCESSING: Preprocessing(step_s),
        StageName.GEOMETRY: Geometry(step_s, scene),
        StageName.DEPTH_PRIORS: Skip(
            "Test pipeline: depth priors (Metric3D-v2) are not integrated."
        ),
        StageName.DYNAMIC_ANALYSIS: Skip(
            "Test pipeline: dynamic-object masking is not integrated."
        ),
        StageName.SENSOR_OPTIMIZATION: Skip("No telemetry was supplied with this mission."),
        StageName.DENSE_RECONSTRUCTION: Dense(step_s, scene),
        StageName.SURFACE_PROCESSING: Skip("Test pipeline: surface extraction is not integrated."),
        StageName.ANALYSIS: Analysis(step_s),
        StageName.EXPORTING: Exporting(step_s),
    }
