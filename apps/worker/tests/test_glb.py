import json
import struct

import numpy as np
import pytest

from nazar_worker.glb import BIN_CHUNK, JSON_CHUNK, LINE_STRIP, POINTS, read_glb, write_glb


def test_glb_layout_follows_the_spec() -> None:
    xyz = np.array([[0, 0, 0], [1, 2, 3], [-1, 0.5, 2]], dtype=np.float64)
    rgb = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)
    data = write_glb(xyz, rgb, np.array([[0, 5, 0], [1, 5, 0]]), extras={"units": "unitless"})
    magic, version, total = struct.unpack_from("<III", data, 0)
    assert (magic, version, total) == (0x46546C67, 2, len(data))
    js_len, js_type = struct.unpack_from("<II", data, 12)
    assert js_type == JSON_CHUNK and js_len % 4 == 0
    bin_len, bin_type = struct.unpack_from("<II", data, 20 + js_len)
    assert bin_type == BIN_CHUNK and bin_len % 4 == 0
    doc = json.loads(data[20 : 20 + js_len])
    assert doc["asset"]["version"] == "2.0"
    assert doc["asset"]["extras"] == {"units": "unitless"}
    # POSITION accessors must carry min/max (glTF 2.0 3.6.2.4).
    assert doc["accessors"][0]["min"] == [-1, 0, 0] and doc["accessors"][0]["max"] == [1, 2, 3]
    assert doc["meshes"][0]["primitives"][0]["mode"] == POINTS
    assert doc["meshes"][1]["primitives"][0]["mode"] == LINE_STRIP
    # Every buffer view starts 4-byte aligned.
    assert all(v["byteOffset"] % 4 == 0 for v in doc["bufferViews"])


def test_glb_round_trip() -> None:
    rng = np.random.default_rng(0)
    xyz = rng.normal(size=(101, 3))
    rgb = rng.integers(0, 256, size=(101, 3)).astype(np.uint8)
    scene = read_glb(write_glb(xyz, rgb))
    assert np.allclose(scene.points, xyz, atol=1e-6)
    assert (scene.colors == rgb).all()
    assert scene.path is None
    assert len(scene.doc["nodes"]) == 1


def test_glb_rejects_empty_or_non_finite() -> None:
    with pytest.raises(ValueError):
        write_glb(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        write_glb(np.array([[np.nan, 0, 0]]), np.zeros((1, 3), dtype=np.uint8))
