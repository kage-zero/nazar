"""Optional flight telemetry: parse, normalise and validate GNSS positions for one video.

Supported inputs (text only; nothing is executed or fetched):

- **DJI SRT subtitles** recorded next to the video. Each cue's start time is the video time.
  Three field layouts are recognised:
  - `[latitude: ..] [longitude: ..] [rel_alt: .. abs_alt: ..]` (Mini / Air / FPV);
  - `[latitude : ..] [longtitude : ..] [altitude: ..]` (Mavic 2; DJI's own spelling);
  - `GPS(lon,lat,alt) BAROMETER: ..` (Phantom 3/4; longitude first).
- **Airdata CSV** flight-log exports: `time(millisecond)`, `latitude`, `longitude`,
  `height_above_takeoff(feet)`, and `isVideo` (1 while recording), which fixes the video start.
- **Plain CSV** with a `time_s` column (seconds since the video started) plus `latitude`,
  `longitude` and optionally `rel_alt_m` (above take-off) or `alt_m` (datum unknown).

Rules (brief §8): latitude/longitude are never treated as metres; they are converted to a local
east-north-up (ENU) frame through WGS84 ECEF. Altitude keeps its kind: height above take-off
(relative) is not ellipsoidal or sea-level height. Samples without a fix (0, 0), out-of-range
values, non-increasing times and physically impossible jumps are dropped and counted. Gaps are
reported and never interpolated across.
"""

import csv
import io
import math
import re
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from nazar_contracts import AltitudeKind, TelemetrySummary, TimeGap

MAX_BYTES = 20 * 1024 * 1024
GAP_S = 1.5
"""A pause between samples longer than this is a gap (DJI SRT writes 1-30 samples per second)."""
MAX_SPEED_MS = 45.0
"""Faster than any consumer drone: a jump implying more is a GNSS glitch, not motion."""
FEET = 0.3048


class TelemetryError(ValueError):
    """The file cannot be used; the message says why, in plain words."""


@dataclass
class Track:
    format: str
    t: npt.NDArray[np.float64]
    """Seconds since the video started."""
    lat: npt.NDArray[np.float64]
    lon: npt.NDArray[np.float64]
    alt: npt.NDArray[np.float64]
    """Metres, of kind `altitude_kind`; NaN when the source had no altitude."""
    altitude_kind: AltitudeKind
    dropped: dict[str, int] = field(default_factory=dict)
    gaps: list[tuple[float, float]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)


# --------------------------------------------------------------------------------- parsing

_CUE_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->")
_NUM = r"(-?\d+(?:\.\d+)?)"
_LAT = re.compile(r"\[\s*latitude\s*:\s*" + _NUM, re.I)
_LON = re.compile(r"\[\s*long?t?itude\s*:\s*" + _NUM, re.I)
_REL_ALT = re.compile(r"rel_alt\s*:\s*" + _NUM, re.I)
_ALT = re.compile(r"\[\s*altitude\s*:\s*" + _NUM, re.I)
_GPS = re.compile(r"GPS\s*\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)", re.I)
_BARO = re.compile(r"BAROMETER\s*:\s*" + _NUM, re.I)


def _cue_seconds(m: re.Match[str]) -> float:
    h, mnt, s, ms = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text: str) -> Track:
    rows: list[tuple[float, float, float, float]] = []
    kinds: set[AltitudeKind] = set()
    for block in re.split(r"\r?\n\s*\r?\n", text):
        when = _CUE_TIME.search(block)
        if not when:
            continue
        t = _cue_seconds(when)
        lat_m, lon_m = _LAT.search(block), _LON.search(block)
        alt = math.nan
        kind = AltitudeKind.NONE
        if lat_m and lon_m:
            lat, lon = float(lat_m.group(1)), float(lon_m.group(1))
            if rel := _REL_ALT.search(block):
                alt, kind = float(rel.group(1)), AltitudeKind.RELATIVE
            elif absolute := _ALT.search(block):
                alt, kind = float(absolute.group(1)), AltitudeKind.ABSOLUTE_UNSPECIFIED
        elif gps := _GPS.search(block):
            lon, lat = float(gps.group(1)), float(gps.group(2))  # DJI writes longitude first
            if baro := _BARO.search(block):
                alt, kind = float(baro.group(1)), AltitudeKind.RELATIVE
            else:
                alt, kind = float(gps.group(3)), AltitudeKind.ABSOLUTE_UNSPECIFIED
        else:
            continue
        kinds.add(kind)
        rows.append((t, lat, lon, alt))
    if not rows:
        raise TelemetryError(
            "No GPS positions found. Expected DJI SRT cues with latitude/longitude "
            "(e.g. '[latitude: 41.89] [longitude: 12.49]' or 'GPS(lon,lat,alt)')."
        )
    return _track("dji_srt", rows, kinds)


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def parse_csv(text: str) -> Track:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise TelemetryError("The CSV has no header row.")
    cols = {_norm(c): c for c in reader.fieldnames}

    def pick(*names: str) -> str | None:
        return next((cols[n] for n in names if n in cols), None)

    lat_c, lon_c = pick("latitude", "lat"), pick("longitude", "lon", "lng")
    if lat_c is None or lon_c is None:
        raise TelemetryError("The CSV needs 'latitude' and 'longitude' columns.")
    airdata = pick("time(millisecond)")
    time_c = airdata or pick("time_s", "video_time_s")
    if time_c is None:
        raise TelemetryError(
            "The CSV needs a time column: 'time_s' (seconds since the video started) or an "
            "Airdata export's 'time(millisecond)' with 'isVideo'."
        )
    video_c = pick("isvideo")
    if airdata and video_c is None:
        raise TelemetryError(
            "This Airdata export has no 'isVideo' column, so the video start time is unknown."
        )
    alt_specs = [
        ("height_above_takeoff(feet)", FEET, AltitudeKind.RELATIVE),
        ("height_above_takeoff(meters)", 1.0, AltitudeKind.RELATIVE),
        ("rel_alt_m", 1.0, AltitudeKind.RELATIVE),
        ("altitude_above_sealevel(feet)", FEET, AltitudeKind.ABSOLUTE_UNSPECIFIED),
        ("alt_m", 1.0, AltitudeKind.ABSOLUTE_UNSPECIFIED),
    ]
    alt_c, alt_scale, kind = None, 1.0, AltitudeKind.NONE
    for name, scale, k in alt_specs:
        if name in cols:
            alt_c, alt_scale, kind = cols[name], scale, k
            break

    rows: list[tuple[float, float, float, float]] = []
    start: float | None = None
    for line_no, rec in enumerate(reader, start=2):
        try:
            t = float(rec[time_c])
            lat, lon = float(rec[lat_c]), float(rec[lon_c])
            alt = (
                float(rec[alt_c]) * alt_scale
                if alt_c and rec[alt_c] not in ("", None)
                else math.nan
            )
        except (TypeError, ValueError) as exc:
            raise TelemetryError(f"Line {line_no}: not a number ({exc}).") from None
        if airdata:
            if (rec[video_c or ""] or "0").strip() not in ("1", "true", "True"):
                continue
            t /= 1000
            if start is None:
                start = t
            t -= start
        rows.append((t, lat, lon, alt))
    if not rows:
        raise TelemetryError(
            "No usable rows (an Airdata export needs rows with isVideo = 1 for this video)."
        )
    return _track("airdata_csv" if airdata else "csv", rows, {kind})


def parse_telemetry(filename: str, data: bytes) -> Track:
    if len(data) > MAX_BYTES:
        raise TelemetryError(f"Telemetry files are limited to {MAX_BYTES // 2**20} MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise TelemetryError("The file is not UTF-8 text.") from None
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "srt":
        return parse_srt(text)
    if suffix == "csv":
        return parse_csv(text)
    raise TelemetryError("Unsupported telemetry file. Use a DJI .SRT or a .CSV export.")


# ------------------------------------------------------------------------------ validation


def _track(
    fmt: str, rows: list[tuple[float, float, float, float]], kinds: set[AltitudeKind]
) -> Track:
    real = kinds - {AltitudeKind.NONE}
    if len(real) > 1:
        raise TelemetryError("The file mixes relative and absolute altitudes.")
    kind = real.pop() if real else AltitudeKind.NONE
    arr = np.array(rows, dtype=np.float64)
    dropped: dict[str, int] = {}

    def drop(mask: npt.NDArray[np.bool_], reason: str) -> None:
        nonlocal arr
        if mask.any():
            dropped[reason] = dropped.get(reason, 0) + int(mask.sum())
            arr = arr[~mask]

    t, lat, lon = arr[:, 0], arr[:, 1], arr[:, 2]
    drop((np.abs(lat) < 1e-9) & (np.abs(lon) < 1e-9), "no_fix")
    t, lat, lon = arr[:, 0], arr[:, 1], arr[:, 2]
    drop(
        ~np.isfinite(t)
        | (t < 0)
        | ~np.isfinite(lat)
        | ~np.isfinite(lon)
        | (np.abs(lat) > 90)
        | (np.abs(lon) > 180),
        "out_of_range",
    )
    # Keep the first of non-increasing timestamps (duplicates / clock steps).
    keep: list[int] = []
    last = -math.inf
    for i, ti in enumerate(arr[:, 0]):
        if ti > last:
            keep.append(i)
            last = ti
    if len(keep) < len(arr):
        dropped["non_increasing_time"] = len(arr) - len(keep)
        arr = arr[keep]
    # Impossible jumps: compare each sample with the last accepted one.
    if len(arr) > 1:
        enu = to_enu(arr[:, 1], arr[:, 2], np.zeros(len(arr)), float(arr[0, 1]), float(arr[0, 2]))
        good = [0]
        for i in range(1, len(arr)):
            j = good[-1]
            dt = arr[i, 0] - arr[j, 0]
            if np.linalg.norm(enu[i, :2] - enu[j, :2]) <= MAX_SPEED_MS * dt + 2.0:
                good.append(i)
        if len(good) < len(arr):
            dropped["impossible_jump"] = len(arr) - len(good)
            arr = arr[good]
    if len(arr) < 2:
        raise TelemetryError("Fewer than two valid GPS positions remain after validation.")
    dt = np.diff(arr[:, 0])
    gaps = [(float(arr[i, 0]), float(arr[i + 1, 0])) for i in np.flatnonzero(dt > GAP_S)]
    return Track(
        format=fmt,
        t=arr[:, 0].copy(),
        lat=arr[:, 1].copy(),
        lon=arr[:, 2].copy(),
        alt=arr[:, 3].copy(),
        altitude_kind=kind,
        dropped=dropped,
        gaps=gaps,
    )


# ------------------------------------------------------------------------------ geodesy

_A = 6378137.0  # WGS84 semi-major axis (m)
_E2 = 6.69437999014e-3  # WGS84 first eccentricity squared


def _ecef(
    lat: npt.NDArray[np.float64], lon: npt.NDArray[np.float64], h: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    la, lo = np.radians(lat), np.radians(lon)
    n = _A / np.sqrt(1 - _E2 * np.sin(la) ** 2)
    return np.stack(
        [
            (n + h) * np.cos(la) * np.cos(lo),
            (n + h) * np.cos(la) * np.sin(lo),
            (n * (1 - _E2) + h) * np.sin(la),
        ],
        axis=1,
    )


def to_enu(
    lat: npt.NDArray[np.float64],
    lon: npt.NDArray[np.float64],
    h: npt.NDArray[np.float64],
    lat0: float,
    lon0: float,
    h0: float = 0.0,
) -> npt.NDArray[np.float64]:
    """East-north-up metres relative to (lat0, lon0, h0), via WGS84 ECEF. Heights only need to
    share a datum with h0: differences of height above take-off are valid ENU 'up' offsets."""
    ref = _ecef(np.array([lat0]), np.array([lon0]), np.array([h0]))[0]
    d = _ecef(lat, lon, h) - ref
    la, lo = math.radians(lat0), math.radians(lon0)
    rot = np.array(
        [
            [-math.sin(lo), math.cos(lo), 0.0],
            [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
            [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)],
        ]
    )
    return np.asarray(d @ rot.T)


def track_enu(track: Track) -> npt.NDArray[np.float64]:
    """Positions in ENU metres around the first sample. Without altitude, up is 0."""
    h = np.nan_to_num(track.alt, nan=0.0)
    return to_enu(track.lat, track.lon, h, float(track.lat[0]), float(track.lon[0]), float(h[0]))


def sample_at(track: Track, times: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """ENU position at each time, linearly interpolated between neighbouring samples, or NaN
    outside the track or inside a gap (never interpolated across)."""
    enu = track_enu(track)
    out = np.full((len(times), 3), np.nan)
    idx = np.searchsorted(track.t, times)
    for k, (tq, i) in enumerate(zip(times, idx, strict=True)):
        if i < len(track.t) and track.t[i] == tq:
            out[k] = enu[i]
        elif 0 < i < len(track.t) and track.t[i] - track.t[i - 1] <= GAP_S:
            w = (tq - track.t[i - 1]) / (track.t[i] - track.t[i - 1])
            out[k] = (1 - w) * enu[i - 1] + w * enu[i]
    return out


def covered_seconds(track: Track, start: float, end: float) -> float:
    """Seconds of [start, end] lying between consecutive samples that are not a gap."""
    total = 0.0
    for a, b in zip(track.t[:-1], track.t[1:], strict=True):
        if b - a <= GAP_S:
            total += max(0.0, min(b, end) - max(a, start))
    return total


def summarize(track: Track, video_duration_s: float | None) -> TelemetrySummary:
    enu = track_enu(track)
    has_alt = bool(np.isfinite(track.alt).any())
    findings: list[str] = []
    coverage = None
    if video_duration_s:
        coverage = covered_seconds(track, 0.0, video_duration_s) / video_duration_s
        if track.t[0] > 1.0:
            findings.append(
                f"Telemetry starts {track.t[0]:.1f} s after the video: early frames have "
                "no position."
            )
        if track.t[-1] > video_duration_s + 1.0:
            findings.append(
                f"Telemetry runs {track.t[-1] - video_duration_s:.1f} s past the end of the "
                "video. Check that it belongs to this clip."
            )
        if coverage < 0.5:
            findings.append(
                f"Only {coverage:.0%} of the video has positions; alignment needs most of it."
            )
    if track.altitude_kind is AltitudeKind.RELATIVE:
        findings.append(
            "Altitude is height above take-off (barometric/fused), not sea-level or "
            "ellipsoidal height. Fine for the shape of the flight, not for absolute elevation."
        )
    elif track.altitude_kind is AltitudeKind.ABSOLUTE_UNSPECIFIED:
        findings.append(
            "Altitude datum is not stated by the source (sea level or ellipsoid); absolute "
            "elevations are uncertain by tens of metres."
        )
    else:
        findings.append("No altitude: only horizontal positions are available.")
    findings.append(
        "Consumer GNSS is typically accurate to a few metres horizontally; geographic "
        "placement inherits that uncertainty."
    )
    if track.gaps:
        findings.append(f"{len(track.gaps)} gap(s) longer than {GAP_S} s; not interpolated.")
    dt = np.diff(track.t)
    return TelemetrySummary(
        format=track.format,
        samples=len(track),
        start_s=round(float(track.t[0]), 3),
        end_s=round(float(track.t[-1]), 3),
        rate_hz=round(float(1 / np.median(dt)), 2),
        altitude_kind=track.altitude_kind,
        horizontal_extent_m=round(float(np.linalg.norm(enu[:, :2], axis=1).max()), 2),
        height_range_m=round(float(np.nanmax(track.alt) - np.nanmin(track.alt)), 2)
        if has_alt
        else None,
        gaps=[TimeGap(start_s=a, end_s=b) for a, b in track.gaps[:50]],
        dropped=track.dropped,
        video_duration_s=video_duration_s,
        video_coverage=round(coverage, 3) if coverage is not None else None,
        findings=findings,
    )


def track_to_json(track: Track) -> dict[str, object]:
    """Lossless JSON form stored next to the upload and handed to the worker."""
    return {
        "schema": "nazar.telemetry-track/1",
        "format": track.format,
        "altitude_kind": track.altitude_kind.value,
        "t": track.t.tolist(),
        "lat": track.lat.tolist(),
        "lon": track.lon.tolist(),
        "alt": [None if math.isnan(a) else a for a in track.alt.tolist()],
        "dropped": track.dropped,
        "gaps": track.gaps,
    }


def track_from_json(doc: dict[str, object]) -> Track:
    def arr(key: str) -> npt.NDArray[np.float64]:
        values = doc[key]
        assert isinstance(values, list)
        return np.array([math.nan if v is None else v for v in values], dtype=np.float64)

    dropped = doc.get("dropped") or {}
    gaps = doc.get("gaps") or []
    assert isinstance(dropped, dict) and isinstance(gaps, list)
    return Track(
        format=str(doc["format"]),
        t=arr("t"),
        lat=arr("lat"),
        lon=arr("lon"),
        alt=arr("alt"),
        altitude_kind=AltitudeKind(str(doc["altitude_kind"])),
        dropped={str(k): int(v) for k, v in dropped.items()},
        gaps=[(float(a), float(b)) for a, b in gaps],
    )
