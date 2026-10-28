"""Minimal LAS 1.2 writer/reader (point data format 2: XYZ + RGB) for the final point cloud.

Written with numpy from the ASPRS LAS 1.2 specification, so the worker needs no extra
dependency. NAZAR clouds are in a local frame with unknown scale, so the file carries **no
CRS** (no GeoKey VLR) and says so in its system identifier, unless a georeferenced export
passes an EPSG code (then a GeoKeyDirectory VLR is written). Axes are converted to the LAS
convention of +Z up: LAS (X, Y, Z) = NAZAR (x, -z, y), a proper rotation.

Per point: classification 1 (unclassified), one return, and the confidence class
(1 observed, 2 estimated, 3 inferred) in the user-data byte.
"""

import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt

HEADER_SIZE = 227
POINT_FORMAT = 2
_HEADER = struct.Struct("<4sHH16sBB32s32sHHHIIBHI5I3d3d6d")
_POINT = np.dtype(
    [
        ("x", "<i4"),
        ("y", "<i4"),
        ("z", "<i4"),
        ("intensity", "<u2"),
        ("returns", "u1"),
        ("classification", "u1"),
        ("scan_angle", "i1"),
        ("user_data", "u1"),
        ("point_source", "<u2"),
        ("red", "<u2"),
        ("green", "<u2"),
        ("blue", "<u2"),
    ]
)
SYSTEM_ID = b"NAZAR local frame, no CRS"
_VLR_HEADER = struct.Struct("<H16sHH32s")
GEOKEY_RECORD = 34735
PROJECTED_CS_KEY = 3072
SOFTWARE = b"NAZAR worker"

assert _HEADER.size == HEADER_SIZE
assert _POINT.itemsize == 26


def to_las_axes(xyz: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """NAZAR (+Y up) to LAS (+Z up)."""
    return np.stack([xyz[:, 0], -xyz[:, 2], xyz[:, 1]], axis=1)


def _scale(span: float) -> float:
    """A power-of-ten resolution that keeps every coordinate inside int32 with headroom."""
    return float(10 ** math.ceil(math.log10(max(span, 1e-9) / 1e9)))


def _geokeys(epsg: int) -> bytes:
    """GeoKeyDirectoryTag VLR (LAS 1.2 sec. 2.5.1, GeoTIFF 1.0) for a projected EPSG code.
    Vertical units are metres; no vertical datum is claimed."""
    keys = [
        (1024, 0, 1, 1),  # GTModelTypeGeoKey = ModelTypeProjected
        (1025, 0, 1, 1),  # GTRasterTypeGeoKey = RasterPixelIsArea
        (PROJECTED_CS_KEY, 0, 1, epsg),  # ProjectedCSTypeGeoKey
        (3076, 0, 1, 9001),  # ProjLinearUnitsGeoKey = metre
        (4099, 0, 1, 9001),  # VerticalUnitsGeoKey = metre
    ]
    payload = struct.pack(f"<{4 + 4 * len(keys)}H", 1, 1, 0, len(keys), *sum(keys, ()))
    head = _VLR_HEADER.pack(
        0,
        b"LASF_Projection".ljust(16, b"\0"),
        GEOKEY_RECORD,
        len(payload),
        f"EPSG:{epsg}".encode().ljust(32, b"\0"),
    )
    return head + payload


def write_las(
    xyz: npt.NDArray[np.float64],
    rgb: npt.NDArray[np.uint8],
    confidence: npt.NDArray[np.uint8] | None = None,
    *,
    created: datetime | None = None,
    enu: bool = False,
    system_id: bytes = SYSTEM_ID,
    epsg: int | None = None,
) -> bytes:
    """`enu=True`: `xyz` is already east-north-up (LAS axes); otherwise it is NAZAR (+Y up).
    `epsg`: `xyz` is in that projected CRS (e.g. UTM), written as a GeoKey VLR."""
    vlr = _geokeys(epsg) if epsg is not None else b""
    xyz = np.asarray(xyz, dtype=np.float64)
    pts = xyz if enu else to_las_axes(xyz)
    if len(pts) == 0 or not np.isfinite(pts).all():
        raise ValueError("LAS export needs at least one point and finite coordinates.")
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    offset = (lo + hi) / 2
    scale = _scale(float(np.abs(pts - offset).max()) * 2)
    rec = np.zeros(len(pts), dtype=_POINT)
    for i, axis in enumerate("xyz"):
        rec[axis] = np.round((pts[:, i] - offset[i]) / scale).astype(np.int32)
    rec["returns"] = 0b00001001  # return 1 of 1
    rec["classification"] = 1
    if confidence is not None:
        rec["user_data"] = confidence
    for i, channel in enumerate(("red", "green", "blue")):
        rec[channel] = rgb[:, i].astype(np.uint16) * 257
    when = created or datetime.now(UTC)
    header = _HEADER.pack(
        b"LASF",
        0,  # file source id
        0,  # global encoding: GPS week time; no WKT
        b"\0" * 16,  # project GUID: none
        1,
        2,
        system_id[:32].ljust(32, b"\0"),
        SOFTWARE.ljust(32, b"\0"),
        when.timetuple().tm_yday,
        when.year,
        HEADER_SIZE,
        HEADER_SIZE + len(vlr),  # offset to point data
        1 if vlr else 0,  # number of VLRs
        POINT_FORMAT,
        _POINT.itemsize,
        len(pts),
        len(pts),
        0,
        0,
        0,
        0,
        scale,
        scale,
        scale,
        *offset.tolist(),
        hi[0],
        lo[0],
        hi[1],
        lo[1],
        hi[2],
        lo[2],
    )
    return header + vlr + rec.tobytes()


@dataclass
class LasCloud:
    xyz: npt.NDArray[np.float64]
    rgb16: npt.NDArray[np.uint16]
    user_data: npt.NDArray[np.uint8]
    system_id: str
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    epsg: int | None = None


def read_las(data: bytes) -> LasCloud:
    """Reads files written by `write_las` (and other uncompressed LAS 1.2 format-2 files)."""
    h = _HEADER.unpack_from(data)
    if h[0] != b"LASF" or (h[4], h[5]) != (1, 2) or h[13] != POINT_FORMAT:
        raise ValueError("not a LAS 1.2 point-format-2 file")
    offset_to_points, count = h[11], h[15]
    scale, offset = np.array(h[21:24]), np.array(h[24:27])
    body = data[offset_to_points : offset_to_points + count * _POINT.itemsize]
    if len(body) != count * _POINT.itemsize:
        raise ValueError("LAS body is shorter than its point count")
    rec = np.frombuffer(body, dtype=_POINT)
    xyz = np.stack([rec[a] for a in "xyz"], axis=1) * scale + offset
    rgb = np.stack([rec[c] for c in ("red", "green", "blue")], axis=1)
    mx, mn = h[27:33:2], h[28:33:2]
    epsg = None
    pos = h[10]  # header size
    for _ in range(h[12]):
        _, user, record, length, _ = _VLR_HEADER.unpack_from(data, pos)
        pos += _VLR_HEADER.size
        if user.rstrip(b"\0") == b"LASF_Projection" and record == GEOKEY_RECORD:
            vals = struct.unpack_from(f"<{length // 2}H", data, pos)
            for i in range(4, 4 + 4 * vals[3], 4):
                if vals[i] == PROJECTED_CS_KEY:
                    epsg = vals[i + 3]
        pos += length
    return LasCloud(
        xyz=xyz,
        rgb16=rgb,
        user_data=np.asarray(rec["user_data"]),
        system_id=h[6].rstrip(b"\0").decode("ascii"),
        bounds_min=(mn[0], mn[1], mn[2]),
        bounds_max=(mx[0], mx[1], mx[2]),
        epsg=epsg,
    )
