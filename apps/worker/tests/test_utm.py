import numpy as np
import pytest

from nazar_media.telemetry import to_enu
from nazar_worker.utm import enu_to_geodetic, enu_to_utm, epsg, to_utm, utm_zone

# Reference values computed with PROJ (pyproj 3.7.1, EPSG:4326 -> EPSG:326xx/327xx) on
# 2026-10-28, in a throwaway environment; pyproj is not a dependency of the project.
PROJ = [
    (41.8902, 12.4922, 33, True, 291945.9942, 4640626.5972),  # Colosseum
    (0.0, 15.0, 33, True, 500000.0, 0.0),
    (0.0, 18.0, 33, True, 833978.5569, 0.0),
    (45.0, 15.0, 33, True, 500000.0, 4982950.4002),
    (-33.8568, 151.2153, 56, False, 334900.5697, 6252288.7529),  # Sydney
    (64.1, -21.9, 27, True, 456137.5541, 7108467.4170),  # Reykjavik
]


@pytest.mark.parametrize(("lat", "lon", "zone", "north", "east", "northing"), PROJ)
def test_utm_matches_proj(
    lat: float, lon: float, zone: int, north: bool, east: float, northing: float
) -> None:
    if lon % 6:  # on a zone edge (e.g. 18 E) the reference projects into the western zone
        assert utm_zone(lat, lon) == (zone, north)
    e, n = to_utm(np.array([lat]), np.array([lon]), zone, north)
    assert e[0] == pytest.approx(east, abs=1e-3)
    assert n[0] == pytest.approx(northing, abs=1e-3)


def test_epsg_codes() -> None:
    assert epsg(33, True) == 32633 and epsg(56, False) == 32756


def test_enu_round_trip() -> None:
    lat0, lon0, h0 = 41.8902, 12.4922, 30.0
    pts = np.array([[0, 0, 0], [120.0, -80.0, 15.0], [-300.0, 250.0, -10.0]])
    lat, lon, h = enu_to_geodetic(pts, lat0, lon0, h0)
    back = to_enu(lat, lon, h, lat0, lon0, h0)
    assert np.abs(back - pts).max() < 1e-6


def test_enu_origin_lands_on_its_utm_coordinates() -> None:
    utm, code = enu_to_utm(np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 2.0]]), 41.8902, 12.4922, 30.0)
    assert code == 32633
    assert utm[0, :2] == pytest.approx([291945.9942, 4640626.5972], abs=1e-3)
    assert utm[0, 2] == pytest.approx(30.0, abs=1e-6)
    # 10 m east in ENU is ~10 m in UTM (grid convergence and scale factor are small here).
    assert np.linalg.norm(utm[1, :2] - utm[0, :2]) == pytest.approx(10.0, rel=2e-3)
    assert utm[1, 2] == pytest.approx(32.0, abs=1e-3)
