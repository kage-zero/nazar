"""Read container/stream facts with ffprobe. Nothing here trusts the file extension."""

import itertools
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from nazar_contracts import VideoProbe
from nazar_media.ffmpeg import MediaError, run_ffprobe


def _rate(value: object) -> float | None:
    if not isinstance(value, str) or value in ("0/0", ""):
        return None
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    return float(rate) if rate > 0 else None


def _rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return round(float(side["rotation"])) % 360
    rotate = stream.get("tags", {}).get("rotate")
    return int(rotate) % 360 if rotate is not None else 0


def _float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "N/A") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_probe(raw: dict[str, Any]) -> VideoProbe:
    streams: list[dict[str, Any]] = raw.get("streams", [])
    fmt: dict[str, Any] = raw.get("format", {})
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not s.get("disposition", {}).get("attached_pic", 0)
        ),
        None,
    )
    if video is None:
        raise MediaError("no_video_stream", "The file contains no video stream.")

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaError("no_dimensions", "The video stream reports no frame size.")

    duration = _float(video.get("duration")) or _float(fmt.get("duration"))
    if duration is None or duration <= 0:
        raise MediaError("no_duration", "The video's duration could not be determined.")

    rotation = _rotation(video)
    swap = rotation % 180 == 90
    nominal, average = _rate(video.get("r_frame_rate")), _rate(video.get("avg_frame_rate"))
    nb_frames = str(video.get("nb_frames") or "")
    bit_rate = str(video.get("bit_rate") or fmt.get("bit_rate") or "")

    return VideoProbe(
        container=str(fmt.get("format_name", "unknown")),
        codec=str(video.get("codec_name", "unknown")),
        pix_fmt=video.get("pix_fmt"),
        width=width,
        height=height,
        display_width=height if swap else width,
        display_height=width if swap else height,
        rotation_deg=rotation,
        duration_s=round(duration, 3),
        frame_count=int(nb_frames) if nb_frames.isdigit() else None,
        nominal_fps=round(nominal, 3) if nominal else None,
        average_fps=round(average, 3) if average else None,
        # Container-level hint only; `is_variable_frame_rate` on real timestamps decides.
        variable_frame_rate=bool(nominal and average and abs(nominal - average) / nominal > 0.01),
        bit_rate=int(bit_rate) if bit_rate.isdigit() else None,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def probe_video(path: Path) -> VideoProbe:
    out = run_ffprobe(["-print_format", "json", "-show_format", "-show_streams"], path)
    try:
        raw = json.loads(out)
    except json.JSONDecodeError as exc:
        raise MediaError("unreadable", "The media metadata could not be parsed.") from exc
    return parse_probe(raw)


def is_variable_frame_rate(timestamps: list[float], tolerance: float = 0.1) -> bool:
    """True when frame intervals differ by more than `tolerance` of the median interval."""
    intervals = sorted(b - a for a, b in itertools.pairwise(timestamps))
    if len(intervals) < 2:
        return False
    median = intervals[len(intervals) // 2]
    return median > 0 and (intervals[-1] - intervals[0]) > tolerance * median


def frame_timestamps(path: Path) -> list[float]:
    """Presentation timestamps of the first video stream's packets, sorted, relative to the
    first frame. Reads packets only (no decoding), so it is fast even for long clips."""
    out = run_ffprobe(
        ["-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0"],
        path,
        timeout=300,
    )
    times = sorted(
        t for t in (_float(line.strip().rstrip(",")) for line in out.splitlines()) if t is not None
    )
    if not times:
        return []
    start = times[0]
    return [round(t - start, 6) for t in times]
