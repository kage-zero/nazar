"""Minimal binary PLY writer/reader for coloured point clouds (x, y, z float32; RGB uint8)."""

import struct
from collections.abc import Sequence

Point = tuple[float, float, float, int, int, int]

_RECORD = struct.Struct("<fffBBB")


def write_ply(points: Sequence[Point], comments: Sequence[str] = ()) -> bytes:
    header = ["ply", "format binary_little_endian 1.0"]
    header += [f"comment {c}" for c in comments]
    header += [
        f"element vertex {len(points)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
    ]
    body = b"".join(_RECORD.pack(*p) for p in points)
    return ("\n".join(header) + "\n").encode("ascii") + body


def read_ply(data: bytes) -> list[Point]:
    """Inverse of `write_ply`, for tests and validation of our own outputs."""
    end = data.index(b"end_header\n") + len(b"end_header\n")
    lines = data[:end].decode("ascii").splitlines()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise ValueError("not a binary little-endian PLY")
    count = next(int(line.split()[2]) for line in lines if line.startswith("element vertex"))
    body = data[end:]
    if len(body) != count * _RECORD.size:
        raise ValueError("PLY body size does not match the vertex count")
    return [_RECORD.unpack_from(body, i * _RECORD.size) for i in range(count)]


def bounds(points: Sequence[Point]) -> tuple[list[float], list[float]]:
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi
