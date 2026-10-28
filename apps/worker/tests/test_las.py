"""LAS export: header layout from the LAS 1.2 specification, round trip, axis conversion."""

import struct

import numpy as np
import pytest

from nazar_worker.las import HEADER_SIZE, read_las, to_las_axes, write_las


def cloud(n: int = 200) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(3)
    xyz = rng.normal(scale=7.0, size=(n, 3)) + np.array([100.0, -3.0, 40.0])
    rgb = rng.integers(0, 256, size=(n, 3), dtype=np.uint8)
    conf = rng.integers(1, 3, size=n, dtype=np.uint8)
    return xyz, rgb, conf


def test_header_fields_sit_at_the_specified_offsets() -> None:
    xyz, rgb, conf = cloud()
    data = write_las(xyz, rgb, conf)
    assert data[:4] == b"LASF"
    assert data[24:26] == bytes([1, 2])  # version 1.2
    assert struct.unpack_from("<H", data, 94)[0] == HEADER_SIZE
    assert struct.unpack_from("<I", data, 96)[0] == HEADER_SIZE  # offset to points, no VLRs
    assert struct.unpack_from("<I", data, 100)[0] == 0  # VLR count: no CRS
    assert data[104] == 2  # point data format
    assert struct.unpack_from("<H", data, 105)[0] == 26  # record length
    assert struct.unpack_from("<I", data, 107)[0] == len(xyz)
    assert len(data) == HEADER_SIZE + 26 * len(xyz)


def test_round_trip_keeps_points_colours_and_confidence() -> None:
    xyz, rgb, conf = cloud()
    las = read_las(write_las(xyz, rgb, conf))
    expected = to_las_axes(xyz)
    assert np.abs(las.xyz - expected).max() < 1e-5
    assert (las.rgb16 == rgb.astype(np.uint16) * 257).all()
    assert (las.user_data == conf).all()
    assert las.system_id == "NAZAR local frame, no CRS"
    assert np.allclose(las.bounds_min, expected.min(axis=0))
    assert np.allclose(las.bounds_max, expected.max(axis=0))


def test_up_axis_becomes_las_z_with_a_proper_rotation() -> None:
    up = to_las_axes(np.array([[0.0, 1.0, 0.0]]))
    assert up.tolist() == [[0.0, 0.0, 1.0]]
    m = to_las_axes(np.eye(3))
    assert np.isclose(np.linalg.det(m), 1.0)


def test_rejects_empty_or_non_finite_clouds() -> None:
    _, rgb, _ = cloud(1)
    with pytest.raises(ValueError):
        write_las(np.zeros((0, 3)), rgb[:0])
    with pytest.raises(ValueError):
        write_las(np.array([[np.nan, 0.0, 0.0]]), rgb)


def test_geokeys_vlr_declares_the_projected_crs() -> None:
    xyz = np.array([[291945.99, 4640626.6, 30.0], [292000.0, 4640700.0, 45.5]])
    rgb = np.array([[10, 20, 30], [40, 50, 60]], dtype=np.uint8)
    data = write_las(xyz, rgb, enu=True, epsg=32633)
    las = read_las(data)
    assert las.epsg == 32633
    assert np.abs(las.xyz - xyz).max() < 1e-3
    # Header: one VLR, points start after it (54-byte VLR header + 4 + 5 keys x 4 shorts).
    offset_to_points, n_vlr = struct.unpack_from("<IH", data, 96)
    assert n_vlr == 1 and offset_to_points == 227 + 54 + 2 * (4 + 20)
    assert data[229:244] == b"LASF_Projection"
    assert read_las(write_las(xyz, rgb, enu=True)).epsg is None
