"""Fusion of Fast3R pointmaps with Metric3D priors, on a synthetic scene with known geometry.

A flat ground plane is seen by two cameras looking straight down. "Fast3R" pointmaps are the
exact plane points (in units where 1 unit = 2 m), "Metric3D" depth is the exact metric depth,
and normals point at the camera. Fusion must recover the scale, attach the normals, fill
low-confidence pixels from the prior, and never use moving-object pixels.
"""

from pathlib import Path

import numpy as np

from nazar_worker.fusion import SOURCE_DEPTH, SOURCE_FAST3R, Priors, fuse, view_scales
from nazar_worker.glb import read_mesh_glb, write_mesh_glb
from nazar_worker.ply import read_confidence, read_source, write_ply_arrays
from nazar_worker.sfm import FrameTransform, nazar_frame_transform, to_nazar_frame

UNITS_PER_METRE = 0.5  # Fast3R units are 2 m each
H_IN, W_IN, ST, F_IN = 64, 96, 2, 80.0
FACTOR = 0.5  # model input is half the keyframe resolution


def _scene(tmp: Path) -> tuple[Path, Priors]:
    """Two downward cameras 10 m above a plane; pointmaps on a stride-2 grid."""
    h, w = H_IN // ST, W_IN // ST
    views, pts, conf, rgb, c2w, dyn = [], [], [], [], [], []
    depth: dict[int, np.ndarray] = {}
    normals: dict[int, np.ndarray] = {}
    for v, cx_m in enumerate([0.0, 2.0]):
        pose = np.eye(4)
        pose[:3, 3] = [cx_m * UNITS_PER_METRE, 0, 0]  # camera axes = world axes, +Z down
        cols, rows = np.meshgrid(np.arange(w) * ST, np.arange(h) * ST)
        z_m = 10.0
        x = (cols - W_IN / 2) / F_IN * z_m
        y = (rows - H_IN / 2) / F_IN * z_m
        cam = np.stack([x, y, np.full_like(x, z_m)], -1) * UNITS_PER_METRE
        pts.append(cam + pose[:3, 3])
        c = np.full((h, w), 20.0, np.float32)
        c[:, : w // 4] = 1.5  # Fast3R unsure on the left quarter: the prior should fill it
        conf.append(c)
        rgb.append(np.full((h, w, 3), 100 + 50 * v, np.uint8))
        c2w.append(pose)
        d = np.zeros((h, w), bool)
        d[h // 2 :, w // 2 : w // 2 + 2] = True  # a "moving car"
        dyn.append(d)
        views.append(v)
        full_h, full_w = int(H_IN / FACTOR), int(W_IN / FACTOR)
        depth[v] = np.full((full_h, full_w), z_m, np.float32)
        n = np.zeros((full_h, full_w, 3), np.float32)
        n[..., 2] = -1.0  # facing the camera (OpenCV +Z forward)
        normals[v] = n
    path = tmp / "result.npz"
    np.savez(
        path,
        pts=np.stack(pts).astype(np.float32),
        conf=np.stack(conf),
        rgb=np.stack(rgb),
        c2w=np.stack(c2w),
        focal=np.array([F_IN, F_IN]),
        views=np.array(views),
        input_size=np.array([W_IN, H_IN]),
        dyn=np.stack(dyn),
        stride=np.array(ST),
        crop=np.array([[FACTOR, 0.0, 0.0]] * 2),
    )
    return path, Priors(depth, normals, "vit_small")


def test_view_scales_recover_units_per_metre(tmp_path: Path) -> None:
    path, priors = _scene(tmp_path)
    data = np.load(path)
    keep = (data["conf"] >= 3) & ~data["dyn"]
    scales = view_scales(data, keep, priors)["views"]
    assert len(scales) == 2
    for s in scales.values():
        assert abs(s["units_per_metre"] - UNITS_PER_METRE) < 1e-6
        assert s["median_rel_err"] < 1e-6


def test_fuse_attaches_normals_fills_holes_and_skips_moving_pixels(tmp_path: Path) -> None:
    path, priors = _scene(tmp_path)
    tf = FrameTransform(1.0, np.eye(3), np.zeros(3))
    fused = fuse(path, tf, keep_thr=3.0, priors=priors, max_points=10_000_000)
    data = np.load(path)
    kept = int(((data["conf"] >= 3) & ~data["dyn"]).sum())
    assert (fused.source == SOURCE_FAST3R).sum() == kept
    filled = int((fused.source == SOURCE_DEPTH).sum())
    holes = int(((data["conf"] < 3) & ~data["dyn"]).sum())
    assert filled == holes  # every low-confidence pixel lies inside the observed depth range
    assert fused.stats["moving_object_pixels_excluded"] == int(data["dyn"].sum())
    # Filled points lie on the same plane as Fast3R's (z = 10 m = 5 units).
    assert np.allclose(fused.points[:, 2], 10 * UNITS_PER_METRE, atol=1e-6)
    # Normals come from the prior and face the cameras.
    assert np.allclose(fused.normals, [0, 0, -1])
    assert abs(fused.stats["metres_per_unit_estimated"] - 1 / UNITS_PER_METRE) < 1e-6
    assert fused.stats["scale_spread_rel"] < 1e-6


def test_fuse_without_priors_keeps_only_fast3r(tmp_path: Path) -> None:
    path, _ = _scene(tmp_path)
    tf = FrameTransform(1.0, np.eye(3), np.zeros(3))
    fused = fuse(path, tf, keep_thr=3.0, priors=None, max_points=10_000_000)
    assert (fused.source == SOURCE_FAST3R).all()
    assert not np.linalg.norm(fused.normals, axis=1).any()
    assert "metres_per_unit_estimated" not in fused.stats


def test_voxel_reduction_respects_the_point_budget(tmp_path: Path) -> None:
    path, priors = _scene(tmp_path)
    tf = FrameTransform(1.0, np.eye(3), np.zeros(3))
    fused = fuse(path, tf, keep_thr=3.0, priors=priors, max_points=100)
    assert 0 < len(fused.points) <= 100
    assert np.allclose(np.linalg.norm(fused.normals, axis=1), 1.0)


def test_frame_transform_matches_to_nazar_frame() -> None:
    rng = np.random.default_rng(1)
    pts = rng.normal(size=(500, 3)) + np.array([0.0, 0.0, 5.0])
    pts[:, 1] = 5.0 + rng.normal(scale=0.01, size=500)  # a plane below the cameras (y down)
    centres = rng.normal(size=(6, 3)) * 0.2
    tf, _ = nazar_frame_transform(pts, centres)
    a, b, _ = to_nazar_frame(pts, centres)
    assert np.allclose(tf.points(pts), a) and np.allclose(tf.points(centres), b)
    assert np.allclose(tf.rotation @ tf.rotation.T, np.eye(3))
    assert np.linalg.det(tf.rotation) > 0


def test_mesh_glb_round_trip() -> None:
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], np.float32)
    faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], np.int32)
    cols = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255], [9, 9, 9]], np.uint8)
    data = write_mesh_glb(verts, faces, cols, verts, extras={"units": "unitless"})
    assert data[:4] == b"glTF" and len(data) % 4 == 0
    mesh = read_mesh_glb(data)
    assert (mesh.vertices == verts).all()
    assert (mesh.faces == faces).all()
    assert (mesh.colors == cols).all()
    prim = mesh.doc["meshes"][0]["primitives"][0]
    assert prim["mode"] == 4 and set(prim["attributes"]) == {"POSITION", "COLOR_0", "NORMAL"}


def test_ply_carries_source_with_confidence() -> None:
    xyz = np.zeros((3, 3))
    rgb = np.zeros((3, 3), np.uint8)
    conf = np.array([1, 2, 2], np.uint8)
    src = np.array([0, 1, 0], np.uint8)
    data = write_ply_arrays(xyz, rgb, (), conf, src)
    got_conf, got_src = read_confidence(data), read_source(data)
    assert got_conf is not None and np.array_equal(got_conf, conf)
    assert got_src is not None and np.array_equal(got_src, src)
    assert read_source(write_ply_arrays(xyz, rgb, (), conf)) is None
