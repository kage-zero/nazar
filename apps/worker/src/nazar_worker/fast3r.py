"""Fast3R geometry: run the model in its own GPU environment and convert the result.

The worker's environment stays free of torch. Fast3R (FAIR Noncommercial Research License;
approved for this academic project) runs in a separate interpreter configured by:

    NAZAR_FAST3R_PYTHON    interpreter of the GPU environment (torch + fast3r installed)
    NAZAR_FAST3R_WEIGHTS   local checkpoint directory (Fast3R_ViT_Large_512)
    NAZAR_FAST3R_MAX_VIEWS views per forward pass (default 0: sized from free VRAM)

The runner (`apps/worker/gpu/fast3r_runner.py`) streams JSON events and writes npz results.
This module converts them into NAZAR's local frame (see `sfm.to_nazar_frame`) and reduces
the dense pointmaps to a browser-sized cloud.
"""

import json
import logging
import os
import queue
import re
import subprocess
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from nazar_worker.gpu import runner_env
from nazar_worker.sfm import FrameTransform, nazar_frame_transform

F64 = npt.NDArray[np.float64]
U8 = npt.NDArray[np.uint8]

log = logging.getLogger("nazar_worker")

RUNNER = Path(__file__).resolve().parents[2] / "gpu" / "fast3r_runner.py"
MODEL = "Fast3R ViT-L/512"
WEIGHTS_REVISION = "jedyang97/Fast3R_ViT_Large_512@a2c770b"
SOURCE_COMMIT = "facebookresearch/fast3r@33104d4"
KEEP_MIN_CONF = 3.0
KEEP_QUANTILE = 25.0
"""A pixel is kept when its confidence is >= KEEP_MIN_CONF and >= this per-job percentile."""
OBSERVED_MIN_CONF = 10.0
"""Kept points with model confidence >= this are labelled observed (heuristic, absolute so
the share is comparable between jobs; Fast3R confidence is 1 + exp(x) >= 1)."""


class Fast3rFailed(Exception):
    def __init__(self, message: str, *, oom: bool = False, max_views: int | None = None) -> None:
        super().__init__(message)
        self.oom = oom
        self.max_views = max_views  # chunk size that ran out of memory, when known


@dataclass(frozen=True)
class Fast3rRuntime:
    python: Path
    weights: Path
    max_views: int = 0  # 0 = let the runner size chunks from free VRAM
    runner: Path = RUNNER

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "Fast3rRuntime | str":
        """The configured runtime, or the reason it is unavailable (shown to users). Reading
        the process environment (no `env` given), unset paths default to the main GPU
        environment and weights installed by `scripts/setup_gpu.py`, when present."""
        defaults = env is None
        env = dict(os.environ) if env is None else env
        python, weights = env.get("NAZAR_FAST3R_PYTHON", ""), env.get("NAZAR_FAST3R_WEIGHTS", "")
        if defaults:
            from nazar_worker.gpu import GpuRuntime

            gpu = GpuRuntime.from_env(env)
            if not python and "NAZAR_FAST3R_PYTHON" not in env and gpu.main_python is not None:
                python = str(gpu.main_python)
            if not weights and (gpu.weights / "Fast3R_ViT_Large_512").is_dir():
                weights = str(gpu.weights / "Fast3R_ViT_Large_512")
        if not python or not weights:
            return "Fast3R is not configured on this worker (NAZAR_FAST3R_PYTHON/WEIGHTS)."
        if not Path(python).is_file():
            return "The configured Fast3R Python interpreter does not exist."
        if not (Path(weights) / "model.safetensors").is_file():
            return "The configured Fast3R weights directory has no model.safetensors."
        if not RUNNER.is_file():
            return "The Fast3R runner script is missing from this worker."
        try:
            max_views = max(0, int(env.get("NAZAR_FAST3R_MAX_VIEWS", "0")))
        except ValueError:
            max_views = 0
        return Fast3rRuntime(Path(python), Path(weights), max_views)


@dataclass
class DenseCloud:
    """A Fast3R result in NAZAR coordinates, reduced to a browser-sized cloud."""

    points: F64
    colors: U8
    conf: npt.NDArray[np.float32]
    centers: F64
    """Camera centres of the placed keyframes, ordered by keyframe index."""
    views: list[int]
    focal_px: float
    """Median focal length, in pixels of the original keyframe width."""
    final: bool
    stats: dict[str, Any] = field(default_factory=dict)
    transform: FrameTransform | None = None
    """Fast3R frame -> NAZAR frame, reused by depth fusion and the splat cameras."""
    npz: Path | None = None
    keep_thr: float = KEEP_MIN_CONF


def voxel_downsample(
    xyz: F64, rgb: U8, conf: npt.NDArray[np.float32], target: int
) -> tuple[F64, U8, npt.NDArray[np.float32], float]:
    """Average points per voxel, growing the voxel until at most `target` remain."""
    if len(xyz) <= target:
        return xyz, rgb, conf, 0.0
    lo = xyz.min(axis=0)
    extent = float(np.max(np.percentile(xyz, 99, axis=0) - np.percentile(xyz, 1, axis=0)))
    voxel = extent / 4000 or 1e-6
    while True:
        cell = np.floor((xyz - lo) / voxel).astype(np.int64)
        key = (cell[:, 0] * 2_000_003 + cell[:, 1]) * 2_000_029 + cell[:, 2]
        uniq, inv = np.unique(key, return_inverse=True)
        if len(uniq) <= target:
            break
        voxel *= 1.3
    n = np.bincount(inv).astype(np.float64)
    out = np.stack([np.bincount(inv, weights=xyz[:, i]) / n for i in range(3)], axis=1)
    col = np.stack([np.bincount(inv, weights=rgb[:, i]) / n for i in range(3)], axis=1)
    cf = np.bincount(inv, weights=conf) / n
    return out, col.round().astype(np.uint8), cf.astype(np.float32), voxel


def load_cloud(
    path: Path, total_frames: int, original_width: int, *, final: bool, max_points: int
) -> DenseCloud:
    data = np.load(path)
    pts, conf, rgb = data["pts"], data["conf"], data["rgb"]
    keep_thr = max(KEEP_MIN_CONF, float(np.percentile(conf, KEEP_QUANTILE)))
    mask = conf >= keep_thr
    if "dyn" in data.files:
        mask &= ~data["dyn"]  # moving objects (SAM 2 masks) never enter the cloud
    xyz_cv = pts[mask].astype(np.float64)
    centers_cv = data["c2w"][:, :3, 3].astype(np.float64)
    tf, plane = nazar_frame_transform(xyz_cv, centers_cv)
    xyz, centers = tf.points(xyz_cv), tf.points(centers_cv)
    down, cols, cf, voxel = voxel_downsample(xyz, rgb[mask], conf[mask], max_points)
    focal = float(np.median(data["focal"])) * original_width / float(data["input_size"][0])
    views = [int(v) for v in data["views"]]
    return DenseCloud(
        points=down,
        colors=cols,
        conf=cf,
        centers=centers,
        views=views,
        focal_px=focal,
        final=final,
        transform=tf,
        npz=path,
        keep_thr=keep_thr,
        stats={
            "placed_keyframes": len(views),
            "total_keyframes": total_frames,
            "pixels": int(conf.size),
            "pixels_kept": int(mask.sum()),
            "confidence_keep_threshold": round(keep_thr, 3),
            "voxel_size": round(voxel, 5),
            "plane_inlier_share": round(plane, 3),
        },
    )


_NOISE = re.compile(r"Warning|warnings\.warn|^\s{2,}\S")


def run_fast3r(
    runtime: Fast3rRuntime,
    images: list[U8],
    workdir: Path,
    check_cancel: Callable[[], None],
    on_event: Callable[[dict[str, Any]], None] = lambda e: None,
    *,
    max_views: int | None = None,
    masks: Path | None = None,
    budget_mib: int = 0,
    preview_points: int = 120_000,
    final_points: int = 300_000,
) -> Iterator[DenseCloud]:
    """Yield a preview cloud after each chunk and the final cloud last. Raises
    `Fast3rFailed` (with `oom` set on CUDA out-of-memory). `check_cancel` may raise; the
    runner process is killed before the exception propagates. `masks` holds moving-object
    masks (one PNG per keyframe, same stem); `budget_mib` caps the runner's GPU memory."""
    frames = workdir / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(images):
        cv2.imwrite(str(frames / f"{i:04d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    width = int(images[0].shape[1])
    cmd = [
        str(runtime.python),
        "-X",
        "faulthandler",  # a native crash still prints a Python traceback to stderr
        str(runtime.runner),
        "--budget-mib",
        str(budget_mib),
        *(["--masks", str(masks)] if masks is not None else []),
        "--frames",
        str(frames),
        "--weights",
        str(runtime.weights),
        "--out",
        str(workdir / "out"),
        "--max-views",
        str(runtime.max_views if max_views is None else max_views),
    ]
    env = runner_env(os.environ)
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv to a configured local interpreter
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        raise Fast3rFailed(f"The Fast3R interpreter could not be started ({exc}).") from exc
    lines: queue.Queue[str | None] = queue.Queue()
    stderr_tail: list[str] = []

    def pump_out() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    def pump_err() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())
            del stderr_tail[:-40]

    threading.Thread(target=pump_out, daemon=True).start()
    threading.Thread(target=pump_err, daemon=True).start()
    error: dict[str, Any] | None = None
    done = False
    try:
        while True:
            check_cancel()
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except ValueError:
                continue  # library chatter on stdout
            on_event(event)
            kind = event.get("event")
            if kind == "chunk":
                yield load_cloud(
                    Path(event["path"]), len(images), width, final=False, max_points=preview_points
                )
            elif kind == "done":
                cloud = load_cloud(
                    Path(event["path"]), len(images), width, final=True, max_points=final_points
                )
                cloud.stats.update(
                    peak_vram_mib=event.get("peak_vram_mib"),
                    peak_host_commit_mib=event.get("peak_host_commit_mib"),
                    chunks=event.get("chunks"),
                    max_views=event.get("max_views"),
                    chunk_alignment=event.get("alignment"),
                    runner_timings_s=event.get("timings"),
                    torch=event.get("torch"),
                )
                done = True
                yield cloud
            elif kind == "error":
                error = event
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    if not done:
        log.warning("Fast3R runner failed (exit %s):\n%s", proc.returncode, "\n".join(stderr_tail))
        if error is not None:
            ran = error.get("max_views")
            raise Fast3rFailed(
                str(error.get("message", "Fast3R failed")),
                oom=error.get("kind") == "oom",
                max_views=ran if isinstance(ran, int) else None,
            )
        useful = [ln for ln in stderr_tail if ln.strip() and not _NOISE.search(ln)]
        tail = " | ".join(useful[-3:])[:400]
        raise Fast3rFailed(f"Fast3R exited with code {proc.returncode}. {tail}".strip())
