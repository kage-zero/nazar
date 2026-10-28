"""WGS84 geodesy for georeferenced exports: ENU -> geodetic -> UTM (EPSG 326xx / 327xx).

Forward transverse Mercator uses Krüger's series to n^4 (as in Karney 2011, eqs. 35-36),
accurate to well under a millimetre within a UTM zone. Implemented with numpy so the worker
needs no PROJ dependency.
"""

import math

import numpy as np
import numpy.typing as npt

A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
K0 = 0.9996
FALSE_EASTING = 500_000.0
FALSE_NORTHING_SOUTH = 10_000_000.0


def utm_zone(lat: float, lon: float) -> tuple[int, bool]:
    """Standard zone number and hemisphere (True = north). Norway/Svalbard exceptions are not
    applied; the zone is still a valid projection, just not the 'official' one there."""
    zone = math.floor((lon + 180) / 6) % 60 + 1
    return zone, lat >= 0


def epsg(zone: int, north: bool) -> int:
    return (32600 if north else 32700) + zone


def enu_to_geodetic(
    enu: npt.NDArray[np.float64], lat0: float, lon0: float, h0: float
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Inverse of the ENU tangent plane at (lat0, lon0, h0): latitude, longitude (degrees)
    and ellipsoidal-style height (same datum as h0)."""
    la, lo = math.radians(lat0), math.radians(lon0)
    rot = np.array(
        [
            [-math.sin(lo), math.cos(lo), 0.0],
            [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
            [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)],
        ]
    )
    n0 = A / math.sqrt(1 - E2 * math.sin(la) ** 2)
    ref = np.array(
        [
            (n0 + h0) * math.cos(la) * math.cos(lo),
            (n0 + h0) * math.cos(la) * math.sin(lo),
            (n0 * (1 - E2) + h0) * math.sin(la),
        ]
    )
    x, y, z = (enu @ rot + ref).T
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - E2))
    for _ in range(5):  # converges to < 1e-12 rad near the surface
        n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - E2 * n / (n + h)))
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(lon), h


def to_utm(
    lat: npt.NDArray[np.float64], lon: npt.NDArray[np.float64], zone: int, north: bool
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Easting, northing (metres) in the given UTM zone."""
    n = F / (2 - F)
    big_a = A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    alpha = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16 + 41 * n**4 / 180,
        13 * n**2 / 48 - 3 * n**3 / 5 + 557 * n**4 / 1440,
        61 * n**3 / 240 - 103 * n**4 / 140,
        49561 * n**4 / 161280,
    ]
    phi = np.radians(lat)
    lam = np.radians(lon) - math.radians(zone * 6 - 183)
    e = math.sqrt(E2)
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xi = np.arctan2(t, np.cos(lam))
    eta = np.arctanh(np.sin(lam) / np.sqrt(1 + t**2))
    xs, es = xi.copy(), eta.copy()
    for j, a in enumerate(alpha, start=1):
        xs += a * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        es += a * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    easting = FALSE_EASTING + K0 * big_a * es
    northing = K0 * big_a * xs + (0.0 if north else FALSE_NORTHING_SOUTH)
    return easting, northing


def enu_to_utm(
    enu: npt.NDArray[np.float64], lat0: float, lon0: float, h0: float
) -> tuple[npt.NDArray[np.float64], int]:
    """ENU points -> (easting, northing, height) in the UTM zone of the ENU origin, and the
    EPSG code of that zone. Height keeps h0's datum (e.g. above take-off)."""
    zone, north = utm_zone(lat0, lon0)
    lat, lon, h = enu_to_geodetic(enu, lat0, lon0, h0)
    east, northing = to_utm(lat, lon, zone, north)
    return np.stack([east, northing, h], axis=1), epsg(zone, north)
