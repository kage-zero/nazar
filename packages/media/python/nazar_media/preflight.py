"""Preflight: probe → decode + measure → flags → keyframes → images → report.

Outputs (all inside `out_dir`, written atomically):
- `preflight.json`: the `PreflightReport`.
- `keyframes/NNNN.jpg`: full-resolution keyframes (inputs for the geometry stage).
- `thumbs/NNNN.jpg`: small previews for the UI.
"""

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from nazar_contracts import (
    AnalysisInfo,
    FrameFlag,
    FrameSeries,
    Keyframe,
    PreflightReport,
    PreflightSummary,
    PreflightWarning,
    VideoProbe,
    WarningSeverity,
)
from nazar_media.analyze import analyze_video
from nazar_media.ffmpeg import Cancelled, MediaError, tool
from nazar_media.keyframes import (
    KeyframeSettings,
    frame_flags,
    quality_scores,
    select_keyframes,
    viewpoint_change,
)
from nazar_media.probe import frame_timestamps, is_variable_frame_rate, probe_video

PhaseFn = Callable[[str, int | None, int | None], None]
CancelFn = Callable[[], bool]

THUMB_HEIGHT = 180


def _warn(code: str, severity: WarningSeverity, message: str) -> PreflightWarning:
    return PreflightWarning(code=code, severity=severity, message=message)


def build_warnings(
    probe: VideoProbe,
    summary: PreflightSummary,
    frames: int,
    keyframes: int,
    decode_errors: int,
    estimated_timestamps: bool,
    telemetry_present: bool,
) -> list[PreflightWarning]:
    w: list[PreflightWarning] = []
    W, INFO, B = WarningSeverity.WARNING, WarningSeverity.INFO, WarningSeverity.BLOCKING

    def share(n: int) -> float:
        return n / frames if frames else 0.0

    if keyframes < 2:
        w.append(
            _warn(
                "too_few_keyframes",
                B,
                "Fewer than two usable keyframes were found, so no multi-view geometry is "
                "possible. Use a longer, sharper clip with camera movement.",
            )
        )
    elif keyframes < 8:
        w.append(
            _warn(
                "few_keyframes",
                W,
                f"Only {keyframes} keyframes were selected. Reconstruction may be sparse or "
                "incomplete.",
            )
        )
    if max(probe.display_width, probe.display_height) < 1280:
        w.append(
            _warn(
                "low_resolution",
                W,
                f"Low resolution ({probe.display_width}x{probe.display_height}). Fine detail "
                "and depth accuracy will be limited.",
            )
        )
    if probe.duration_s < 5:
        w.append(_warn("short_clip", W, "The clip is under 5 seconds; coverage will be small."))
    if share(summary.blurry_frames) > 0.25:
        w.append(
            _warn(
                "blur",
                W,
                f"{share(summary.blurry_frames):.0%} of frames look blurry (motion blur or "
                "focus). Blurry frames are excluded from keyframes.",
            )
        )
    exposure = summary.dark_frames + summary.overexposed_frames
    if share(exposure) > 0.15:
        w.append(
            _warn(
                "exposure",
                W,
                f"{share(exposure):.0%} of frames are too dark or overexposed and are excluded.",
            )
        )
    if share(summary.duplicate_frames) > 0.1:
        w.append(
            _warn(
                "repeated_frames",
                W,
                f"{share(summary.duplicate_frames):.0%} of frames repeat the previous frame "
                "(hovering, frozen video or frame duplication).",
            )
        )
    if summary.viewpoint_change < 0.15:
        w.append(
            _warn(
                "low_viewpoint_change",
                W,
                "The camera barely moves across the clip. 3D reconstruction needs parallax "
                "(viewpoint change); expect weak or failed geometry.",
            )
        )
    if decode_errors:
        w.append(
            _warn(
                "decode_errors",
                W,
                f"The decoder reported {decode_errors} error line(s); some frames may be damaged.",
            )
        )
    if probe.variable_frame_rate:
        w.append(
            _warn(
                "variable_frame_rate",
                INFO,
                "Variable frame rate detected. NAZAR uses each frame's own timestamp.",
            )
        )
    if estimated_timestamps:
        w.append(
            _warn(
                "estimated_timestamps",
                W,
                "Frame timestamps could not be read reliably and were estimated from the "
                "average frame rate.",
            )
        )
    if probe.rotation_deg:
        w.append(
            _warn(
                "rotated",
                INFO,
                f"The video carries a {probe.rotation_deg}° rotation; frames are analysed upright.",
            )
        )
    if not telemetry_present:
        w.append(
            _warn(
                "no_telemetry",
                INFO,
                "No telemetry: the reconstruction will be in a local frame with unknown scale, "
                "and global position/metric measurements will be unavailable.",
            )
        )
    return w


def extract_keyframe_images(
    src: Path, keyframes: list[Keyframe], out_dir: Path, timeout: float = 600
) -> None:
    """Write full-resolution keyframes and UI thumbnails, selected by decoded frame index."""
    staging = out_dir / ".images-tmp"
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "keyframes").mkdir(parents=True)
    (staging / "thumbs").mkdir(parents=True)
    expr = "+".join(f"eq(n\\,{k.index})" for k in keyframes)
    graph = (
        f"[0:v:0]select='{expr}',split=2[full][small];"
        f"[small]scale=-2:{THUMB_HEIGHT}:flags=area[thumb]"
    )
    cmd = [
        tool("ffmpeg"),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(src),
        "-filter_complex",
        graph,
        "-map",
        "[full]",
        "-fps_mode",
        "passthrough",
        "-q:v",
        "2",
        str(staging / "keyframes" / "%04d.jpg"),
        "-map",
        "[thumb]",
        "-fps_mode",
        "passthrough",
        "-q:v",
        "5",
        str(staging / "thumbs" / "%04d.jpg"),
    ]
    result = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
        cmd, capture_output=True, timeout=timeout, check=False
    )
    written = len(list((staging / "keyframes").glob("*.jpg")))
    if result.returncode != 0 or written != len(keyframes):
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(
            f"Keyframe extraction wrote {written} of {len(keyframes)} images "
            f"(ffmpeg exit {result.returncode})."
        )
    for name in ("keyframes", "thumbs"):
        target = out_dir / name
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging / name, target)
    shutil.rmtree(staging, ignore_errors=True)


def write_report(report: PreflightReport, out_dir: Path) -> Path:
    path = out_dir / "preflight.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(report.model_dump_json(), encoding="utf-8")
    os.replace(tmp, path)
    return path


def run_preflight(
    src: Path,
    out_dir: Path,
    *,
    asset_id: str,
    source_sha256: str,
    max_duration_s: float,
    telemetry_present: bool = False,
    settings: KeyframeSettings | None = None,
    on_phase: PhaseFn | None = None,
    should_cancel: CancelFn | None = None,
) -> PreflightReport:
    """Validate and analyse a video. Raises `MediaError` when the file must be rejected and
    `Cancelled` if `should_cancel` returns true."""
    settings = settings or KeyframeSettings()
    started = time.monotonic()

    def phase(name: str, done: int | None = None, total: int | None = None) -> None:
        if on_phase:
            on_phase(name, done, total)

    phase("probing")
    probe = probe_video(src)
    if probe.duration_s > max_duration_s:
        raise MediaError(
            "too_long",
            f"The video is {probe.duration_s:.0f} s long; the limit is {max_duration_s:.0f} s.",
        )
    timestamps = frame_timestamps(src)

    expected = probe.frame_count or round(probe.duration_s * (probe.average_fps or 30))
    phase("analyzing", 0, expected)
    metrics, (width, height) = analyze_video(
        src,
        (probe.display_width, probe.display_height),
        progress=lambda n: phase("analyzing", n, max(expected, n)),
        should_cancel=should_cancel,
    )
    frames = len(metrics)
    estimated = len(timestamps) != frames
    if estimated:
        fps = probe.average_fps or probe.nominal_fps or 30.0
        timestamps = [round(i / fps, 6) for i in range(frames)]
    else:
        probe = probe.model_copy(update={"variable_frame_rate": is_variable_frame_rate(timestamps)})

    if should_cancel and should_cancel():
        raise Cancelled
    phase("selecting_keyframes")
    flags = frame_flags(metrics, settings)
    quality = quality_scores(metrics, flags)
    keyframes = select_keyframes(timestamps, metrics, quality, settings)

    def count(flag: FrameFlag) -> int:
        return sum(1 for f in flags if flag in f)

    summary = PreflightSummary(
        usable_frames=sum(1 for f in flags if not f),
        blurry_frames=count(FrameFlag.BLURRY),
        dark_frames=count(FrameFlag.DARK),
        overexposed_frames=count(FrameFlag.OVEREXPOSED),
        duplicate_frames=count(FrameFlag.DUPLICATE),
        median_sharpness=round(sorted(metrics.sharpness)[frames // 2], 3),
        viewpoint_change=viewpoint_change(metrics),
    )
    warnings = build_warnings(
        probe,
        summary,
        frames,
        len(keyframes),
        metrics.decode_errors,
        estimated,
        telemetry_present,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    if keyframes:
        if should_cancel and should_cancel():
            raise Cancelled
        phase("extracting_keyframes", 0, len(keyframes))
        extract_keyframe_images(src, keyframes, out_dir)

    report = PreflightReport(
        asset_id=asset_id,
        source_sha256=source_sha256,
        generated_at=datetime.now(UTC),
        probe=probe,
        analysis=AnalysisInfo(
            width=width,
            height=height,
            frames_decoded=frames,
            decode_errors=metrics.decode_errors,
            timestamps="estimated" if estimated else "stream",
            processing_s=round(time.monotonic() - started, 2),
        ),
        summary=summary,
        keyframes=keyframes,
        warnings=warnings,
        telemetry_present=telemetry_present,
        settings=settings.as_dict(),
        series=FrameSeries(
            index=list(range(frames)),
            t=timestamps,
            sharpness=metrics.sharpness,
            brightness=metrics.brightness,
            change=metrics.change,
            motion_px=metrics.motion_px,
            flags=flags,
        ),
    )
    write_report(report, out_dir)
    return report
