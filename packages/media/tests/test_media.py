import itertools
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from nazar_contracts import FrameFlag, KeyframeReason, PreflightReport
from nazar_media import Cancelled, KeyframeSettings, MediaError, run_preflight
from nazar_media.analyze import FrameMetrics, analysis_size, decorrelation, signature
from nazar_media.keyframes import frame_flags, quality_scores, select_keyframes
from nazar_media.probe import is_variable_frame_rate, parse_probe

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE1 = REPO_ROOT / "docs/sample/video/sample1.mp4"
SAMPLE2 = REPO_ROOT / "docs/sample/video/sample2.mp4"
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg not installed",
)


def video_stream(**extra: object) -> dict[str, object]:
    return {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "duration": "10.0",
        **extra,
    }


def test_probe_swaps_display_size_for_rotated_video() -> None:
    probe = parse_probe(
        {
            "streams": [video_stream(side_data_list=[{"rotation": -90}])],
            "format": {"format_name": "mov,mp4"},
        }
    )
    assert probe.rotation_deg == 270
    assert (probe.display_width, probe.display_height) == (1080, 1920)


def test_variable_frame_rate_comes_from_real_timestamps() -> None:
    assert is_variable_frame_rate([i / 30 for i in range(100)]) is False
    assert is_variable_frame_rate([0.0, 0.033, 0.066, 0.133, 0.166, 0.2, 0.3, 0.333]) is True
    hinted = parse_probe({"streams": [video_stream(avg_frame_rate="24/1")], "format": {}})
    assert hinted.variable_frame_rate is True


def test_probe_rejects_files_without_video() -> None:
    with pytest.raises(MediaError) as err:
        parse_probe({"streams": [{"codec_type": "audio"}], "format": {"duration": "3"}})
    assert err.value.code == "no_video_stream"


def test_analysis_size_keeps_aspect_and_even_dimensions() -> None:
    assert analysis_size(1920, 1080) == (320, 180)
    assert analysis_size(288, 360) == (256, 320)
    assert analysis_size(100, 60) == (100, 60)


def test_decorrelation_ignores_brightness_and_grows_with_shift() -> None:
    rng = np.random.default_rng(0)
    scene = rng.random((200, 400)).astype(np.float32) * 255
    scene = np.cumsum(np.cumsum(scene, axis=0), axis=1)  # smooth, image-like structure
    base = scene[:180, :320]
    assert decorrelation(signature(base), signature(base * 0.5 + 20)) < 0.01
    small = decorrelation(signature(base), signature(scene[:180, 10:330]))
    large = decorrelation(signature(base), signature(scene[:180, 60:380]))
    assert 0 < small < large


def synthetic_metrics(n: int, drift: float) -> FrameMetrics:
    """`n` frames whose view drifts steadily: frame i's signature moves away from frame 0."""
    rng = np.random.default_rng(1)
    a, b = rng.standard_normal(256), rng.standard_normal(256)
    m = FrameMetrics()
    for i in range(n):
        v = np.cos(drift * i) * a + np.sin(drift * i) * b
        v = (v - v.mean()) / v.std()
        m.signatures.append(v.astype(np.float16))
        m.sharpness.append(100.0)
        m.brightness.append(0.5)
        m.dark_fraction.append(0.0)
        m.bright_fraction.append(0.0)
        m.change.append(0.0 if i == 0 else 0.01)
        m.motion_px.append(1.0)
    return m


def test_keyframes_skip_blurry_frames_and_respect_max_gap() -> None:
    settings = KeyframeSettings()
    m = synthetic_metrics(300, drift=0.0)  # static view: only max-gap keyframes
    m.sharpness[0] = 1.0  # blurry first frame must not start the sequence
    t = [i / 30 for i in range(300)]
    flags = frame_flags(m, settings)
    assert flags[0] == [FrameFlag.BLURRY]
    keys = select_keyframes(t, m, quality_scores(m, flags), settings)
    assert keys[0].index == 1 and keys[0].reason is KeyframeReason.START
    gaps = [b.t - a.t for a, b in itertools.pairwise(keys)]
    assert all(g <= settings.max_gap_s + settings.lookahead_s + 1e-9 for g in gaps)
    assert {k.reason for k in keys[1:-1]} == {KeyframeReason.MAX_GAP}
    assert [k.image for k in keys] == list(range(1, len(keys) + 1))


def test_keyframes_follow_viewpoint_change() -> None:
    settings = KeyframeSettings()
    m = synthetic_metrics(300, drift=0.02)
    t = [i / 30 for i in range(300)]
    keys = select_keyframes(t, m, quality_scores(m, frame_flags(m, settings)), settings)
    assert sum(k.reason is KeyframeReason.NOVELTY for k in keys) > len(keys) // 2
    assert all(b.index > a.index for a, b in itertools.pairwise(keys))


def test_keyframe_count_is_capped() -> None:
    settings = KeyframeSettings(max_keyframes=10)
    m = synthetic_metrics(600, drift=0.05)
    t = [i / 30 for i in range(600)]
    keys = select_keyframes(t, m, quality_scores(m, frame_flags(m, settings)), settings)
    assert 2 <= len(keys) <= 10


def test_duplicates_are_flagged() -> None:
    m = synthetic_metrics(5, drift=0.0)
    m.change[3], m.motion_px[3] = 0.0, 0.0
    flags = frame_flags(m, KeyframeSettings())
    assert FrameFlag.DUPLICATE in flags[3]
    assert FrameFlag.DUPLICATE not in flags[0]


@needs_ffmpeg
def test_preflight_on_provided_sample_video(tmp_path: Path) -> None:
    report = run_preflight(SAMPLE1, tmp_path, asset_id="a1", source_sha256="x", max_duration_s=900)
    assert report.probe.codec == "h264"
    assert (report.probe.display_width, report.probe.display_height) == (640, 360)
    assert report.analysis.frames_decoded == 567
    assert report.analysis.timestamps == "stream"
    assert report.analysis.decode_errors == 0
    assert len(report.series.t) == 567 and report.series.t[0] == 0.0
    assert all(b > a for a, b in itertools.pairwise(report.series.t))
    assert 8 <= len(report.keyframes) <= 96
    assert len(list((tmp_path / "keyframes").glob("*.jpg"))) == len(report.keyframes)
    assert len(list((tmp_path / "thumbs").glob("*.jpg"))) == len(report.keyframes)
    codes = {w.code for w in report.warnings}
    assert "no_telemetry" in codes and "low_resolution" in codes
    assert "low_viewpoint_change" not in codes  # sample1 is an orbit: real parallax
    stored = PreflightReport.model_validate(json.loads((tmp_path / "preflight.json").read_text()))
    assert stored.keyframes == report.keyframes


@needs_ffmpeg
def test_preflight_portrait_sample_uses_stream_timestamps(tmp_path: Path) -> None:
    report = run_preflight(SAMPLE2, tmp_path, asset_id="a2", source_sha256="x", max_duration_s=900)
    # The container average (29.97 fps) differs from 30/1, yet every interval is 1/30 s.
    assert report.probe.variable_frame_rate is False
    assert (report.probe.display_width, report.probe.display_height) == (288, 360)
    assert report.analysis.timestamps == "stream"
    assert abs(report.series.t[-1] - report.probe.duration_s) < 0.1


@needs_ffmpeg
def test_preflight_rejects_non_video_and_too_long(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"definitely not a video" * 100)
    with pytest.raises(MediaError) as err:
        run_preflight(fake, tmp_path / "o1", asset_id="x", source_sha256="x", max_duration_s=900)
    assert err.value.code == "unreadable"

    audio = tmp_path / "audio.m4a"
    subprocess.run(  # noqa: S603
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            str(audio),
        ],
        check=True,
    )
    with pytest.raises(MediaError) as err:
        run_preflight(audio, tmp_path / "o2", asset_id="x", source_sha256="x", max_duration_s=900)
    assert err.value.code == "no_video_stream"

    with pytest.raises(MediaError) as err:
        run_preflight(SAMPLE1, tmp_path / "o3", asset_id="x", source_sha256="x", max_duration_s=5)
    assert err.value.code == "too_long"


@needs_ffmpeg
def test_preflight_can_be_cancelled(tmp_path: Path) -> None:
    with pytest.raises(Cancelled):
        run_preflight(
            SAMPLE1,
            tmp_path,
            asset_id="x",
            source_sha256="x",
            max_duration_s=900,
            should_cancel=lambda: True,
        )
    assert not (tmp_path / "preflight.json").exists()
