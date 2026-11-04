"""Classical incremental structure-from-motion on CPU (OpenCV + SciPy).

This is NAZAR's CPU geometry *baseline*: real geometry from the uploaded video's keyframes,
not a learned model. It runs where Fast3R cannot (no GPU), and it is what Fast3R output will
be compared against. It is honest about what it is:

- monocular, so the result has **no absolute scale** (`scale_status=unknown`, unitless);
- the focal length is a guess refined by bundle adjustment (no calibration is supplied);
- the cloud is **sparse** (one point per multi-view feature track), not a dense surface;
- the up direction is estimated from the dominant plane, which is usually the ground.

Pipeline: SIFT features → ratio-test matches over a short window → essential-matrix RANSAC
→ two-view initialisation from the pair with the best parallax → incremental PnP registration
→ track triangulation with angle and reprojection checks → bundle adjustment (SciPy, Huber
loss, sparse Jacobian, shared focal length) → outlier filtering → plane-based up alignment.

Coordinates leave this module in NAZAR's convention: right-handed, +Y up, -Z forward.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix

F64 = npt.NDArray[np.float64]
U8 = npt.NDArray[np.uint8]

# OpenCV cameras look down +Z with +Y down; NAZAR (three.js) looks down -Z with +Y up.
CV_TO_NAZAR = np.diag([1.0, -1.0, -1.0])


@dataclass(frozen=True)
class SfmSettings:
    max_features: int = 4000
    ratio: float = 0.75
    match_window: int = 12
    """Each keyframe is matched with the next `match_window` keyframes."""
    ransac_px: float = 1.5
    min_pair_inliers: int = 30
    min_pnp_inliers: int = 25
    max_reproj_px: float = 4.0
    min_angle_deg: float = 1.5
    focal_guess: float = 0.75
    """Initial focal length as a fraction of image width (≈67° horizontal FOV)."""
    ba_every: int = 4
    """Run bundle adjustment after every N newly registered keyframes."""


@dataclass
class Snapshot:
    """One state of the reconstruction, already in NAZAR coordinates."""

    points: F64
    colors: U8
    views: npt.NDArray[np.int32]
    """Number of registered keyframes that observe each point (track support)."""
    errors: F64
    """Mean reprojection error per point, in pixels."""
    centers: F64
    """Camera centres of registered keyframes, ordered by keyframe index."""
    registered: list[int]
    total_frames: int
    focal_px: float
    final: bool
    stats: dict[str, float | int] = field(default_factory=dict)


class SfmFailed(Exception):
    """The keyframes do not support a reconstruction; the message says why, for users."""


@dataclass
class _Frame:
    image: U8
    keypoints: F64
    descriptors: npt.NDArray[np.float32]
    colors: U8


class _Tracks:
    """Union-find over (frame, keypoint) observations, then compacted into tracks."""

    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, a: tuple[int, int]) -> tuple[int, int]:
        self.parent.setdefault(a, a)
        root = a
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[a] != root:
            self.parent[a], a = root, self.parent[a]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def build(self) -> list[dict[int, int]]:
        groups: dict[tuple[int, int], dict[int, int]] = {}
        conflicted: set[tuple[int, int]] = set()
        for obs in list(self.parent):
            root = self.find(obs)
            track = groups.setdefault(root, {})
            frame, kp = obs
            if frame in track and track[frame] != kp:
                conflicted.add(root)  # two keypoints of one image merged: ambiguous track
            track[frame] = kp
        return [t for r, t in groups.items() if r not in conflicted and len(t) >= 2]


def _features(images: Sequence[U8], s: SfmSettings) -> list[_Frame]:
    sift = cv2.SIFT.create(nfeatures=s.max_features)
    frames = []
    for img in images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kps, desc = sift.detectAndCompute(gray, None)
        pts = np.array([k.pt for k in kps], dtype=np.float64).reshape(-1, 2)
        ij = np.clip(np.round(pts).astype(int), 0, [img.shape[1] - 1, img.shape[0] - 1])
        colors = img[ij[:, 1], ij[:, 0], ::-1].astype(np.uint8)  # BGR → RGB
        if desc is None:
            desc = np.zeros((0, 128), np.float32)
        frames.append(_Frame(img, pts, desc.astype(np.float32), colors))
    return frames


def _match(a: _Frame, b: _Frame, k: F64, s: SfmSettings) -> npt.NDArray[np.int64] | None:
    """Mutual ratio-test matches that survive essential-matrix RANSAC, as (ia, ib) rows."""
    if len(a.descriptors) < 8 or len(b.descriptors) < 8:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    def ratio(d1: npt.NDArray[np.float32], d2: npt.NDArray[np.float32]) -> dict[int, int]:
        out = {}
        for pair in matcher.knnMatch(d1, d2, k=2):
            if len(pair) == 2 and pair[0].distance < s.ratio * pair[1].distance:
                out[pair[0].queryIdx] = pair[0].trainIdx
        return out

    fwd, bwd = ratio(a.descriptors, b.descriptors), ratio(b.descriptors, a.descriptors)
    pairs = np.array([(i, j) for i, j in fwd.items() if bwd.get(j) == i], dtype=np.int64)
    if len(pairs) < s.min_pair_inliers:
        return None
    _, mask = cv2.findEssentialMat(
        a.keypoints[pairs[:, 0]],
        b.keypoints[pairs[:, 1]],
        k,
        method=cv2.RANSAC,
        prob=0.999,
        threshold=s.ransac_px,
    )
    if mask is None:
        return None
    inliers = pairs[mask.ravel().astype(bool)]
    return inliers if len(inliers) >= s.min_pair_inliers else None


def _intrinsics(f: float, w: int, h: int) -> F64:
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)


def _project(k: F64, rvec: F64, tvec: F64, x: F64) -> F64:
    proj, _ = cv2.projectPoints(x.reshape(-1, 1, 3), rvec, tvec, k, None)
    return np.asarray(proj, dtype=np.float64).reshape(-1, 2)


def _angle_deg(c1: F64, c2: F64, x: F64) -> F64:
    a, b = x - c1, x - c2
    cos = np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


class _Recon:
    def __init__(self, frames: list[_Frame], tracks: list[dict[int, int]], f: float) -> None:
        self.frames, self.tracks, self.f = frames, tracks, f
        h, w = frames[0].image.shape[:2]
        self.w, self.h = w, h
        self.rvecs: dict[int, F64] = {}
        self.tvecs: dict[int, F64] = {}
        self.xyz: dict[int, F64] = {}  # track id → 3D point (OpenCV world = first camera)
        self.by_frame: dict[int, dict[int, int]] = {}  # frame → keypoint → track id
        for tid, t in enumerate(tracks):
            for frame, kp in t.items():
                self.by_frame.setdefault(frame, {})[kp] = tid

    @property
    def k(self) -> F64:
        return _intrinsics(self.f, self.w, self.h)

    def center(self, i: int) -> F64:
        r, _ = cv2.Rodrigues(self.rvecs[i])
        return np.asarray(-r.T @ self.tvecs[i].ravel(), dtype=np.float64)

    def projection(self, i: int) -> F64:
        r, _ = cv2.Rodrigues(self.rvecs[i])
        return np.asarray(self.k @ np.hstack([r, self.tvecs[i].reshape(3, 1)]), dtype=np.float64)

    def triangulate(self, s: SfmSettings) -> int:
        """Triangulate every track seen by ≥2 registered frames that has no point yet, from
        its widest-baseline pair, keeping points that are in front of every observing camera,
        reproject within `max_reproj_px` everywhere, and have enough triangulation angle."""
        centers = {f: self.center(f) for f in self.rvecs}
        projections = {f: self.projection(f) for f in self.rvecs}
        by_pair: dict[tuple[int, int], list[int]] = {}
        for tid, track in enumerate(self.tracks):
            if tid in self.xyz:
                continue
            regs = [f for f in track if f in centers]
            if len(regs) < 2:
                continue
            pair = max(
                ((a, b) for ai, a in enumerate(regs) for b in regs[ai + 1 :]),
                key=lambda p: float(np.linalg.norm(centers[p[0]] - centers[p[1]])),
            )
            by_pair.setdefault(pair, []).append(tid)
        cand: list[int] = []
        xs: list[F64] = []
        angles: list[F64] = []
        for (a, b), tids in by_pair.items():
            pa = np.array([self.frames[a].keypoints[self.tracks[t][a]] for t in tids]).T
            pb = np.array([self.frames[b].keypoints[self.tracks[t][b]] for t in tids]).T
            hom = cv2.triangulatePoints(projections[a], projections[b], pa, pb)
            ok = np.abs(hom[3]) > 1e-12
            x = (hom[:3, ok] / hom[3, ok]).T.astype(np.float64)
            cand.extend(t for t, keep in zip(tids, ok, strict=True) if keep)
            xs.append(x)
            angles.append(_angle_deg(centers[a].reshape(1, 3), centers[b].reshape(1, 3), x))
        if not cand:
            return 0
        x_all = np.vstack(xs)
        good = np.concatenate(angles) >= s.min_angle_deg
        pos = {t: n for n, t in enumerate(cand)}
        err, depth = self._per_point(x_all, pos)
        good &= (err <= s.max_reproj_px) & (depth > 0)
        for tid, n in pos.items():
            if good[n]:
                self.xyz[tid] = x_all[n]
        return int(good.sum())

    def _per_point(self, x: F64, pos: dict[int, int]) -> tuple[F64, F64]:
        """For points `x` (row `pos[track]`), the worst reprojection error and the smallest
        depth over every registered frame that observes the track. Batched per frame."""
        worst = np.zeros(len(x))
        nearest = np.full(len(x), np.inf)
        k = self.k
        for f in self.rvecs:
            rows, kps = [], []
            for kp, t in self.by_frame.get(f, {}).items():
                n = pos.get(t)
                if n is not None:
                    rows.append(n)
                    kps.append(kp)
            if not rows:
                continue
            ri = np.array(rows)
            r, _ = cv2.Rodrigues(self.rvecs[f])
            depth = (x[ri] @ r.T + self.tvecs[f])[:, 2]
            err = np.linalg.norm(
                _project(k, self.rvecs[f], self.tvecs[f], x[ri]) - self.frames[f].keypoints[kps],
                axis=1,
            )
            np.maximum.at(worst, ri, err)
            np.minimum.at(nearest, ri, depth)
        return worst, nearest

    def register(self, i: int, s: SfmSettings) -> bool:
        obs = [(kp, tid) for kp, tid in self.by_frame.get(i, {}).items() if tid in self.xyz]
        if len(obs) < s.min_pnp_inliers:
            return False
        obj = np.array([self.xyz[tid] for _, tid in obs], dtype=np.float64)
        img = np.array([self.frames[i].keypoints[kp] for kp, _ in obs], dtype=np.float64)
        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj,
            img,
            self.k,
            None,
            iterationsCount=2000,
            reprojectionError=s.max_reproj_px,
            confidence=0.999,
            flags=cv2.SOLVEPNP_EPNP,
        )
        if not ok or inliers is None or len(inliers) < s.min_pnp_inliers:
            return False
        idx = inliers.ravel()
        rvec, tvec = cv2.solvePnPRefineLM(obj[idx], img[idx], self.k, None, rvec, tvec)
        self.rvecs[i] = np.asarray(rvec, dtype=np.float64).reshape(3)
        self.tvecs[i] = np.asarray(tvec, dtype=np.float64).reshape(3)
        return True

    def errors(self) -> tuple[list[int], F64, npt.NDArray[np.int32]]:
        """Per triangulated track: mean reprojection error (px) and number of observers."""
        tids = sorted(self.xyz)
        pos = {t: n for n, t in enumerate(tids)}
        x = np.array([self.xyz[t] for t in tids]).reshape(-1, 3)
        total = np.zeros(len(tids))
        views = np.zeros(len(tids), dtype=np.int32)
        k = self.k
        for f in self.rvecs:
            pairs = [(pos[t], kp) for kp, t in self.by_frame.get(f, {}).items() if t in pos]
            if not pairs:
                continue
            ri = np.array([p[0] for p in pairs])
            kps = [p[1] for p in pairs]
            err = np.linalg.norm(
                _project(k, self.rvecs[f], self.tvecs[f], x[ri]) - self.frames[f].keypoints[kps],
                axis=1,
            )
            np.add.at(total, ri, err)
            np.add.at(views, ri, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            errs = np.where(views > 0, total / np.maximum(views, 1), np.inf)
        return tids, errs, views

    def prune(self, s: SfmSettings) -> int:
        tids, errs, _ = self.errors()
        removed = 0
        for tid, e in zip(tids, errs, strict=True):
            if not np.isfinite(e) or e > s.max_reproj_px:
                del self.xyz[tid]
                removed += 1
        return removed

    def bundle_adjust(self, fixed: int, max_nfev: int = 25) -> float:
        """Joint refinement of poses (except `fixed`), points and one shared focal length.
        Returns the RMS reprojection error in pixels after optimisation."""
        cams = sorted(self.rvecs)
        movable = [c for c in cams if c != fixed]
        cam_pos = {c: n for n, c in enumerate(movable)}
        tids = sorted(self.xyz)
        pt_pos = {t: n for n, t in enumerate(tids)}
        obs_cam, obs_pt, obs_xy = [], [], []
        for t in tids:
            for f, kp in self.tracks[t].items():
                if f in self.rvecs:
                    obs_cam.append(f)
                    obs_pt.append(pt_pos[t])
                    obs_xy.append(self.frames[f].keypoints[kp])
        if not obs_xy:
            return float("nan")
        obs_xy_a = np.array(obs_xy)
        obs_pt_a = np.array(obs_pt)
        obs_cam_a = np.array(obs_cam)
        n_cam, n_pt, n_obs = len(movable), len(tids), len(obs_xy)
        fixed_pose = np.concatenate([self.rvecs[fixed], self.tvecs[fixed]])
        per_cam = [(c, np.flatnonzero(obs_cam_a == c)) for c in cams]
        pt_col = 1 + 6 * n_cam

        def unpack(p: F64) -> tuple[float, F64, F64]:
            f = p[0]
            cams_p = p[1:pt_col].reshape(n_cam, 6)
            pts = p[pt_col:].reshape(n_pt, 3)
            return f, cams_p, pts

        def pose(c: int, cams_p: F64) -> F64:
            return cams_p[cam_pos[c]] if c in cam_pos else fixed_pose

        def residuals(p: F64) -> F64:
            f, cams_p, pts = unpack(p)
            k = _intrinsics(f, self.w, self.h)
            proj = np.empty((n_obs, 2))
            for c, idx in per_cam:
                pc = pose(c, cams_p)
                proj[idx] = _project(k, pc[:3], pc[3:], pts[obs_pt_a[idx]])
            return np.asarray((proj - obs_xy_a).ravel(), dtype=np.float64)

        # The Jacobian's sparsity pattern is fixed, so build (row, col) once in the same
        # order the values are produced below, and only refill values per iteration.
        cam_blocks = []
        for c, idx in per_cam:
            res_rows = np.stack([2 * idx, 2 * idx + 1], axis=1)
            col_sets = [np.zeros((len(idx), 1), dtype=np.int64)]
            if c in cam_pos:
                base = 1 + 6 * cam_pos[c]
                col_sets.append(np.tile(np.arange(base, base + 6), (len(idx), 1)))
            col_sets.append((pt_col + 3 * obs_pt_a[idx])[:, None] + np.arange(3))
            cols = np.concatenate(col_sets, axis=1)  # (n, 1 [+6] + 3)
            cam_blocks.append(
                (np.repeat(res_rows, cols.shape[1], axis=1).ravel(), np.tile(cols, 2).ravel())
            )
        jac_rows = np.concatenate([r for r, _ in cam_blocks])
        jac_cols = np.concatenate([c for _, c in cam_blocks])
        jac_shape = (2 * n_obs, 1 + 6 * n_cam + 3 * n_pt)

        def jacobian(p: F64) -> csr_matrix:
            # Analytic: OpenCV gives d(proj)/d(rvec, tvec, fx, fy); the point block is
            # d(proj)/d(Xc) · R by the chain rule.
            f, cams_p, pts = unpack(p)
            k = _intrinsics(f, self.w, self.h)
            vals = []
            for c, idx in per_cam:
                pc = pose(c, cams_p)
                x = pts[obs_pt_a[idx]]
                _, jac = cv2.projectPoints(x.reshape(-1, 1, 3), pc[:3], pc[3:], k, None)
                jac = jac.reshape(len(idx), 2, -1)
                r, _ = cv2.Rodrigues(pc[:3])
                xc = x @ r.T + pc[3:]
                z = np.where(np.abs(xc[:, 2]) < 1e-9, 1e-9, xc[:, 2])
                dxc = np.zeros((len(idx), 2, 3))
                dxc[:, 0, 0] = f / z
                dxc[:, 1, 1] = f / z
                dxc[:, 0, 2] = -f * xc[:, 0] / z**2
                dxc[:, 1, 2] = -f * xc[:, 1] / z**2
                parts: list[npt.NDArray[Any]] = [jac[:, :, 6:7] + jac[:, :, 7:8]]
                if c in cam_pos:
                    parts.append(jac[:, :, :6])
                parts.append(dxc @ r)
                vals.append(np.concatenate(parts, axis=2).ravel())  # (n, 2, k) row-major
            return csr_matrix((np.concatenate(vals), (jac_rows, jac_cols)), shape=jac_shape)

        x0 = np.concatenate(
            [
                [self.f],
                np.array([np.concatenate([self.rvecs[c], self.tvecs[c]]) for c in movable]).ravel()
                if movable
                else np.zeros(0),
                np.array([self.xyz[t] for t in tids]).ravel(),
            ]
        )
        result = least_squares(
            residuals,
            x0,
            jac=jacobian,
            loss="huber",
            f_scale=2.0,
            x_scale="jac",
            method="trf",
            tr_solver="lsmr",
            max_nfev=max_nfev,
        )
        focal, cams_p, pts = unpack(result.x)
        if 0.2 * self.w < focal < 5 * self.w:  # reject a degenerate focal collapse
            self.f = float(focal)
        for c, n in cam_pos.items():
            self.rvecs[c], self.tvecs[c] = cams_p[n, :3].copy(), cams_p[n, 3:].copy()
        for t, n in pt_pos.items():
            self.xyz[t] = pts[n].copy()
        res = residuals(result.x).reshape(-1, 2)
        return float(np.sqrt(np.mean(np.sum(res**2, axis=1))))


def _up_alignment(points: F64, centers: F64, seed: int = 0) -> tuple[F64, F64, float]:
    """Rotation and translation that put the dominant plane at y=0 with cameras above it.
    Returns (rotation, translation, inlier share). Falls back to identity without a plane."""
    if len(points) < 50:
        return np.eye(3), np.zeros(3), 0.0
    rng = np.random.default_rng(seed)
    spread = np.median(np.linalg.norm(points - np.median(points, axis=0), axis=1))
    tol = 0.05 * spread
    best_n, best_d, best_in = None, 0.0, 0
    for _ in range(300):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        n = np.cross(b - a, c - a)
        norm = np.linalg.norm(n)
        if norm < 1e-12:
            continue
        n /= norm
        d = -float(n @ a)
        inl = int(np.sum(np.abs(points @ n + d) < tol))
        if inl > best_in:
            best_n, best_d, best_in = n, d, inl
    share = best_in / len(points)
    if best_n is None or share < 0.2:
        return np.eye(3), np.zeros(3), share
    n = best_n
    if np.median(centers @ n + best_d) < 0:  # cameras must be on the +normal side (above)
        n, best_d = -n, -best_d
    up = np.array([0.0, 1.0, 0.0])
    v, c = np.cross(n, up), float(n @ up)
    if np.linalg.norm(v) < 1e-9:
        rot = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        rot = np.eye(3) + vx + vx @ vx * (1 / (1 + c))
    # After rotation the plane is y = -d; shift it to y = 0.
    return rot, np.array([0.0, best_d, 0.0]), share


@dataclass(frozen=True)
class FrameTransform:
    """The similarity `to_nazar_frame` applied: p_nazar = scale * rotation @ p_cv + offset.
    Kept so later stages (depth priors, splat cameras) can map more data into the same frame."""

    scale: float
    rotation: F64
    """Proper rotation from the OpenCV frame to NAZAR axes (axis flip + levelling)."""
    offset: F64

    def points(self, p_cv: F64) -> F64:
        return np.asarray(self.scale * p_cv @ self.rotation.T + self.offset)

    def directions(self, d_cv: F64) -> F64:
        """Directions (normals, camera axes) rotate but do not scale or shift."""
        return np.asarray(d_cv @ self.rotation.T)


def nazar_frame_transform(
    pts_cv: F64, centers_cv: F64, max_plane_samples: int = 20_000
) -> tuple[FrameTransform, float]:
    """The transform into NAZAR's local frame: +Y up (dominant plane levelled, cameras above
    it), centred on the median point, scaled so the median camera distance is 10 units.
    Returns (transform, plane inlier share)."""
    pts = pts_cv @ CV_TO_NAZAR.T
    centers = centers_cv @ CV_TO_NAZAR.T
    mid, k = np.zeros(3), 1.0
    if len(pts):
        mid = np.median(pts, axis=0)
        k = 10 / (float(np.median(np.linalg.norm(centers - mid, axis=1))) or 1.0)
    sample = (pts - mid) * k
    if len(sample) > max_plane_samples:
        pick = np.random.default_rng(0).choice(len(sample), max_plane_samples, replace=False)
        sample = sample[pick]
    rot, shift, plane_share = _up_alignment(sample, (centers - mid) * k)
    return FrameTransform(k, rot @ CV_TO_NAZAR, shift - k * rot @ mid), plane_share


def to_nazar_frame(
    pts_cv: F64, centers_cv: F64, max_plane_samples: int = 20_000
) -> tuple[F64, F64, float]:
    """OpenCV-camera-frame points and camera centres → NAZAR's local frame (see
    `nazar_frame_transform`). Returns (points, centres, plane inlier share). Shared by every
    geometry method so their outputs are directly comparable."""
    tf, plane_share = nazar_frame_transform(pts_cv, centers_cv, max_plane_samples)
    return tf.points(pts_cv), tf.points(centers_cv), plane_share


def reconstruct(
    images: Sequence[U8],
    settings: SfmSettings | None = None,
    check_cancel: Callable[[], None] = lambda: None,
) -> Iterator[Snapshot]:
    """Yield snapshots as the reconstruction grows; the last one has `final=True`.
    Raises `SfmFailed` with a user-facing reason when the keyframes cannot be reconstructed."""
    s = settings or SfmSettings()
    if len(images) < 3:
        raise SfmFailed(f"Need at least 3 keyframes for structure-from-motion; got {len(images)}.")
    h, w = images[0].shape[:2]
    frames = _features(images, s)
    check_cancel()
    k0 = _intrinsics(s.focal_guess * w, w, h)
    n = len(frames)
    matches: dict[tuple[int, int], npt.NDArray[np.int64]] = {}
    for i in range(n):
        for j in range(i + 1, min(n, i + 1 + s.match_window)):
            got = _match(frames[i], frames[j], k0, s)
            if got is not None:
                matches[(i, j)] = got
        check_cancel()
    if not matches:
        raise SfmFailed(
            "No pair of keyframes shares enough reliable features. The footage may be too "
            "blurry, too uniform (water, sky, snow) or change view too abruptly."
        )
    uf = _Tracks()
    for (i, j), m in matches.items():
        for a, b in m:
            uf.union((i, int(a)), (j, int(b)))
    tracks = uf.build()

    recon = _Recon(frames, tracks, s.focal_guess * w)
    init = _initial_pair(frames, matches, k0, s)
    if init is None:
        raise SfmFailed(
            "No keyframe pair has enough parallax to start the reconstruction. The camera "
            "may only rotate in place (no translation), which a single video cannot "
            "triangulate."
        )
    a, b, rvec, tvec = init
    recon.rvecs[a], recon.tvecs[a] = np.zeros(3), np.zeros(3)
    recon.rvecs[b], recon.tvecs[b] = rvec, tvec
    recon.triangulate(s)
    recon.bundle_adjust(fixed=a)
    recon.prune(s)
    yield _snapshot(recon, a, n, final=False)

    since_ba = 0
    failed: set[int] = set()
    while True:
        check_cancel()
        candidates = [
            i
            for i in range(n)
            if i not in recon.rvecs
            and i not in failed
            and any(abs(i - r) <= s.match_window for r in recon.rvecs)
        ]
        if not candidates:
            break
        # Register the keyframe that sees the most already-triangulated points.
        candidates.sort(
            key=lambda i: -sum(1 for t in recon.by_frame.get(i, {}).values() if t in recon.xyz)
        )
        i = candidates[0]
        if not recon.register(i, s):
            failed.add(i)
            continue
        failed.clear()  # new points may now let earlier failures register
        recon.triangulate(s)
        since_ba += 1
        if since_ba >= s.ba_every:
            recon.bundle_adjust(fixed=a)
            recon.prune(s)
            since_ba = 0
            yield _snapshot(recon, a, n, final=False)

    recon.bundle_adjust(fixed=a, max_nfev=50)
    recon.prune(s)
    recon.triangulate(s)
    rms = recon.bundle_adjust(fixed=a, max_nfev=30)
    recon.prune(s)
    final = _snapshot(recon, a, n, final=True)
    final.stats["ba_rms_px"] = round(rms, 3)
    yield final


def _initial_pair(
    frames: list[_Frame],
    matches: dict[tuple[int, int], npt.NDArray[np.int64]],
    k: F64,
    s: SfmSettings,
) -> tuple[int, int, F64, F64] | None:
    """The matched pair with the most inliers among those with real parallax (median
    triangulation angle ≥ 2°, and not explained by a homography, i.e. not pure rotation)."""
    best: tuple[float, tuple[int, int, F64, F64]] | None = None
    for (i, j), m in matches.items():
        pa, pb = frames[i].keypoints[m[:, 0]], frames[j].keypoints[m[:, 1]]
        hmat, hmask = cv2.findHomography(pa, pb, cv2.RANSAC, s.ransac_px * 2)
        if hmat is not None and hmask is not None and hmask.sum() > 0.85 * len(m):
            continue  # nearly all matches fit a homography: rotation-only or a flat far view
        e, _ = cv2.findEssentialMat(pa, pb, k, method=cv2.RANSAC, threshold=s.ransac_px)
        if e is None or e.shape != (3, 3):
            continue
        good, r, t, mask = cv2.recoverPose(e, pa, pb, k)
        if good < s.min_pair_inliers:
            continue
        p1 = k @ np.hstack([np.eye(3), np.zeros((3, 1))])
        p2 = k @ np.hstack([r, t])
        keep = mask.ravel() > 0
        hom = cv2.triangulatePoints(p1, p2, pa[keep].T, pb[keep].T)
        x = np.asarray((hom[:3] / hom[3]).T, dtype=np.float64)
        c2 = np.asarray(-r.T @ t, dtype=np.float64).ravel()
        angle = float(np.median(_angle_deg(np.zeros((1, 3)), c2.reshape(1, 3), x)))
        if angle < 2.0:
            continue
        score = good * min(angle, 8.0)
        if best is None or score > best[0]:
            rvec, _ = cv2.Rodrigues(r)
            pose = (
                i,
                j,
                np.asarray(rvec, np.float64).reshape(3),
                np.asarray(t, np.float64).reshape(3),
            )
            best = (score, pose)
    return best[1] if best else None


def _snapshot(recon: _Recon, anchor: int, total: int, *, final: bool) -> Snapshot:
    tids, errs, views = recon.errors()
    pts_cv = np.array([recon.xyz[t] for t in tids]).reshape(-1, 3)
    colors = np.array([_track_color(recon, t) for t in tids], dtype=np.uint8).reshape(-1, 3)
    registered = sorted(recon.rvecs)
    centers_cv = np.array([recon.center(i) for i in registered]).reshape(-1, 3)

    pts, centers, plane_share = to_nazar_frame(pts_cv, centers_cv)
    return Snapshot(
        points=pts,
        colors=colors,
        views=views,
        errors=errs,
        centers=centers,
        registered=registered,
        total_frames=total,
        focal_px=recon.f,
        final=final,
        stats={
            "anchor_keyframe": anchor,
            "registered": len(registered),
            "points": len(tids),
            "mean_reproj_px": round(float(np.mean(errs)), 3) if len(errs) else 0.0,
            "plane_inlier_share": round(plane_share, 3),
        },
    )


def _track_color(recon: _Recon, tid: int) -> U8:
    cols = [recon.frames[f].colors[kp] for f, kp in recon.tracks[tid].items() if f in recon.rvecs]
    return np.asarray(np.median(np.array(cols), axis=0), dtype=np.uint8)
