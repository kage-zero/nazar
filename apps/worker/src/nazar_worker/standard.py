"""Standard pipeline: real geometry from the uploaded video's keyframes.

Geometry comes from Fast3R when this worker has the GPU runtime configured (see `fast3r.py`),
otherwise from the classical CPU SfM baseline (`sfm.py`). When Fast3R is configured but fails
(e.g. out of GPU memory even with smaller batches), the job falls back to the baseline and
says so in a warning, the report and every artifact's provenance; it never substitutes
silently. Stages whose models are not installed (Metric3D-v2, YOLO/SAM2, InstantSplat) are
skipped with a reason, never faked.
"""

import hashlib
import json
import platform
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
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
from nazar_worker import fast3r
from nazar_worker.fast3r import DenseCloud, Fast3rFailed, Fast3rRuntime, run_fast3r
from nazar_worker.ply import ESTIMATED, OBSERVED, write_ply_arrays
from nazar_worker.sfm import SfmFailed, SfmSettings, Snapshot, reconstruct
from nazar_worker.stages import StageAdapter, StageContext, StageFailed

SFM = "sfm"
FAST3R = "fast3r"
PRODUCERS = {SFM: "nazar-worker/sfm-baseline", FAST3R: "nazar-worker/fast3r"}
MODELS = {
    SFM: "Classical SfM baseline (OpenCV SIFT + PnP + SciPy bundle adjustment)",
    FAST3R: fast3r.MODEL,
}
LOCAL_FRAME = CoordinateFrame(
    type=FrameType.LOCAL_RECONSTRUCTION, units="unitless", scale_status=ScaleStatus.UNKNOWN
)
FRAME_NOTE = "local frame, +Y up (estimated from dominant plane), unitless, unknown absolute scale"
PLY_NOTES = {
    SFM: f"NAZAR classical SfM baseline - sparse points from the video keyframes; {FRAME_NOTE}",
    FAST3R: f"NAZAR Fast3R - dense points predicted from the input video keyframes; {FRAME_NOTE}",
}
OBSERVED_MIN_VIEWS = 3
OBSERVED_MAX_PX = 1.0
MIN_FAST3R_VIEWS = 4


def _provenance(method: str) -> Provenance:
    if method == FAST3R:
        version = f"{fast3r.SOURCE_COMMIT}; weights {fast3r.WEIGHTS_REVISION}"
        settings = json.dumps(
            {
                "keep_min_conf": fast3r.KEEP_MIN_CONF,
                "keep_quantile": fast3r.KEEP_QUANTILE,
                "observed_min_conf": fast3r.OBSERVED_MIN_CONF,
            },
            sort_keys=True,
        ).encode()
    else:
        version = f"opencv {cv2.__version__}; scipy {scipy.__version__}"
        settings = json.dumps(SfmSettings().__dict__, sort_keys=True).encode()
    return Provenance(
        producer=PRODUCERS[method],
        model=MODELS[method],
        model_version=version,
        config_hash=hashlib.sha256(settings).hexdigest()[:16],
        test_pipeline=False,
    )


@dataclass
class _Run:
    """State handed from stage to stage within one job attempt."""

    runtime: Fast3rRuntime | str
    images: list[npt.NDArray[np.uint8]] = field(default_factory=list)
    keyframe_index: list[int] = field(default_factory=list)
    """Source video frame index of each keyframe image."""
    method: str = SFM
    fallback_reason: str | None = None
    snapshot: Snapshot | None = None
    dense: DenseCloud | None = None
    gpu: dict[str, Any] = field(default_factory=dict)
    keep: npt.NDArray[np.bool_] | None = None
    timings: dict[str, float] = field(default_factory=dict)
    first_preview_s: float | None = None
    started: float = field(default_factory=time.monotonic)

    # The final geometry, whichever method produced it.
    def points(self) -> npt.NDArray[np.float64]:
        if self.dense is not None:
            return self.dense.points
        assert self.snapshot is not None
        return self.snapshot.points

    def placed(self) -> list[int]:
        if self.dense is not None:
            return self.dense.views
        assert self.snapshot is not None
        return self.snapshot.registered

    def observed_mask(self) -> npt.NDArray[np.bool_]:
        assert self.keep is not None
        if self.dense is not None:
            return np.asarray(self.dense.conf[self.keep] >= fast3r.OBSERVED_MIN_CONF)
        assert self.snapshot is not None
        views, errs = self.snapshot.views[self.keep], self.snapshot.errors[self.keep]
        return np.asarray((views >= OBSERVED_MIN_VIEWS) & (errs <= OBSERVED_MAX_PX))


def _declare(
    run: _Run,
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
        provenance=_provenance(run.method),
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
    """Fast3R when available, else the SfM baseline; every intermediate state is published as
    a preview revision."""

    revision = 0

    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        t0 = time.monotonic()
        if isinstance(run.runtime, Fast3rRuntime):
            try:
                self._fast3r(ctx, run.runtime)
            except Fast3rFailed as exc:
                run.fallback_reason = str(exc)
                run.dense, run.gpu = None, {}
                ctx.warn(
                    "fast3r_fallback",
                    "Fast3R could not run on this job, so the CPU baseline (classical "
                    f"structure-from-motion) was used instead. Reason: {str(exc)[:200]}",
                    "warning",
                )
        if run.dense is None:
            run.method = SFM
            self._sfm(ctx)
        run.timings["geometry_s"] = round(time.monotonic() - t0, 3)

    def _fast3r(self, ctx: StageContext, runtime: Fast3rRuntime) -> None:
        run = self.run_state
        run.method = FAST3R
        total = len(run.images)
        max_views = runtime.max_views
        while True:
            per_pass = f"{max_views} views per pass" if max_views else "sizing passes to GPU memory"
            ctx.progress(f"Fast3R: loading the model ({per_pass})", 0, total, "keyframes")

            def on_event(event: dict[str, Any]) -> None:
                if event.get("event") == "loaded":
                    run.gpu.update(device=event.get("device"), load_s=event.get("seconds"))
                    ctx.progress("Fast3R: predicting pointmaps", 0, total, "keyframes")
                elif event.get("event") == "retry":
                    ctx.warn(
                        "fast3r_smaller_batches",
                        f"The GPU ran out of memory; Fast3R continued with {event.get('max_views')}"
                        " views per pass (chunks are aligned on shared keyframes).",
                        "info",
                    )

            try:
                with tempfile.TemporaryDirectory(prefix="nazar-fast3r-") as tmp:
                    for cloud in run_fast3r(
                        runtime,
                        run.images,
                        Path(tmp),
                        ctx.check_cancel,
                        on_event,
                        max_views=max_views,
                    ):
                        if cloud.final:
                            run.dense = cloud
                        else:
                            self._preview(ctx, cloud.points, cloud.colors, cloud.views, total)
                break
            except Fast3rFailed as exc:
                ran = exc.max_views or max_views
                if not exc.oom or ran // 2 < MIN_FAST3R_VIEWS:
                    raise
                max_views = ran // 2
                ctx.warn(
                    "fast3r_smaller_batches",
                    f"The GPU ran out of memory; Fast3R was rerun with {max_views} views per "
                    "pass (chunks are aligned on shared keyframes).",
                    "info",
                )
        assert run.dense is not None
        run.gpu.update(run.dense.stats)
        self._preview(ctx, run.dense.points, run.dense.colors, run.dense.views, total)

    def _sfm(self, ctx: StageContext) -> None:
        run = self.run_state
        total = len(run.images)
        ctx.progress("Matching features between keyframes", 0, total, "keyframes")
        try:
            for snap in reconstruct(run.images, check_cancel=ctx.check_cancel):
                run.snapshot = snap
                if snap.final:
                    break
                self._preview(ctx, snap.points, snap.colors, snap.registered, total)
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

    def _preview(
        self,
        ctx: StageContext,
        points: npt.NDArray[np.float64],
        colors: npt.NDArray[np.uint8],
        placed: list[int],
        total: int,
    ) -> None:
        run = self.run_state
        self.revision += 1
        ply = write_ply_arrays(points, colors, [PLY_NOTES[run.method]])
        ctx.publish(
            _declare(
                run,
                f"preview-{self.revision}",
                ArtifactKind.POINT_CLOUD_PREVIEW,
                "application/vnd.nazar.ply",
                ply,
                xyz=points,
                frames=_frames(run, placed),
                lod=1,
            ),
            ply,
        )
        if run.first_preview_s is None:
            run.first_preview_s = round(time.monotonic() - run.started, 3)
        label = "Fast3R placed" if run.method == FAST3R else "Registered"
        ctx.progress(
            f"{label} {len(placed)} of {total} keyframes · {len(points):,} points",
            len(placed),
            total,
            "keyframes",
        )


class Densify(_Stage):
    """Statistical outlier removal on the final cloud, published with the camera path. For
    Fast3R the cloud is already dense (pointmaps, voxel-averaged); for the baseline it is the
    sparse SfM cloud. No Gaussian/neural scene is built yet."""

    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        t0 = time.monotonic()
        if run.dense is not None:
            pts, cols = run.dense.points, run.dense.colors
            centers, focal = run.dense.centers, run.dense.focal_px
        else:
            assert run.snapshot is not None
            pts, cols = run.snapshot.points, run.snapshot.colors
            centers, focal = run.snapshot.centers, run.snapshot.focal_px
        keep = _statistical_inliers(pts)
        run.keep = keep
        pts, cols = pts[keep], cols[keep]
        what = "dense Fast3R cloud" if run.dense is not None else "sparse cloud"
        ctx.progress(
            f"Filtered {what} ({int((~keep).sum()):,} outliers removed)",
            int(keep.sum()),
            len(keep),
            "points",
        )
        labels = np.where(run.observed_mask(), OBSERVED, ESTIMATED).astype(np.uint8)
        ply = write_ply_arrays(pts, cols, [PLY_NOTES[run.method]], labels)
        ctx.publish(
            _declare(
                run,
                "point-cloud",
                ArtifactKind.POINT_CLOUD,
                "application/vnd.nazar.ply",
                ply,
                xyz=pts,
                frames=_frames(run, run.placed()),
                lod=0,
                final=True,
            ),
            ply,
        )
        poses = [
            {"keyframe": i, "frame_index": run.keyframe_index[i], "position": c.round(5).tolist()}
            for i, c in zip(run.placed(), centers, strict=True)
        ]
        source = (
            "Camera poses estimated by Fast3R (PnP on its pointmaps)"
            if run.method == FAST3R
            else "Camera centres from the classical SfM baseline"
        )
        traj = json.dumps(
            {
                "frame": "local_reconstruction",
                "units": "unitless",
                "note": f"{source}, same frame as the cloud.",
                "focal_px_estimated": round(focal, 2),
                "poses": poses,
            },
            indent=1,
        ).encode()
        ctx.publish(
            _declare(
                run,
                "camera-trajectory",
                ArtifactKind.CAMERA_TRAJECTORY,
                "application/json",
                traj,
                frames=_frames(run, run.placed()),
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
        observed = run.observed_mask()
        n_obs = int(observed.sum())
        ctx.progress(
            f"{n_obs:,} observed / {len(observed) - n_obs:,} estimated points",
            len(observed),
            len(observed),
            "points",
        )
        ctx.warn(
            "scale_unknown",
            "Video only: distances are relative (unitless). Absolute size, height and "
            "geographic position are unknown without telemetry or a known reference length.",
            "warning",
        )
        if run.method == FAST3R:
            ctx.warn(
                "learned_geometry",
                "Geometry is predicted by Fast3R, a learned multi-view model: dense, but "
                "predicted. Confidence is the model's own score, not a measured error.",
                "info",
            )
        else:
            ctx.warn(
                "sparse_baseline",
                "Geometry comes from the CPU baseline (classical structure-from-motion): a "
                "sparse cloud of matched features, not a dense surface.",
                "info",
            )


class Exporting(_Stage):
    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        assert run.keep is not None
        observed = run.observed_mask()
        n_obs = int(observed.sum())
        if run.dense is not None:
            geometry: dict[str, Any] = {
                "method": MODELS[FAST3R],
                "model_version": _provenance(FAST3R).model_version,
                "licence": "FAIR Noncommercial Research License (academic use approved)",
                "placed_keyframes": len(run.dense.views),
                "points_before_filter": len(run.dense.points),
                "points": int(run.keep.sum()),
                "focal_px_estimated": round(run.dense.focal_px, 2),
                "focal_note": "Estimated by Fast3R's global head; not calibrated.",
                **{k: v for k, v in run.gpu.items() if k not in ("device",)},
            }
            rule = (
                f"Pixels with Fast3R confidence below max({fast3r.KEEP_MIN_CONF}, the job's "
                f"{fast3r.KEEP_QUANTILE:.0f}th percentile) are dropped; kept points with "
                f"confidence >= {fast3r.OBSERVED_MIN_CONF} are observed, the rest estimated. "
                "Heuristic labels from the model's own score, not calibrated probabilities."
            )
            resources = {
                "device": run.gpu.get("device") or "GPU",
                "peak_vram_mib": run.gpu.get("peak_vram_mib"),
                "peak_host_commit_mib": run.gpu.get("peak_host_commit_mib"),
                "host": platform.platform(),
            }
            limitations = [
                "Geometry is predicted by a learned model; thin structures and areas seen in "
                "few keyframes can be distorted.",
                "Unknown absolute scale; measurements are relative only.",
                "Up direction is estimated from the dominant plane and may be wrong for "
                "scenes without a ground plane.",
            ]
            surface = "Surface meshing is not implemented yet."
        else:
            snap = run.snapshot
            assert snap is not None
            geometry = {
                # Reconstruction stats first: the explicit fields below must win over them
                # (the final cloud is the filtered one, not the raw SfM output).
                **{k: v for k, v in snap.stats.items() if k not in ("points", "registered")},
                "method": MODELS[SFM],
                "registered_keyframes": len(snap.registered),
                "points_before_filter": len(snap.points),
                "points": int(run.keep.sum()),
                "focal_px_estimated": round(snap.focal_px, 2),
                "focal_note": "Not calibrated: initial guess refined by bundle adjustment.",
            }
            if run.fallback_reason:
                geometry["fast3r_fallback_reason"] = run.fallback_reason
            rule = (
                f"observed = seen by >= {OBSERVED_MIN_VIEWS} keyframes with mean reprojection "
                f"<= {OBSERVED_MAX_PX} px; estimated = everything else. Heuristic labels, not "
                "calibrated probabilities."
            )
            resources = {
                "device": "CPU",
                "peak_vram": "not applicable (CPU only)",
                "host": platform.platform(),
            }
            limitations = [
                "Sparse points only; textureless or repetitive surfaces are missing.",
                "Unknown absolute scale; measurements are relative only.",
                "Up direction is estimated from the dominant plane and may be wrong for "
                "scenes without a ground plane.",
            ]
            surface = "A sparse cloud cannot support a meaningful surface."
        report = {
            "schema": "nazar.processing-report/1",
            "generated_at": datetime.now(UTC).isoformat(),
            "job_id": ctx.lease.job_id,
            "attempt": ctx.lease.attempt,
            "pipeline": "standard",
            "geometry_method": run.method,
            "input": {
                "video_sha256": ctx.lease.video_sha256,
                "keyframes": len(run.images),
                "telemetry": None,
                "image_size": list(run.images[0].shape[1::-1]) if run.images else None,
            },
            "geometry": geometry,
            "confidence": {
                "observed": n_obs,
                "estimated": len(observed) - n_obs,
                "inferred": 0,
                "rule": rule,
            },
            "coordinate_frame": {
                "type": "local_reconstruction",
                "axes": "right-handed, +Y up (estimated from the dominant plane), -Z forward",
                "units": "unitless",
                "scale_status": "unknown",
                "normalisation": "median camera distance from the scene centre = 10 units",
            },
            "timings_s": {**run.timings, "first_preview_s": run.first_preview_s},
            "resources": resources,
            "skipped": {
                "depth_priors": "Metric3D-v2 is not installed on this worker.",
                "dynamic_analysis": "YOLO + SAM2 are not installed on this worker.",
                "sensor_optimization": "No telemetry was supplied.",
                "surface_processing": surface,
            },
            "limitations": limitations,
        }
        content = json.dumps(report, indent=2).encode()
        ctx.publish(
            _declare(run, "report", ArtifactKind.REPORT, "application/json", content, final=True),
            content,
        )


class Skip:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def skip_reason(self, lease: WorkerLease) -> str | None:
        return self.reason

    def run(self, ctx: StageContext) -> None:
        raise AssertionError("a skipped stage never runs")


def build_standard_pipeline(
    runtime: Fast3rRuntime | str | None = None,
) -> dict[StageName, StageAdapter]:
    """`runtime`: the Fast3R runtime, or why it is unavailable; read from the environment
    when omitted."""
    run = _Run(runtime=Fast3rRuntime.from_env() if runtime is None else runtime)
    return {
        StageName.PREPROCESSING: Preprocessing(run),
        StageName.GEOMETRY: Geometry(run),
        StageName.DEPTH_PRIORS: Skip("Metric3D-v2 is not installed on this worker."),
        StageName.DYNAMIC_ANALYSIS: Skip("YOLO + SAM2 are not installed on this worker."),
        StageName.SENSOR_OPTIMIZATION: Skip("No telemetry was supplied with this mission."),
        StageName.DENSE_RECONSTRUCTION: Densify(run),
        StageName.SURFACE_PROCESSING: _SurfaceSkip(run),
        StageName.ANALYSIS: Analysis(run),
        StageName.EXPORTING: Exporting(run),
    }


class _SurfaceSkip(Skip):
    """Skipped either way; the reason depends on which geometry was produced."""

    def __init__(self, run: _Run) -> None:
        super().__init__("")
        self.run_state = run

    def skip_reason(self, lease: WorkerLease) -> str | None:
        if self.run_state.dense is not None:
            return "Surface meshing is not implemented yet; the dense cloud is the final output."
        return (
            "Skipped: a sparse cloud cannot support a meaningful surface; it would be mostly "
            "invented."
        )
