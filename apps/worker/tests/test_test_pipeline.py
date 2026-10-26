import hashlib

from nazar_worker.ply import bounds, read_ply, write_ply
from nazar_worker.test_pipeline import FIXTURE_NOTE, synthetic_scene


def test_ply_round_trip_preserves_points() -> None:
    pts = [(0.0, 1.5, -2.25, 10, 20, 30), (3.0, -1.0, 0.5, 255, 0, 128)]
    data = write_ply(pts, ["hello"])
    assert data.startswith(b"ply\nformat binary_little_endian 1.0\ncomment hello\n")
    assert read_ply(data) == pts


def test_synthetic_scene_is_deterministic_and_finite() -> None:
    a, b = synthetic_scene(), synthetic_scene()
    assert a == b
    assert 15_000 < len(a) < 40_000
    lo, hi = bounds(a)
    assert all(-7 < v < 7 for v in lo + hi)
    assert hi[1] > 2  # the pyramid rises above the ground plane


def test_fixture_ply_is_labelled_as_synthetic() -> None:
    data = write_ply(synthetic_scene()[:10], [FIXTURE_NOTE])
    assert b"not a reconstruction" in data.split(b"end_header")[0]
    assert len(hashlib.sha256(data).hexdigest()) == 64
