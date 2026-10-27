"""Minimal binary PLY writer/reader for coloured point clouds (x, y, z float32; RGB uint8).

Final clouds may carry one extra `uchar confidence` per point: 1 = observed, 2 = estimated,
3 = inferred (the labels the job report counts). Generic PLY readers ignore the property."""

import struct
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

Point = tuple[float, float, float, int, int, int]

_RECORD = struct.Struct("<fffBBB")
_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
_DTYPE_CONF = np.dtype([*_DTYPE.descr, ("c", "u1")])

OBSERVED, ESTIMATED, INFERRED = 1, 2, 3


def _header(count: int, comments: Sequence[str], confidence: bool = False) -> bytes:
    header = ["ply", "format binary_little_endian 1.0"]
    header += [f"comment {c}" for c in comments]
    header += [
        f"element vertex {count}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        *(["property uchar confidence"] if confidence else []),
        "end_header",
    ]
    return ("\n".join(header) + "\n").encode("ascii")


def write_ply(points: Sequence[Point], comments: Sequence[str] = ()) -> bytes:
    return _header(len(points), comments) + b"".join(_RECORD.pack(*p) for p in points)


def write_ply_arrays(
    xyz: npt.NDArray[np.float64],
    rgb: npt.NDArray[np.uint8],
    comments: Sequence[str] = (),
    confidence: npt.NDArray[np.uint8] | None = None,
) -> bytes:
    """Same format as `write_ply`, from (n, 3) arrays without per-point Python work, plus the
    optional per-point confidence class."""
    rec = np.empty(len(xyz), dtype=_DTYPE if confidence is None else _DTYPE_CONF)
    for i, axis in enumerate("xyz"):
        rec[axis] = xyz[:, i]
    for i, channel in enumerate("rgb"):
        rec[channel] = rgb[:, i]
    if confidence is not None:
        rec["c"] = confidence
    return _header(len(xyz), comments, confidence is not None) + rec.tobytes()


def _parse(data: bytes) -> npt.NDArray[np.void]:
    end = data.index(b"end_header\n") + len(b"end_header\n")
    lines = data[:end].decode("ascii").splitlines()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise ValueError("not a binary little-endian PLY")
    count = next(int(line.split()[2]) for line in lines if line.startswith("element vertex"))
    dtype = _DTYPE_CONF if "property uchar confidence" in lines else _DTYPE
    body = data[end:]
    if len(body) != count * dtype.itemsize:
        raise ValueError("PLY body size does not match the vertex count")
    return np.frombuffer(body, dtype=dtype)


def read_ply(data: bytes) -> list[Point]:
    """Inverse of `write_ply`, for tests and validation of our own outputs."""
    rec = _parse(data)
    return [
        (float(r["x"]), float(r["y"]), float(r["z"]), int(r["r"]), int(r["g"]), int(r["b"]))
        for r in rec
    ]


def read_confidence(data: bytes) -> npt.NDArray[np.uint8] | None:
    """The per-point confidence classes, or None when the cloud carries none."""
    rec = _parse(data)
    return np.asarray(rec["c"]) if "c" in (rec.dtype.names or ()) else None


def bounds(points: Sequence[Point]) -> tuple[list[float], list[float]]:
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi
