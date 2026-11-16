"""Fusion of Fast3R pointmaps with Metric3D-v2 depth/normal priors (numpy only).

Inputs are the Fast3R runner's `result.npz` (per-view pointmaps on a stride grid of the model
input, confidences, poses, moving-object flags, crop info) and, optionally, Metric3D's
per-keyframe metric depth and normals at the original keyframe resolution.

What the priors contribute, each measured and reported:

- **Scale evidence.** Per view, the median ratio of Fast3R camera depth to Metric3D depth gives
  Fast3R units per metre. The spread of that ratio across views says how consistent the two
  are; the median gives an *estimated* metric scale (Fast3R's focal length is itself an
  estimate, so this is never presented as a sensor scale).
- **Normals.** Each fused point carries the Metric3D normal of its pixel, rotated into the
  world frame, so the mesher does not have to guess normals from noisy neighbourhoods.
- **Fill.** Pixels Fast3R was not confident about (often textureless ground) are filled from
  the scaled prior depth, but only in views where prior and Fast3R agree, and only within the
  depth range Fast3R itself observed in that view. Filled points are tagged `depth_prior`.

Moving-object pixels (SAM 2 masks) are excluded from everything.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from nazar_worker.sfm import FrameTransform

F64 = npt.NDArray[np.float64]
U8 = npt.NDArray[np.uint8]

SOURCE_FAST3R, SOURCE_DEPTH = 0, 1
MAX_VIEW_REL_ERR = 0.15
"""A view's prior is used for fill only when it agrees with Fast3R to this median rel. error."""
MIN_AGREEING_PIXELS = 500
MIN_VIEW_COS = 0.2
"""Fast3R points on a surface seen more edge-on than this (|cos| of the angle between the prior
normal and the viewing ray, about 78 degrees) are dropped: the pixel grid stretches there into
sparse parallel stripes that other views do not cover, and they never mesh into a clean surface."""


@dataclass
class Priors:
    """Metric3D outputs per keyframe index (original keyframe resolution)."""

    depth: dict[int, npt.NDArray[np.float32]]
    normals: dict[int, npt.NDArray[np.float32]]
    model: str
    runner: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fused:
    points: F64
    colors: U8
    conf: npt.NDArray[np.float32]
    normals: F64
    """Unit normals in NAZAR axes; zero where no prior normal was available."""
    source: U8
    cameras: F64
    """Centre (NAZAR frame) of the camera that observed each point."""
    stats: dict[str, Any] = field(default_factory=dict)


def _pixel_grid(data: Any, v: int) -> tuple[F64, F64]:
    """Original-keyframe pixel coordinates of view v's stride grid."""
    h, w = data["conf"].shape[1:]
    st = int(data["stride"])
    factor, left, top = data["crop"][v]
    xs = (np.arange(w) * st + left) / factor
    ys = (np.arange(h) * st + top) / factor
    gx, gy = np.meshgrid(xs, ys)
    return gx, gy


def _sample(img: npt.NDArray[Any], x: F64, y: F64) -> npt.NDArray[Any]:
    h, w = img.shape[:2]
    xi = np.clip(np.round(x).astype(int), 0, w - 1)
    yi = np.clip(np.round(y).astype(int), 0, h - 1)
    out: npt.NDArray[Any] = img[yi, xi]
    return out


def view_scales(data: Any, keep: npt.NDArray[np.bool_], priors: Priors) -> dict[str, Any]:
    """Per-view Fast3R-units-per-metre and agreement of the prior with Fast3R's own depth."""
    views = [int(k) for k in data["views"]]
    out: dict[int, dict[str, float]] = {}
    for v, kf in enumerate(views):
        if kf not in priors.depth:
            continue
        x, y = _pixel_grid(data, v)
        d_prior = _sample(priors.depth[kf], x, y).astype(np.float64)
        w2c = np.linalg.inv(data["c2w"][v])
        cam = data["pts"][v].reshape(-1, 3) @ w2c[:3, :3].T + w2c[:3, 3]
        z = cam[:, 2].reshape(d_prior.shape)
        ok = keep[v] & (d_prior > 0.1) & (d_prior < 290) & (z > 0)
        if ok.sum() < MIN_AGREEING_PIXELS:
            continue
        ratio = z[ok] / d_prior[ok]
        s = float(np.median(ratio))
        rel = float(np.median(np.abs(z[ok] - s * d_prior[ok]) / z[ok]))
        out[v] = {"units_per_metre": s, "median_rel_err": rel, "pixels": int(ok.sum())}
    return {"views": out}


FILL_WINDOW = 7
"""Half-size (grid pixels) of the neighbourhood a fill pixel must share with real Fast3R points."""
FILL_MIN_SUPPORT = 0.2
"""Fraction of that neighbourhood that must be real Fast3R points."""
FILL_DEPTH_TOL = 0.08
"""Prior depth must be within this relative distance of the neighbouring Fast3R depth."""


def _box_sum(a: F64, r: int) -> F64:
    """Sum of `a` over a (2r+1)^2 window (zero padded), via an integral image."""
    pad = np.pad(a, ((r + 1, r), (r + 1, r)))
    c = pad.cumsum(0).cumsum(1)
    n = 2 * r + 1
    out: F64 = c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]
    return out


def _fillable(keep: npt.NDArray[np.bool_], z: F64, rgb: U8, d: F64) -> npt.NDArray[np.bool_]:
    """Where the depth prior may fill a Fast3R hole without inventing floaters.

    Filling every low-confidence pixel from the prior adds sky and smeared depth edges, which
    buries the real scene. A pixel qualifies only if (1) enough real Fast3R points lie around it,
    (2) the prior depth agrees with their mean depth, and (3) it is not sky-coloured.
    """
    kf = keep.astype(np.float64)
    support = _box_sum(kf, FILL_WINDOW) / float((2 * FILL_WINDOW + 1) ** 2)
    zsum = _box_sum(kf * z, FILL_WINDOW)
    ksum = _box_sum(kf, FILL_WINDOW)
    local = np.divide(zsum, ksum, out=np.zeros_like(zsum), where=ksum > 0)
    agrees = np.abs(d - local) <= FILL_DEPTH_TOL * np.maximum(local, 1e-9)
    near = (support >= FILL_MIN_SUPPORT) & agrees
    c = rgb.astype(np.int16)
    sky = (c[..., 2] > c[..., 0] + 12) & (c[..., 2] >= c[..., 1])
    out: npt.NDArray[np.bool_] = near & ~sky
    return out


def fuse(
    npz: Path,
    tf: FrameTransform,
    keep_thr: float,
    priors: Priors | None,
    max_points: int,
) -> Fused:
    data = np.load(npz)
    conf = data["conf"]
    dyn = data["dyn"] if "dyn" in data.files else np.zeros(conf.shape, bool)
    keep = (conf >= keep_thr) & ~dyn
    views = [int(k) for k in data["views"]]
    centres_cv = data["c2w"][:, :3, 3]

    pts_l, col_l, conf_l, nrm_l, src_l, cam_l = [], [], [], [], [], []
    stats: dict[str, Any] = {
        "fast3r_pixels": int(conf.size),
        "fast3r_kept": int(keep.sum()),
        "moving_object_pixels_excluded": int(dyn.sum()),
    }
    scales = view_scales(data, keep, priors) if priors is not None else {"views": {}}
    agree = {v: s for v, s in scales["views"].items() if s["median_rel_err"] <= MAX_VIEW_REL_ERR}
    filled = 0
    with_normal = 0
    grazing_dropped = 0
    for v, kf in enumerate(views):
        rot = data["c2w"][v][:3, :3]
        k = keep[v]
        if priors is not None and kf in priors.normals:
            xg, yg = _pixel_grid(data, v)
            ncam = _sample(priors.normals[kf], xg, yg).astype(np.float64)
            ray = data["pts"][v].reshape(-1, 3) - data["c2w"][v][:3, 3]
            ray = (ray / np.maximum(np.linalg.norm(ray, axis=1, keepdims=True), 1e-12)).reshape(
                ncam.shape
            )
            cos = np.abs(np.einsum("hwc,hwc->hw", ncam @ rot.T, ray))
            grazing = k & (cos < MIN_VIEW_COS)
            grazing_dropped += int(grazing.sum())
            k = k & ~grazing
        p = data["pts"][v][k].astype(np.float64)
        n = np.zeros_like(p)
        x = y = None
        if priors is not None and kf in priors.normals:
            x, y = _pixel_grid(data, v)
            nc = _sample(priors.normals[kf], x[k], y[k]).astype(np.float64)
            n = nc @ rot.T
            with_normal += len(p)
        pts_l.append(p)
        col_l.append(data["rgb"][v][k])
        conf_l.append(conf[v][k])
        nrm_l.append(n)
        src_l.append(np.full(len(p), SOURCE_FAST3R, np.uint8))
        cam_l.append(np.repeat(centres_cv[v][None], len(p), 0))
        if priors is None or v not in agree or x is None or y is None:
            continue
        # Fill: pixels Fast3R rejected for low confidence (not moving objects).
        hole = ~keep[v] & ~dyn[v]
        d = _sample(priors.depth[kf], x, y).astype(np.float64) * agree[v]["units_per_metre"]
        w2c = np.linalg.inv(data["c2w"][v])
        cam = data["pts"][v][k].astype(np.float64) @ w2c[:3, :3].T + w2c[:3, 3]
        lo, hi = np.percentile(cam[:, 2], 1), np.percentile(cam[:, 2], 99)
        zgrid = np.zeros(k.shape, np.float64)
        zgrid[k] = cam[:, 2]
        hole &= (d >= 0.95 * lo) & (d <= 1.05 * hi)
        hole &= _fillable(k, zgrid, data["rgb"][v], d)
        if not hole.any():
            continue
        h_in, w_in = conf.shape[1:]
        st = int(data["stride"])
        f = float(data["focal"][v])
        W, H = (int(a) for a in data["input_size"])
        cols, rows = np.meshgrid(np.arange(w_in) * st, np.arange(h_in) * st)
        rays = np.stack([(cols - W / 2) / f, (rows - H / 2) / f, np.ones_like(cols, float)], -1)
        pc = rays[hole] * d[hole][:, None]
        pw = pc @ rot.T + data["c2w"][v][:3, 3]
        nc = _sample(priors.normals[kf], x[hole], y[hole]).astype(np.float64)
        pts_l.append(pw)
        col_l.append(data["rgb"][v][hole])
        conf_l.append(np.zeros(len(pw), np.float32))
        nrm_l.append(nc @ rot.T)
        src_l.append(np.full(len(pw), SOURCE_DEPTH, np.uint8))
        cam_l.append(np.repeat(centres_cv[v][None], len(pw), 0))
        filled += len(pw)

    pts_cv = np.concatenate(pts_l)
    nrm_cv = np.concatenate(nrm_l)
    has_n = np.linalg.norm(nrm_cv, axis=1) > 0.5
    pts = tf.points(pts_cv)
    normals = np.zeros_like(pts)
    normals[has_n] = tf.directions(nrm_cv[has_n])
    cams = tf.points(np.concatenate(cam_l))
    colors = np.concatenate(col_l)
    confs = np.concatenate(conf_l).astype(np.float32)
    source = np.concatenate(src_l)
    stats.update(
        depth_prior_filled=filled,
        grazing_points_dropped=grazing_dropped,
        samples_with_prior_normal=int(has_n.sum()),
    )
    if priors is not None:
        per_view = scales["views"]
        stats["prior_views_compared"] = len(per_view)
        stats["prior_views_agreeing"] = len(agree)
        if per_view:
            s = np.array([sv["units_per_metre"] for sv in per_view.values()])
            rel = np.array([sv["median_rel_err"] for sv in per_view.values()])
            stats["prior_median_rel_err"] = round(float(np.median(rel)), 4)
            stats["scale_spread_rel"] = round(float(np.std(s) / np.mean(s)), 4)
            # NAZAR units per metre = Fast3R units per metre * transform scale.
            stats["metres_per_unit_estimated"] = round(1.0 / (float(np.median(s)) * tf.scale), 6)
    out = _voxel_reduce(pts, colors, confs, normals, source, cams, max_points)
    out.stats = {**stats, "fused_points": len(out.points), "voxel_size": out.stats["voxel_size"]}
    return out


def _voxel_reduce(
    pts: F64,
    colors: U8,
    conf: npt.NDArray[np.float32],
    normals: F64,
    source: U8,
    cams: F64,
    target: int,
) -> Fused:
    """Average per voxel, growing the voxel until at most `target` points remain."""
    if len(pts) <= target:
        return Fused(pts, colors, conf, normals, source, cams, {"voxel_size": 0.0})
    lo = pts.min(axis=0)
    extent = float(np.max(np.percentile(pts, 99, axis=0) - np.percentile(pts, 1, axis=0)))
    voxel = extent / 4000 or 1e-6
    while True:
        cell = np.floor((pts - lo) / voxel).astype(np.int64)
        key = (cell[:, 0] * 2_000_003 + cell[:, 1]) * 2_000_029 + cell[:, 2]
        uniq, first, inv = np.unique(key, return_index=True, return_inverse=True)
        if len(uniq) <= target:
            break
        voxel *= 1.3
    cnt = np.bincount(inv).astype(np.float64)

    def mean(a: npt.NDArray[Any]) -> F64:
        return np.stack([np.bincount(inv, weights=a[:, i]) / cnt for i in range(a.shape[1])], 1)

    nsum = mean(normals)
    norm = np.linalg.norm(nsum, axis=1, keepdims=True)
    nrm = np.where(norm > 1e-6, nsum / np.maximum(norm, 1e-12), 0.0)
    # A voxel counts as Fast3R-observed if any Fast3R point supports it.
    src = np.where(np.bincount(inv, weights=(source == SOURCE_FAST3R)) > 0, 0, 1).astype(np.uint8)
    return Fused(
        points=mean(pts),
        colors=mean(colors.astype(np.float64)).round().clip(0, 255).astype(np.uint8),
        conf=(np.bincount(inv, weights=conf) / cnt).astype(np.float32),
        normals=nrm,
        source=src,
        cameras=cams[first],
        stats={"voxel_size": round(voxel, 6)},
    )
