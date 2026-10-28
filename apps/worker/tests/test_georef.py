"""Sensor alignment. SYNTHETIC DATA: tracks are generated from a known similarity transform
(no real flight log was supplied), so the tests check the maths and the acceptance rules."""

import math

import numpy as np

from nazar_contracts import AltitudeKind
from nazar_media.telemetry import Track, track_enu
from nazar_worker.georef import align, umeyama
from nazar_worker.utm import to_utm, utm_zone

LAT0, LON0 = 41.8902, 12.4922
M_PER_DEG_LAT = 111_070.0


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def orbit_enu(n: int, radius: float, climb: float = 0.0) -> np.ndarray:
    a = np.linspace(0, 1.5 * math.pi, n)
    return np.stack([radius * np.cos(a), radius * np.sin(a), 40 + climb * a], axis=1)


def track_from_enu(t: np.ndarray, enu: np.ndarray, kind: AltitudeKind) -> Track:
    lat = LAT0 + enu[:, 1] / M_PER_DEG_LAT
    lon = LON0 + enu[:, 0] / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
    return Track("csv", t, lat, lon, enu[:, 2].copy(), kind)


def local_from_enu(enu: np.ndarray, scale: float) -> np.ndarray:
    """A 'reconstruction': ENU seen through an unknown similarity (local -> ENU is known)."""
    r = rot_y(0.7) @ np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])
    return np.asarray(((enu - enu.mean(axis=0)) @ r) / scale)


def test_umeyama_recovers_a_known_transform() -> None:
    rng = np.random.default_rng(1)
    src = rng.normal(size=(20, 3))
    rot = rot_y(0.4)
    dst = 3.5 * src @ rot.T + np.array([1, 2, 3])
    s, r, t = umeyama(src, dst)
    assert math.isclose(s, 3.5, rel_tol=1e-9)
    assert np.allclose(r, rot) and np.allclose(t, [1, 2, 3])


def test_orbit_with_gnss_noise_gives_scale_and_georeference() -> None:
    rng = np.random.default_rng(2)
    t = np.arange(0, 30, 0.1)
    truth = orbit_enu(len(t), radius=60, climb=3)
    track = track_from_enu(
        t, truth + rng.normal(scale=1.5, size=truth.shape), AltitudeKind.RELATIVE
    )
    kf = np.arange(0, 300, 12)
    centres = local_from_enu(truth[kf], scale=6.0)
    got = align(centres, t[kf], track)
    assert got.scale_accepted and got.orientation_accepted, got.reasons
    assert got.metres_per_unit is not None
    assert math.isclose(got.metres_per_unit, 6.0, rel_tol=0.03)
    assert got.residual_rms_m is not None and got.residual_rms_m < 4
    # Camera centres land on the GNSS track in ENU metres around the first fix.
    enu = got.to_enu(centres)
    assert np.abs(enu - track_enu(track)[kf]).max() < 8


def test_clock_offset_is_detected() -> None:
    # A path whose speed varies: on a uniform orbit a time shift is just a rotation and
    # cannot be observed.
    t = np.arange(0, 30, 0.1)
    u = (t / 30) ** 2 * 1.5 * math.pi
    truth = np.stack([60 * np.cos(u), 60 * np.sin(u), 40 + 0.3 * t**1.5], axis=1)
    track = track_from_enu(t, truth, AltitudeKind.RELATIVE)
    kf = np.arange(20, 280, 10)
    # The video clock runs 0.8 s behind the telemetry clock.
    got = align(local_from_enu(truth[kf], 4.0), t[kf] - 0.8, track)
    assert got.scale_accepted
    assert math.isclose(got.time_offset_s, 0.8, abs_tol=0.11)


def test_straight_line_gives_scale_but_no_orientation() -> None:
    t = np.arange(0, 20, 0.5)
    truth = np.stack([5 * t, np.zeros_like(t), 40 + 0.01 * t], axis=1)
    track = track_from_enu(t, truth, AltitudeKind.RELATIVE)
    kf = np.arange(0, len(t), 3)
    got = align(local_from_enu(truth[kf], 10.0), t[kf], track)
    assert got.scale_accepted and not got.orientation_accepted
    assert "straight line" in got.reasons[0]


def test_hover_is_rejected_short_baseline() -> None:
    t = np.arange(0, 20, 0.5)
    truth = orbit_enu(len(t), radius=3)
    track = track_from_enu(t, truth, AltitudeKind.RELATIVE)
    kf = np.arange(0, len(t), 3)
    got = align(local_from_enu(truth[kf], 1.0), t[kf], track)
    assert not got.scale_accepted
    assert any("at least 20 m" in r for r in got.reasons)


def test_telemetry_from_another_flight_is_rejected() -> None:
    t = np.arange(0, 30, 0.5)
    track = track_from_enu(t, orbit_enu(len(t), radius=60, climb=3), AltitudeKind.RELATIVE)
    rng = np.random.default_rng(3)
    centres = rng.normal(scale=5, size=(20, 3))
    got = align(centres, np.linspace(0, 29, 20), track)
    assert not got.scale_accepted
    assert any("does not match" in r for r in got.reasons)


def test_no_altitude_and_no_overlap_are_rejected() -> None:
    t = np.arange(0, 30, 0.5)
    truth = orbit_enu(len(t), radius=60)
    centres = local_from_enu(truth[::5], 5.0)
    flat = track_from_enu(t, truth, AltitudeKind.NONE)
    assert "no altitude" in align(centres, t[::5], flat).reasons[0]
    late = track_from_enu(t + 100, truth, AltitudeKind.RELATIVE)
    assert "Fewer than 5" in align(centres, t[::5], late).reasons[0]


def test_georeferenced_points_land_on_the_gnss_track_in_utm() -> None:
    t = np.arange(0, 30, 0.1)
    truth = orbit_enu(len(t), radius=60, climb=3)
    track = track_from_enu(t, truth, AltitudeKind.RELATIVE)
    kf = np.arange(0, 300, 12)
    centres = local_from_enu(truth[kf], scale=6.0)
    got = align(centres, t[kf], track)
    assert got.orientation_accepted
    utm, code = got.to_utm(centres)
    zone, north = utm_zone(LAT0, LON0)
    assert code == 32633 and (zone, north) == (33, True)
    e, n = to_utm(track.lat[kf], track.lon[kf], zone, north)
    # track_from_enu uses a flat-earth metres-per-degree, so the synthetic track is ~0.1 %
    # anisotropically distorted; a similarity cannot absorb that (~0.15 m over this orbit).
    assert np.abs(utm[:, 0] - e).max() < 0.25 and np.abs(utm[:, 1] - n).max() < 0.25
    assert np.abs(utm[:, 2] - track.alt[kf]).max() < 0.25  # heights stay above take-off
