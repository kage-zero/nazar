"""Tests for the classical SfM baseline: the maths on synthetic ground truth, and the whole
reconstruction on the real sample video (keyframes extracted by the real preflight)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from nazar_worker.ply import read_confidence, read_ply, write_ply, write_ply_arrays
from nazar_worker.sfm import (
    SfmFailed,
    SfmSettings,
    _Frame,
    _intrinsics,
    _Recon,
    _up_alignment,
    reconstruct,
)

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "sample" / "video" / "sample1.mp4"


def test_array_ply_matches_tuple_ply() -> None:
    rng = np.random.default_rng(1)
    xyz = rng.normal(size=(50, 3))
    rgb = rng.integers(0, 255, size=(50, 3), dtype=np.uint8)
    tuples = [(*map(float, p), *map(int, c)) for p, c in zip(xyz, rgb, strict=True)]
    assert write_ply_arrays(xyz, rgb, ["x"]) == write_ply(tuples, ["x"])  # type: ignore[arg-type]
    assert len(read_ply(write_ply_arrays(xyz, rgb))) == 50
    assert read_confidence(write_ply_arrays(xyz, rgb)) is None


def test_ply_carries_optional_confidence_classes() -> None:
    xyz = np.arange(12, dtype=np.float64).reshape(4, 3)
    rgb = np.full((4, 3), 7, dtype=np.uint8)
    labels = np.array([1, 2, 2, 1], dtype=np.uint8)
    data = write_ply_arrays(xyz, rgb, confidence=labels)
    assert b"property uchar confidence" in data
    assert read_confidence(data).tolist() == [1, 2, 2, 1]  # type: ignore[union-attr]
    assert read_ply(data) == read_ply(write_ply_arrays(xyz, rgb))


def _synthetic_recon(
    focal: float = 500.0, noise_px: float = 0.0
) -> tuple[_Recon, dict[str, object]]:
    """Six cameras on an arc looking at a random cloud, with exact (or noisy) observations."""
    rng = np.random.default_rng(3)
    w, h = 640, 480
    k = _intrinsics(focal, w, h)
    pts = rng.uniform(-2, 2, size=(300, 3)) + np.array([0.0, 0.0, 10.0])
    rvecs, tvecs, frames = [], [], []
    for i in range(6):
        angle = np.radians(-10 + 4 * i)
        r = cv2.Rodrigues(np.array([0.0, angle, 0.0]))[0]
        center = np.array([10 * np.sin(angle), 0.3 * i, 10 - 10 * np.cos(angle)])
        rvec = cv2.Rodrigues(r)[0].ravel()
        tvec = -r @ center
        proj, _ = cv2.projectPoints(pts.reshape(-1, 1, 3), rvec, tvec, k, None)
        kps = proj.reshape(-1, 2) + rng.normal(scale=noise_px, size=(len(pts), 2))
        frames.append(
            _Frame(
                np.zeros((h, w, 3), np.uint8),
                kps,
                np.zeros((len(pts), 128), np.float32),
                np.zeros((len(pts), 3), np.uint8),
            )
        )
        rvecs.append(rvec)
        tvecs.append(tvec)
    tracks = [dict.fromkeys(range(6), j) for j in range(len(pts))]
    recon = _Recon(frames, tracks, focal)
    for i in range(6):
        recon.rvecs[i] = np.array(rvecs[i], dtype=np.float64)
        recon.tvecs[i] = np.array(tvecs[i], dtype=np.float64)
    for j, p in enumerate(pts):
        recon.xyz[j] = p.copy()
    return recon, {"pts": pts, "rvecs": rvecs, "tvecs": tvecs}


def test_bundle_adjustment_recovers_perturbed_scene_and_focal() -> None:
    recon, _ = _synthetic_recon(focal=500.0, noise_px=0.3)
    rng = np.random.default_rng(4)
    recon.f = 460.0  # 8 % focal error, as from an uncalibrated guess
    for i in range(1, 6):
        recon.rvecs[i] = recon.rvecs[i] + rng.normal(scale=0.01, size=3)
        recon.tvecs[i] = recon.tvecs[i] + rng.normal(scale=0.1, size=3)
    for j in recon.xyz:
        recon.xyz[j] = recon.xyz[j] + rng.normal(scale=0.05, size=3)
    _, before, _ = recon.errors()
    rms = recon.bundle_adjust(fixed=0, max_nfev=100)
    _, after, _ = recon.errors()
    assert before.mean() > 5
    assert after.mean() < 0.6  # back to the injected 0.3 px noise level
    assert rms < 0.6
    assert abs(recon.f - 500.0) < 10


def test_triangulation_rejects_points_without_parallax() -> None:
    recon, _ = _synthetic_recon()
    recon.xyz.clear()
    # Two cameras at the same place: every angle is ~0°, so nothing may be triangulated.
    recon.rvecs = {0: recon.rvecs[0], 1: recon.rvecs[0].copy()}
    recon.tvecs = {0: recon.tvecs[0], 1: recon.tvecs[0].copy()}
    assert recon.triangulate(SfmSettings()) == 0
    # With the real, separated cameras the exact observations triangulate.
    recon2, _ = _synthetic_recon()
    recon2.xyz.clear()
    assert recon2.triangulate(SfmSettings()) == 300


def test_up_alignment_puts_dominant_plane_level_below_cameras() -> None:
    rng = np.random.default_rng(5)
    ground = np.column_stack([rng.uniform(-5, 5, 800), np.zeros(800), rng.uniform(-5, 5, 800)])
    clutter = rng.uniform(-5, 5, size=(200, 3))
    tilt = cv2.Rodrigues(np.array([0.4, 0.1, -0.3]))[0]
    pts = np.vstack([ground, clutter]) @ tilt.T + [1, 2, 3]
    cams = np.array([[0.0, 6.0, 0.0], [2.0, 6.0, 1.0]]) @ tilt.T + [1, 2, 3]
    rot, shift, share = _up_alignment(pts, cams)
    level = pts[:800] @ rot.T + shift
    assert share > 0.7
    assert np.abs(level[:, 1]).max() < 0.3
    assert ((cams @ rot.T + shift)[:, 1] > 5).all()


def test_too_few_keyframes_is_a_user_facing_failure() -> None:
    with pytest.raises(SfmFailed, match="at least 3 keyframes"):
        list(reconstruct([np.zeros((10, 10, 3), np.uint8)] * 2))


@pytest.mark.skipif(not SAMPLE.is_file(), reason="sample video not present")
def test_real_sample_reconstructs_progressively(tmp_path: Path) -> None:
    """Real data: the supplied drone clip through the real preflight, then the baseline."""
    from nazar_media import run_preflight

    report = run_preflight(
        SAMPLE, tmp_path, asset_id="t", source_sha256="0" * 64, max_duration_s=600
    )
    images = []
    for k in report.keyframes:
        image = cv2.imread(str(tmp_path / "keyframes" / f"{k.image:04d}.jpg"))
        assert image is not None
        images.append(image.astype(np.uint8))
    snapshots = list(reconstruct(images))
    previews, final = snapshots[:-1], snapshots[-1]
    assert previews and not any(s.final for s in previews) and final.final
    # Previews grow monotonically in registered keyframes: progressive, not all at once.
    counts = [len(s.registered) for s in snapshots]
    assert counts == sorted(counts) and counts[0] < counts[-1]
    assert len(final.registered) >= 0.8 * len(images)
    assert len(final.points) >= 3000
    assert float(final.errors.mean()) < 1.5
    assert np.isfinite(final.points).all()
    # Up alignment: the cameras fly above the dominant (ground) plane.
    assert np.median(final.centers[:, 1]) > np.percentile(final.points[:, 1], 75)
