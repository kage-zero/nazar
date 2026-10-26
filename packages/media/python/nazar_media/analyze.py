"""Decode every frame at a small analysis resolution and measure per-frame quality.

FFmpeg decodes (and applies container rotation); frames are piped as 8-bit grayscale and
measured with NumPy. Only scalar metrics are kept, so memory stays bounded for long clips.
"""

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

from nazar_media.ffmpeg import Cancelled, MediaError, tool

ANALYSIS_LONG_SIDE = 320
SIGNATURE_LONG_SIDE = 48

Gray = npt.NDArray[np.float32]
ProgressFn = Callable[[int], None]
CancelFn = Callable[[], bool]


def analysis_size(display_width: int, display_height: int) -> tuple[int, int]:
    """Scale so the long side is at most ANALYSIS_LONG_SIDE; keep aspect; even dimensions."""
    long_side = max(display_width, display_height)
    scale = min(1.0, ANALYSIS_LONG_SIDE / long_side)

    def even(v: float) -> int:
        return max(2, round(v * scale / 2) * 2)

    return even(display_width), even(display_height)


@dataclass
class FrameMetrics:
    sharpness: list[float] = field(default_factory=list)
    brightness: list[float] = field(default_factory=list)
    dark_fraction: list[float] = field(default_factory=list)
    bright_fraction: list[float] = field(default_factory=list)
    change: list[float] = field(default_factory=list)
    motion_px: list[float] = field(default_factory=list)
    signatures: list[npt.NDArray[np.float16]] = field(default_factory=list)
    """Tiny normalised thumbnails (zero mean, unit variance) used for viewpoint novelty."""
    decode_errors: int = 0

    def __len__(self) -> int:
        return len(self.sharpness)


def laplacian_variance(img: Gray) -> float:
    lap = 4 * img[1:-1, 1:-1] - img[:-2, 1:-1] - img[2:, 1:-1] - img[1:-1, :-2] - img[1:-1, 2:]
    return float(lap.var())


def _subpixel(peak: int, axis_len: int, line: npt.NDArray[np.float64]) -> float:
    """Parabolic refinement of a correlation peak along one axis (with wrap-around)."""
    left, centre, right = line[(peak - 1) % axis_len], line[peak], line[(peak + 1) % axis_len]
    denom = left - 2 * centre + right
    offset = 0.5 * (left - right) / denom if abs(denom) > 1e-12 else 0.0
    value = peak + float(np.clip(offset, -0.5, 0.5))
    return value - axis_len if value > axis_len / 2 else value


def area_downsample(img: Gray, width: int, height: int) -> Gray:
    rows = np.linspace(0, img.shape[0], height + 1).astype(int)
    cols = np.linspace(0, img.shape[1], width + 1).astype(int)
    summed = np.add.reduceat(np.add.reduceat(img, rows[:-1], axis=0), cols[:-1], axis=1)
    counts = np.outer(np.diff(rows), np.diff(cols))
    out: Gray = (summed / counts).astype(np.float32)
    return out


def signature(img: Gray) -> npt.NDArray[np.float16]:
    h, w = img.shape
    scale = SIGNATURE_LONG_SIDE / max(h, w)
    small = area_downsample(img, max(2, round(w * scale)), max(2, round(h * scale)))
    small -= small.mean()
    small /= small.std() + 1e-6
    return small.ravel().astype(np.float16)


def decorrelation(a: npt.NDArray[np.float16], b: npt.NDArray[np.float16]) -> float:
    """1 - normalised cross-correlation of two signatures: 0 = identical view, grows as the
    viewpoint changes (translation, orbit, zoom). Global brightness changes cancel out."""
    return 1.0 - float(np.dot(a.astype(np.float32), b.astype(np.float32))) / a.size


class PhaseCorrelator:
    """Global image translation per frame via phase correlation.

    Consecutive drone frames often move by less than one analysis pixel, so each frame is
    correlated against an *anchor* frame (sub-pixel peak), and the per-frame motion is the
    change of that displacement. The anchor is renewed once the displacement grows large,
    keeping the overlap high enough for a reliable peak.
    """

    def __init__(self, height: int, width: int, reanchor_fraction: float = 0.06) -> None:
        self._window = np.outer(np.hanning(height), np.hanning(width)).astype(np.float32)
        self._shape = (height, width)
        self._reanchor_px = reanchor_fraction * max(height, width)
        self._anchor: npt.NDArray[np.complex128] | None = None
        self._last = np.zeros(2)

    def _displacement(self, spectrum: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
        assert self._anchor is not None
        cross = spectrum * np.conj(self._anchor)
        cross /= np.abs(cross) + 1e-9
        corr: npt.NDArray[np.float64] = np.fft.irfft2(cross, s=self._shape)
        h, w = self._shape
        py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
        dy = _subpixel(int(py), h, corr[:, px])
        dx = _subpixel(int(px), w, corr[py, :])
        return np.array([dy, dx])

    def shift(self, img: Gray) -> float:
        spectrum = np.fft.rfft2((img - img.mean()) * self._window)
        if self._anchor is None:
            self._anchor = spectrum
            return 0.0
        disp = self._displacement(spectrum)
        motion = float(np.hypot(*(disp - self._last)))
        self._last = disp
        if np.hypot(*disp) >= self._reanchor_px:
            self._anchor, self._last = spectrum, np.zeros(2)
        return motion


def measure_frames(
    frames: "Callable[[], Gray | None]",
    size: tuple[int, int],
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> FrameMetrics:
    width, height = size
    metrics = FrameMetrics()
    correlator = PhaseCorrelator(height, width)
    prev: Gray | None = None
    while (img := frames()) is not None:
        metrics.sharpness.append(round(laplacian_variance(img), 3))
        metrics.brightness.append(round(float(img.mean()) / 255, 4))
        metrics.dark_fraction.append(round(float((img < 16).mean()), 4))
        metrics.bright_fraction.append(round(float((img > 239).mean()), 4))
        metrics.change.append(
            0.0 if prev is None else round(float(np.abs(img - prev).mean()) / 255, 5)
        )
        metrics.motion_px.append(round(correlator.shift(img), 2))
        metrics.signatures.append(signature(img))
        prev = img
        n = len(metrics)
        if n % 25 == 0:
            if should_cancel and should_cancel():
                raise Cancelled
            if progress:
                progress(n)
    return metrics


def analyze_video(
    path: Path,
    display_size: tuple[int, int],
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> tuple[FrameMetrics, tuple[int, int]]:
    """Decode all frames of the first video stream (display order, no frame dropping or
    duplication) and measure them. Returns the metrics and the analysis size."""
    width, height = analysis_size(*display_size)
    frame_bytes = width * height
    cmd = [
        tool("ffmpeg"),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-fps_mode",
        "passthrough",
        "-vf",
        f"scale={width}:{height}:flags=area,format=gray",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, resolved executable
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert proc.stdout is not None and proc.stderr is not None
    stderr_lines: list[str] = []
    stderr_pipe = proc.stderr

    def drain() -> None:
        for line in stderr_pipe:
            stderr_lines.append(line.decode("utf-8", "replace").strip())

    drainer = threading.Thread(target=drain, daemon=True)
    drainer.start()
    stdout = proc.stdout

    def next_frame() -> Gray | None:
        buf = stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            return None
        return np.frombuffer(buf, dtype=np.uint8).reshape(height, width).astype(np.float32)

    try:
        metrics = measure_frames(next_frame, (width, height), progress, should_cancel)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    proc.wait()
    drainer.join(timeout=5)
    metrics.decode_errors = sum(1 for line in stderr_lines if line)
    if len(metrics) == 0:
        raise MediaError("undecodable", "No video frames could be decoded from this file.")
    return metrics, (width, height)
