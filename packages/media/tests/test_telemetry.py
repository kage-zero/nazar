# ruff: noqa: E501 - fixture lines reproduce DJI subtitle lines verbatim
"""Telemetry parsing and validation.

SYNTHETIC FIXTURES: no real flight log was supplied with the project, so every file below is
written by hand in the documented layout of its format. They test parsing and validation
rules, not any real flight.
"""

import math

import numpy as np
import pytest

from nazar_contracts import AltitudeKind
from nazar_media.telemetry import (
    TelemetryError,
    parse_telemetry,
    sample_at,
    summarize,
    to_enu,
    track_enu,
    track_from_json,
    track_to_json,
)

SRT_MINI = """1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2024-05-01 10:00:00.000
[iso: 100] [shutter: 1/500.0] [fnum: 1.7] [ev: 0] [ct: 5500] [color_md : default] [focal_len: 24.00] [latitude: 41.890210] [longitude: 12.492231] [rel_alt: 50.000 abs_alt: 98.512] </font>

2
00:00:01,000 --> 00:00:01,033
<font size="28">FrameCnt: 31, DiffTime: 33ms
2024-05-01 10:00:01.000
[iso: 100] [latitude: 41.890300] [longitude: 12.492231] [rel_alt: 51.000 abs_alt: 99.512] </font>

3
00:00:02,000 --> 00:00:02,033
<font size="28">FrameCnt: 61, DiffTime: 33ms
[latitude: 41.890390] [longitude: 12.492231] [rel_alt: 52.000 abs_alt: 100.512] </font>
"""

SRT_PHANTOM = """1
00:00:00,000 --> 00:00:01,000
HOME(12.4922,41.8902) 2017.08.05 14:11:51
GPS(12.492231,41.890210,16) BAROMETER:30.5
ISO:100 Shutter:60 EV:0 Fnum:2.2

2
00:00:01,000 --> 00:00:02,000
HOME(12.4922,41.8902) 2017.08.05 14:11:52
GPS(12.492331,41.890210,16) BAROMETER:30.9
ISO:100 Shutter:60 EV:0 Fnum:2.2
"""

SRT_MAVIC2 = """1
00:00:00,000 --> 00:00:00,033
[latitude : 41.890210] [longtitude : 12.492231] [altitude: 120.300000]

2
00:00:00,500 --> 00:00:00,533
[latitude : 41.890215] [longtitude : 12.492231] [altitude: 120.400000]
"""

AIRDATA = """time(millisecond),datetime(utc),latitude,longitude,height_above_takeoff(feet),isVideo
0,2024-05-01 10:00:00,41.890210,12.492231,0,0
1000,2024-05-01 10:00:01,41.890210,12.492231,100,1
2000,2024-05-01 10:00:02,41.890300,12.492231,110,1
3000,2024-05-01 10:00:03,41.890390,12.492231,120,1
"""


def test_dji_srt_mini_layout() -> None:
    track = parse_telemetry("DJI_0001.SRT", SRT_MINI.encode())
    assert track.format == "dji_srt"
    assert track.t.tolist() == [0.0, 1.0, 2.0]
    assert track.lat[1] == pytest.approx(41.8903)
    assert track.altitude_kind is AltitudeKind.RELATIVE
    assert track.alt.tolist() == [50.0, 51.0, 52.0]


def test_dji_srt_phantom_layout_has_longitude_first() -> None:
    track = parse_telemetry("x.srt", SRT_PHANTOM.encode())
    assert track.lat[0] == pytest.approx(41.89021) and track.lon[0] == pytest.approx(12.492231)
    assert track.altitude_kind is AltitudeKind.RELATIVE  # barometer, above take-off
    assert track.alt.tolist() == [30.5, 30.9]


def test_dji_srt_mavic2_misspelling_and_absolute_altitude() -> None:
    track = parse_telemetry("x.SRT", SRT_MAVIC2.encode())
    assert track.t.tolist() == [0.0, 0.5]
    assert track.altitude_kind is AltitudeKind.ABSOLUTE_UNSPECIFIED


def test_airdata_csv_starts_at_recording_and_converts_feet() -> None:
    track = parse_telemetry("flight.csv", AIRDATA.encode())
    assert track.format == "airdata_csv"
    assert track.t.tolist() == [0.0, 1.0, 2.0]  # the isVideo=0 row is before the video
    assert track.alt[0] == pytest.approx(30.48)
    assert track.altitude_kind is AltitudeKind.RELATIVE


def test_plain_csv_without_altitude() -> None:
    track = parse_telemetry("t.csv", b"time_s,lat,lon\n0,41.89,12.49\n1,41.8901,12.49\n")
    assert track.altitude_kind is AltitudeKind.NONE
    assert all(math.isnan(a) for a in track.alt)


def test_bad_rows_are_dropped_and_counted_never_repaired() -> None:
    rows = [
        "time_s,latitude,longitude,rel_alt_m",
        "0,41.890210,12.492231,50",
        "1,0,0,50",  # no fix
        "1,41.890300,12.492231,50",
        "1,41.890300,12.492231,50",  # duplicate time
        "2,41.990300,12.492231,50",  # 11 km in one second: glitch
        "3,41.890480,12.492231,50",
        "9,41.890500,12.492231,50",  # gap of 6 s
    ]
    track = parse_telemetry("t.csv", "\n".join(rows).encode())
    assert track.dropped == {"no_fix": 1, "non_increasing_time": 1, "impossible_jump": 1}
    assert track.t.tolist() == [0.0, 1.0, 3.0, 9.0]
    assert track.gaps == [(1.0, 3.0), (3.0, 9.0)]


@pytest.mark.parametrize(
    ("name", "body", "message"),
    [
        ("x.txt", b"hello", "Unsupported"),
        ("x.srt", b"1\n00:00:00,000 --> 00:00:01,000\nno gps here\n", "No GPS"),
        ("x.csv", b"a,b\n1,2\n", "latitude"),
        ("x.csv", b"latitude,longitude\n1,2\n", "time column"),
        ("x.csv", b"time_s,latitude,longitude\n0,41,12\nx,41,12\n", "Line 3"),
        ("x.csv", b"time_s,latitude,longitude\n0,41,12\n", "Fewer than two"),
        ("x.csv", b"\xff\xfe", "UTF-8"),
    ],
)
def test_unusable_files_are_rejected_with_a_reason(name: str, body: bytes, message: str) -> None:
    with pytest.raises(TelemetryError, match=message):
        parse_telemetry(name, body)


def test_enu_matches_known_geodesy() -> None:
    # 0.001 deg of latitude at 41.89 N is ~111.07 m north (WGS84 meridian arc).
    enu = to_enu(np.array([41.891]), np.array([12.49]), np.array([0.0]), 41.89, 12.49)
    assert enu[0, 1] == pytest.approx(111.07, abs=0.1)
    assert abs(enu[0, 0]) < 0.01
    # 0.001 deg of longitude there is ~82.9 m east, not 111 m: lat/lon are not metres.
    enu = to_enu(np.array([41.89]), np.array([12.491]), np.array([0.0]), 41.89, 12.49)
    assert enu[0, 0] == pytest.approx(82.9, abs=0.2)


def test_sampling_interpolates_within_but_never_across_gaps() -> None:
    track = parse_telemetry(
        "t.csv",
        b"time_s,latitude,longitude,rel_alt_m\n0,41.89,12.49,10\n1,41.8901,12.49,12\n"
        b"5,41.8905,12.49,20\n",
    )
    enu = track_enu(track)
    got = sample_at(track, np.array([0.5, 3.0, 7.0, 1.0]))
    assert got[0] == pytest.approx((enu[0] + enu[1]) / 2)
    assert np.isnan(got[1]).all()  # inside the 4 s gap
    assert np.isnan(got[2]).all()  # after the track
    assert got[3] == pytest.approx(enu[1])
    assert enu[1, 2] == pytest.approx(2.0, abs=0.01)  # relative heights give ENU up offsets


def test_summary_reports_coverage_and_altitude_meaning() -> None:
    track = parse_telemetry("DJI_0001.SRT", SRT_MINI.encode())
    summary = summarize(track, video_duration_s=4.0)
    assert summary.samples == 3 and summary.rate_hz == 1.0
    assert summary.video_coverage == 0.5  # samples span 0-2 s of a 4 s video
    assert summary.altitude_kind is AltitudeKind.RELATIVE
    assert summary.height_range_m == 2.0
    assert summary.horizontal_extent_m == pytest.approx(20.0, abs=0.1)  # 0.00018 deg north
    assert any("height above take-off" in f for f in summary.findings)
    assert summarize(track, None).video_coverage is None


def test_track_json_round_trip_keeps_missing_altitude() -> None:
    track = parse_telemetry("t.csv", b"time_s,lat,lon\n0,41.89,12.49\n1,41.8901,12.49\n")
    again = track_from_json(track_to_json(track))
    assert again.t.tolist() == track.t.tolist()
    assert np.isnan(again.alt).all()
    assert again.altitude_kind is AltitudeKind.NONE
