"""Minimal glTF 2.0 binary (GLB) writer/reader for the final point cloud and camera path.

Written with numpy from the Khronos glTF 2.0 specification, so the worker needs no extra
dependency. The file holds one scene with two nodes:

- `point_cloud`: a POINTS primitive with POSITION (float32) and COLOR_0 (normalised uint8 RGBA,
  sRGB as stored by the PLY);
- `camera_path`: a LINE_STRIP through the camera centres (omitted with fewer than two).

glTF is right-handed with +Y up, the same axes as NAZAR's local frame, so coordinates are
written unchanged. glTF viewers assume metres: when the scale is unknown the file says so in
`asset.extras`, and coordinates are unitless.
"""

import json
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

MAGIC = 0x46546C67  # "glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
POINTS, LINE_STRIP = 0, 3
FLOAT, UNSIGNED_BYTE = 5126, 5121
ARRAY_BUFFER = 34962


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * (-len(data) % 4)


def write_glb(
    xyz: npt.NDArray[np.float64],
    rgb: npt.NDArray[np.uint8],
    path: npt.NDArray[np.float64] | None = None,
    *,
    extras: dict[str, Any] | None = None,
) -> bytes:
    pts = np.ascontiguousarray(xyz, dtype=np.float32)
    if len(pts) == 0 or not np.isfinite(pts).all():
        raise ValueError("GLB export needs at least one point and finite coordinates.")
    rgba = np.empty((len(pts), 4), dtype=np.uint8)
    rgba[:, :3] = rgb
    rgba[:, 3] = 255
    blobs: list[bytes] = [pts.tobytes(), rgba.tobytes()]
    accessors: list[dict[str, Any]] = [
        {
            "bufferView": 0,
            "componentType": FLOAT,
            "count": len(pts),
            "type": "VEC3",
            "min": pts.min(axis=0).tolist(),
            "max": pts.max(axis=0).tolist(),
        },
        {
            "bufferView": 1,
            "componentType": UNSIGNED_BYTE,
            "normalized": True,
            "count": len(pts),
            "type": "VEC4",
        },
    ]
    meshes: list[dict[str, Any]] = [
        {
            "name": "point_cloud",
            "primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 1}, "mode": POINTS}],
        }
    ]
    nodes: list[dict[str, Any]] = [{"name": "point_cloud", "mesh": 0}]
    if path is not None and len(path) >= 2:
        line = np.ascontiguousarray(path, dtype=np.float32)
        blobs.append(line.tobytes())
        accessors.append(
            {
                "bufferView": 2,
                "componentType": FLOAT,
                "count": len(line),
                "type": "VEC3",
                "min": line.min(axis=0).tolist(),
                "max": line.max(axis=0).tolist(),
            }
        )
        meshes.append(
            {
                "name": "camera_path",
                "primitives": [{"attributes": {"POSITION": 2}, "mode": LINE_STRIP}],
            }
        )
        nodes.append({"name": "camera_path", "mesh": 1})

    views, offset, body = [], 0, b""
    for blob in blobs:
        views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(blob), "target": ARRAY_BUFFER}
        )
        padded = _pad(blob, b"\0")
        body += padded
        offset += len(padded)
    doc = {
        "asset": {"version": "2.0", "generator": "NAZAR worker", "extras": extras or {}},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(body)}],
    }
    js = _pad(json.dumps(doc, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(js) + 8 + len(body)
    return b"".join(
        [
            struct.pack("<III", MAGIC, 2, total),
            struct.pack("<II", len(js), JSON_CHUNK),
            js,
            struct.pack("<II", len(body), BIN_CHUNK),
            body,
        ]
    )


TRIANGLES = 4
UNSIGNED_INT = 5125
ELEMENT_ARRAY_BUFFER = 34963


def write_mesh_glb(
    vertices: npt.NDArray[np.floating[Any]],
    faces: npt.NDArray[np.integer[Any]],
    colors: npt.NDArray[np.uint8],
    normals: npt.NDArray[np.floating[Any]] | None = None,
    *,
    extras: dict[str, Any] | None = None,
) -> bytes:
    """One TRIANGLES mesh with POSITION, NORMAL (optional) and COLOR_0 (normalised uint8
    RGBA), indexed by uint32. Same axes and unit conventions as `write_glb`."""
    pos = np.ascontiguousarray(vertices, dtype=np.float32)
    idx = np.ascontiguousarray(faces, dtype=np.uint32).reshape(-1)
    if len(pos) == 0 or len(idx) == 0 or not np.isfinite(pos).all():
        raise ValueError("Mesh GLB export needs vertices, faces and finite coordinates.")
    if idx.max() >= len(pos):
        raise ValueError("Face index out of range.")
    rgba = np.empty((len(pos), 4), dtype=np.uint8)
    rgba[:, :3] = colors
    rgba[:, 3] = 255
    blobs: list[tuple[bytes, int]] = [
        (idx.tobytes(), ELEMENT_ARRAY_BUFFER),
        (pos.tobytes(), ARRAY_BUFFER),
        (rgba.tobytes(), ARRAY_BUFFER),
    ]
    accessors: list[dict[str, Any]] = [
        {"bufferView": 0, "componentType": UNSIGNED_INT, "count": len(idx), "type": "SCALAR"},
        {
            "bufferView": 1,
            "componentType": FLOAT,
            "count": len(pos),
            "type": "VEC3",
            "min": pos.min(axis=0).tolist(),
            "max": pos.max(axis=0).tolist(),
        },
        {
            "bufferView": 2,
            "componentType": UNSIGNED_BYTE,
            "normalized": True,
            "count": len(pos),
            "type": "VEC4",
        },
    ]
    attributes = {"POSITION": 1, "COLOR_0": 2}
    if normals is not None:
        nrm = np.ascontiguousarray(normals, dtype=np.float32)
        blobs.append((nrm.tobytes(), ARRAY_BUFFER))
        accessors.append(
            {"bufferView": 3, "componentType": FLOAT, "count": len(nrm), "type": "VEC3"}
        )
        attributes["NORMAL"] = 3
    views, offset, body = [], 0, b""
    for blob, target in blobs:
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob), "target": target})
        padded = _pad(blob, b"\0")
        body += padded
        offset += len(padded)
    doc = {
        "asset": {"version": "2.0", "generator": "NAZAR worker", "extras": extras or {}},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "surface", "mesh": 0}],
        "meshes": [
            {
                "name": "surface",
                "primitives": [{"attributes": attributes, "indices": 0, "mode": TRIANGLES}],
            }
        ],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(body)}],
    }
    js = _pad(json.dumps(doc, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(js) + 8 + len(body)
    return b"".join(
        [
            struct.pack("<III", MAGIC, 2, total),
            struct.pack("<II", len(js), JSON_CHUNK),
            js,
            struct.pack("<II", len(body), BIN_CHUNK),
            body,
        ]
    )


@dataclass
class GlbMesh:
    doc: dict[str, Any]
    vertices: npt.NDArray[np.float32]
    faces: npt.NDArray[np.uint32]
    colors: npt.NDArray[np.uint8]


def read_mesh_glb(data: bytes) -> GlbMesh:
    """Reads files written by `write_mesh_glb` (tests and checks only)."""
    js_len = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20 : 20 + js_len])
    body = data[28 + js_len :]

    def view(i: int, dtype: type[np.generic], width: int) -> npt.NDArray[Any]:
        acc = doc["accessors"][i]
        bv = doc["bufferViews"][acc["bufferView"]]
        raw = body[bv["byteOffset"] : bv["byteOffset"] + bv["byteLength"]]
        return np.frombuffer(raw, dtype=dtype).reshape(acc["count"], width)

    return GlbMesh(
        doc,
        view(1, np.float32, 3),
        view(0, np.uint32, 1).reshape(-1, 3),
        view(2, np.uint8, 4)[:, :3],
    )


@dataclass
class GlbScene:
    doc: dict[str, Any]
    points: npt.NDArray[np.float32]
    colors: npt.NDArray[np.uint8]
    path: npt.NDArray[np.float32] | None


def read_glb(data: bytes) -> GlbScene:
    """Reads files written by `write_glb` (used by tests and checks, not a general loader)."""
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != MAGIC or version != 2 or total != len(data):
        raise ValueError("Not a glTF 2.0 binary.")
    js_len, js_type = struct.unpack_from("<II", data, 12)
    if js_type != JSON_CHUNK:
        raise ValueError("First chunk is not JSON.")
    doc = json.loads(data[20 : 20 + js_len])
    bin_len, bin_type = struct.unpack_from("<II", data, 20 + js_len)
    if bin_type != BIN_CHUNK:
        raise ValueError("Second chunk is not BIN.")
    body = data[28 + js_len : 28 + js_len + bin_len]

    def accessor(i: int, dtype: type[np.generic], width: int) -> npt.NDArray[Any]:
        acc = doc["accessors"][i]
        view = doc["bufferViews"][acc["bufferView"]]
        raw = body[view["byteOffset"] : view["byteOffset"] + view["byteLength"]]
        return np.frombuffer(raw, dtype=dtype).reshape(acc["count"], width)

    pts = accessor(0, np.float32, 3)
    cols = accessor(1, np.uint8, 4)[:, :3]
    path = accessor(2, np.float32, 3) if len(doc["accessors"]) > 2 else None
    return GlbScene(doc, pts, cols, path)
