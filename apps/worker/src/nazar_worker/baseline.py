"""Standard pipeline on CPU: real geometry from the video via the classical SfM baseline.

Stages that need GPU models which are not installed on this worker (Fast3R, Metric3D-v2,
YOLO/SAM2, InstantSplat) are skipped with a reason, never faked. Everything published here
is derived from the uploaded video's keyframes; see `sfm.py` for what the geometry is and
is not (sparse, unitless, unknown absolute scale).
"""

import hashlib
import json
import platform
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
import scipy
from scipy.spatial import cKDTree

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
from nazar_worker.ply import write_ply_arrays
from nazar_worker.sfm import SfmFailed, SfmSettings, Snapshot, reconstruct
from nazar_worker.stages import StageAdapter, StageContext, StageFailed

PRODUCER = "nazar-worker/sfm-baseline"
MODEL = "Classical SfM baseline (OpenCV SIFT + PnP + SciPy bundle adjustment)"
LOCAL_FRAME = CoordinateFrame(
    type=FrameType.LOCAL_RECONSTRUCTION, units="unitless", scale_status=ScaleStatus.UNKNOWN
)
PLY_NOTE = (
    "NAZAR classical SfM baseline - sparse points from the input video keyframes; "
    "local frame, +Y up (estimated from dominant plane), unitless, unknown absolute scale"
)
OBSERVED_MIN_VIEWS = 3
OBSERVED_MAX_PX = 1.0


def _provenance() -> Provenance:
    settings = json.dumps(SfmSettings().__dict__, sort_keys=True).encode()
    return Provenance(
        producer=PRODUCER,
        model=MODEL,
        model_version=f"opencv {cv2.__version__}; scipy {scipy.__version__}",
        config_hash=hashlib.sha256(settings).hexdigest()[:16],
        test_pipeline=False,
    )


@dataclass
class _Run:
    """State handed from stage to stage within one job attempt."""

    images: list[npt.NDArray[np.uint8]] = field(default_factory=list)
    keyframe_index: list[int] = field(default_factory=list)
    """Source video frame index of each keyframe image."""
    snapshot: Snapshot | None = None
    keep: npt.NDArray[np.bool_] | None = None
    timings: dict[str, float] = field(default_factory=dict)
    first_preview_s: float | None = None
    started: float = field(default_factory=time.monotonic)


def _declare(
    key: str,
    kind: ArtifactKind,
    media_type: str,
    content: bytes,
    *,
    xyz: npt.NDArray[np.float64] | None = None,
    frames: FrameRange | None = None,
    lod: int | None = None,
    final: bool = False,
    spatial: bool = False,
) -> ArtifactCreate:
    box = None
    if xyz is not None and len(xyz):
        box = Bounds3D(min=xyz.min(axis=0).tolist(), max=xyz.max(axis=0).tolist())
    return ArtifactCreate(
        key=key,
        kind=kind,
        media_type=media_type,
        byte_size=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        frame=LOCAL_FRAME if spatial or xyz is not None else None,
        bounds=box,
        point_count=len(xyz) if xyz is not None else None,
        lod=lod,
        source_frames=frames,
        provenance=_provenance(),
        final=final,
    )


def _frames(run: _Run, used: list[int] | None = None) -> FrameRange | None:
    idx = [run.keyframe_index[i] for i in (used if used is not None else range(len(run.images)))]
    if not idx:
        return None
    return FrameRange(first_index=min(idx), last_index=max(idx), count=len(idx))


class _Stage:
    def __init__(self, run: _Run) -> None:
        self.run_state = run

    def skip_reason(self, lease: WorkerLease) -> str | None:
        return None


class Preprocessing(_Stage):
    """Fetches the keyframes chosen at upload (quality + viewpoint novelty) and decodes them."""

    def run(self, ctx: StageContext) -> None:
        t0 = time.monotonic()
        report = ctx.preflight()
        keyframes = report.get("keyframes", [])
        if len(keyframes) < 3:
            raise StageFailed(
                f"The preflight selected only {len(keyframes)} keyframes; at least 3 are needed."
            )
        for n, kf in enumerate(keyframes, start=1):
            ctx.check_cancel()
            data = np.frombuffer(ctx.keyframe(int(kf["image"])), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                raise StageFailed(f"Keyframe {kf['image']} could not be decoded.")
            self.run_state.images.append(img.astype(np.uint8))
            self.run_state.keyframe_index.append(int(kf["index"]))
            if n % 8 == 0 or n == len(keyframes):
                ctx.progress("Loaded keyframes from preflight", n, len(keyframes), "keyframes")
        self.run_state.timings["preprocessing_s"] = round(time.monotonic() - t0, 3)


class Geometry(_Stage):
    """Incremental SfM; every intermediate snapshot is published as a preview revision."""

    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        t0 = time.monotonic()
        total = len(run.images)
        ctx.progress("Matching features between keyframes", 0, total, "keyframes")
        revision = 0
        try:
            for snap in reconstruct(run.images, check_cancel=ctx.check_cancel):
                run.snapshot = snap
                if snap.final:
                    break
                revision += 1
                self._preview(ctx, snap, revision)
        except SfmFailed as exc:
            raise StageFailed(str(exc)) from exc
        final = run.snapshot
        assert final is not None and final.final
        snap = final
        missing = total - len(snap.registered)
        if missing:
            ctx.warn(
                "unregistered_keyframes",
                f"{missing} of {total} keyframes could not be placed (too little overlap or "
                "parallax with the rest); the cloud covers only what the others see.",
                "warning",
            )
        if len(snap.registered) < max(3, total // 3):
            raise StageFailed(
                f"Only {len(snap.registered)} of {total} keyframes could be reconstructed, "
                "which is too few for a trustworthy result."
            )
        run.timings["geometry_s"] = round(time.monotonic() - t0, 3)

    def _preview(self, ctx: StageContext, snap: Snapshot, revision: int) -> None:
        run = self.run_state
        ply = write_ply_arrays(snap.points, snap.colors, [PLY_NOTE])
        ctx.publish(
            _declare(
                f"preview-{revision}",
                ArtifactKind.POINT_CLOUD_PREVIEW,
                "application/vnd.nazar.ply",
                ply,
                xyz=snap.points,
                frames=_frames(run, snap.registered),
                lod=1,
            ),
            ply,
        )
        if run.first_preview_s is None:
            run.first_preview_s = round(time.monotonic() - run.started, 3)
        ctx.progress(
            f"Registered {len(snap.registered)} of {snap.total_frames} keyframes · "
            f"{len(snap.points):,} points",
            len(snap.registered),
            snap.total_frames,
            "keyframes",
        )


class Densify(_Stage):
    """No dense model is installed on this worker: clean the sparse cloud with statistical
    outlier removal and publish it, with the camera path, as the final geometry."""

    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        t0 = time.monotonic()
        snap = run.snapshot
        assert snap is not None
        keep = _statistical_inliers(snap.points)
        run.keep = keep
        pts, cols = snap.points[keep], snap.colors[keep]
        ctx.progress(
            f"Dense model not installed; filtered sparse cloud ({int((~keep).sum())} outliers "
            "removed)",
            int(keep.sum()),
            len(keep),
            "points",
        )
        ply = write_ply_arrays(pts, cols, [PLY_NOTE])
        ctx.publish(
            _declare(
                "point-cloud",
                ArtifactKind.POINT_CLOUD,
                "application/vnd.nazar.ply",
                ply,
                xyz=pts,
                frames=_frames(run, snap.registered),
                lod=0,
                final=True,
            ),
            ply,
        )
        poses = [
            {"keyframe": i, "frame_index": run.keyframe_index[i], "position": c.round(5).tolist()}
            for i, c in zip(snap.registered, snap.centers, strict=True)
        ]
        traj = json.dumps(
            {
                "frame": "local_reconstruction",
                "units": "unitless",
                "note": "Camera centres from the classical SfM baseline, same frame as the cloud.",
                "focal_px_estimated": round(snap.focal_px, 2),
                "poses": poses,
            },
            indent=1,
        ).encode()
        ctx.publish(
            _declare(
                "camera-trajectory",
                ArtifactKind.CAMERA_TRAJECTORY,
                "application/json",
                traj,
                frames=_frames(run, snap.registered),
                final=True,
                spatial=True,
            ),
            traj,
        )
        run.timings["dense_reconstruction_s"] = round(time.monotonic() - t0, 3)


def _statistical_inliers(points: npt.NDArray[np.float64], k: int = 8, sigma: float = 2.5) -> Any:
    if len(points) <= k:
        return np.ones(len(points), dtype=bool)
    dist, _ = cKDTree(points).query(points, k=k + 1)
    mean = dist[:, 1:].mean(axis=1)
    return mean <= mean.mean() + sigma * mean.std()


class Analysis(_Stage):
    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        snap = run.snapshot
        assert snap is not None and run.keep is not None
        views, errs = snap.views[run.keep], snap.errors[run.keep]
        observed = int(np.sum((views >= OBSERVED_MIN_VIEWS) & (errs <= OBSERVED_MAX_PX)))
        ctx.progress(
            f"{observed:,} observed / {len(views) - observed:,} estimated points",
            len(views),
            len(views),
            "points",
        )
        ctx.warn(
            "scale_unknown",
            "Video only: distances are relative (unitless). Absolute size, height and "
            "geographic position are unknown without telemetry or a known reference length.",
            "warning",
        )
        ctx.warn(
            "sparse_baseline",
            "Geometry comes from the CPU baseline (classical structure-from-motion): a sparse "
            "cloud of matched features, not a dense surface. Fast3R needs the GPU worker.",
            "info",
        )


class Exporting(_Stage):
    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        snap = run.snapshot
        assert snap is not None and run.keep is not None
        views, errs = snap.views[run.keep], snap.errors[run.keep]
        observed = int(np.sum((views >= OBSERVED_MIN_VIEWS) & (errs <= OBSERVED_MAX_PX)))
        report = {
            "schema": "nazar.processing-report/1",
            "generated_at": datetime.now(UTC).isoformat(),
            "job_id": ctx.lease.job_id,
            "attempt": ctx.lease.attempt,
            "pipeline": "standard",
            "input": {
                "video_sha256": ctx.lease.video_sha256,
                "keyframes": len(run.images),
                "telemetry": None,
                "image_size": list(run.images[0].shape[1::-1]) if run.images else None,
            },
            "geometry": {
                # Reconstruction stats first: the explicit fields below must win over them
                # (the final cloud is the filtered one, not the raw SfM output).
                **{k: v for k, v in snap.stats.items() if k not in ("points", "registered")},
                "method": MODEL,
                "registered_keyframes": len(snap.registered),
                "points_before_filter": len(snap.points),
                "points": int(run.keep.sum()),
                "focal_px_estimated": round(snap.focal_px, 2),
                "focal_note": "Not calibrated: initial guess refined by bundle adjustment.",
            },
            "confidence": {
                "observed": observed,
                "estimated": len(views) - observed,
                "inferred": 0,
                "rule": (
                    f"observed = seen by >= {OBSERVED_MIN_VIEWS} keyframes with mean "
                    f"reprojection <= {OBSERVED_MAX_PX} px; estimated = everything else. "
                    "Heuristic labels, not calibrated probabilities."
                ),
            },
            "coordinate_frame": {
                "type": "local_reconstruction",
                "axes": "right-handed, +Y up (estimated from the dominant plane), -Z forward",
                "units": "unitless",
                "scale_status": "unknown",
                "normalisation": "median camera distance from the scene centre = 10 units",
            },
            "timings_s": {**run.timings, "first_preview_s": run.first_preview_s},
            "resources": {
                "device": "CPU",
                "peak_vram": "not applicable (CPU only)",
                "host": platform.platform(),
            },
            "skipped": {
                "depth_priors": "Metric3D-v2 is not installed on this worker (needs GPU).",
                "dynamic_analysis": "YOLO + SAM2 are not installed on this worker (needs GPU).",
                "sensor_optimization": "No telemetry was supplied.",
                "surface_processing": "A sparse cloud cannot support a meaningful surface.",
            },
            "limitations": [
                "Sparse points only; textureless or repetitive surfaces are missing.",
                "Unknown absolute scale; measurements are relative only.",
                "Up direction is estimated from the dominant plane and may be wrong for "
                "scenes without a ground plane.",
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


def build_baseline_pipeline() -> dict[StageName, StageAdapter]:
    run = _Run()
    return {
        StageName.PREPROCESSING: Preprocessing(run),
        StageName.GEOMETRY: Geometry(run),
        StageName.DEPTH_PRIORS: Skip(
            "Metric3D-v2 is not installed on this worker; it needs the GPU environment."
        ),
        StageName.DYNAMIC_ANALYSIS: Skip(
            "YOLO + SAM2 are not installed on this worker; they need the GPU environment."
        ),
        StageName.SENSOR_OPTIMIZATION: Skip("No telemetry was supplied with this mission."),
        StageName.DENSE_RECONSTRUCTION: Densify(run),
        StageName.SURFACE_PROCESSING: Skip(
            "Skipped: a sparse cloud cannot support a meaningful surface; it would be mostly "
            "invented."
        ),
        StageName.ANALYSIS: Analysis(run),
        StageName.EXPORTING: Exporting(run),
    }
