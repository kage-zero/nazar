"""Frame flags and keyframe selection.

Keyframes are chosen from quality + temporal spacing + viewpoint change, not at a fixed
rate: once a frame's appearance has decorrelated from the last keyframe by `novelty`
(see `analyze.decorrelation`; it rises for orbits, pans and forward flight alike), the
sharpest eligible frame in a short look-ahead window becomes the next keyframe.
`max_gap_s` forces a keyframe during slow segments so coverage has no long holes;
`min_gap_s` stops bursts during fast motion.
These are heuristics; the thresholds are recorded in every preflight report.
"""

import statistics
from dataclasses import asdict, dataclass

from nazar_contracts import FrameFlag, Keyframe, KeyframeReason
from nazar_media.analyze import FrameMetrics, decorrelation


@dataclass(frozen=True)
class KeyframeSettings:
    blur_relative: float = 0.4
    dark_brightness: float = 0.12
    dark_fraction: float = 0.6
    bright_brightness: float = 0.9
    bright_fraction: float = 0.5
    duplicate_change: float = 0.0015
    duplicate_motion_px: float = 0.5
    novelty: float = 0.035
    min_gap_s: float = 0.15
    max_gap_s: float = 1.0
    lookahead_s: float = 0.3
    max_keyframes: int = 96

    def as_dict(self) -> dict[str, float | int | str]:
        return dict(asdict(self))


def frame_flags(m: FrameMetrics, s: KeyframeSettings) -> list[list[FrameFlag]]:
    median = statistics.median(m.sharpness) if len(m) else 0.0
    flags: list[list[FrameFlag]] = []
    for i in range(len(m)):
        f: list[FrameFlag] = []
        if median > 0 and m.sharpness[i] < s.blur_relative * median:
            f.append(FrameFlag.BLURRY)
        if m.brightness[i] < s.dark_brightness or m.dark_fraction[i] > s.dark_fraction:
            f.append(FrameFlag.DARK)
        if m.brightness[i] > s.bright_brightness or m.bright_fraction[i] > s.bright_fraction:
            f.append(FrameFlag.OVEREXPOSED)
        if i > 0 and m.change[i] < s.duplicate_change and m.motion_px[i] < s.duplicate_motion_px:
            f.append(FrameFlag.DUPLICATE)
        flags.append(f)
    return flags


def quality_scores(m: FrameMetrics, flags: list[list[FrameFlag]]) -> list[float]:
    """0 for flagged frames, otherwise relative sharpness capped at 1."""
    median = statistics.median(m.sharpness) if len(m) else 0.0
    return [
        0.0 if flags[i] or median <= 0 else round(min(1.0, m.sharpness[i] / (1.5 * median)), 4)
        for i in range(len(m))
    ]


def _select(
    t: list[float],
    m: FrameMetrics,
    quality: list[float],
    s: KeyframeSettings,
    novelty: float,
) -> list[tuple[int, KeyframeReason]]:
    n = len(t)
    eligible = [q > 0 for q in quality]
    first = next((i for i in range(n) if eligible[i]), None)
    if first is None:
        return []
    keys: list[tuple[int, KeyframeReason]] = [(first, KeyframeReason.START)]
    last, i = first, first + 1
    while i < n:
        since = t[i] - t[last]
        reason: KeyframeReason | None = None
        if since >= s.min_gap_s and decorrelation(m.signatures[last], m.signatures[i]) >= novelty:
            reason = KeyframeReason.NOVELTY
        elif since >= s.max_gap_s:
            reason = KeyframeReason.MAX_GAP
        if reason is None:
            i += 1
            continue
        window = [j for j in range(i, n) if t[j] - t[i] <= s.lookahead_s and eligible[j]]
        if not window:
            i += 1
            continue
        last = max(window, key=lambda j: quality[j])
        keys.append((last, reason))
        i = last + 1
    end = next((j for j in range(n - 1, -1, -1) if eligible[j]), None)
    if end is not None and end != last and t[end] - t[last] >= s.min_gap_s:
        keys.append((end, KeyframeReason.END))
    return keys


def select_keyframes(
    t: list[float],
    m: FrameMetrics,
    quality: list[float],
    s: KeyframeSettings,
) -> list[Keyframe]:
    novelty = s.novelty
    picks = _select(t, m, quality, s, novelty)
    for _ in range(6):
        if len(picks) <= s.max_keyframes:
            break
        novelty *= len(picks) / s.max_keyframes * 1.05
        picks = _select(t, m, quality, s, novelty)
    if len(picks) > s.max_keyframes:
        step = len(picks) / s.max_keyframes
        picks = [picks[int(k * step)] for k in range(s.max_keyframes)]
    return [
        Keyframe(index=i, t=round(t[i], 4), reason=reason, quality=quality[i], image=n + 1)
        for n, (i, reason) in enumerate(picks)
    ]


def viewpoint_change(m: FrameMetrics, step: float = 0.05) -> float:
    """Sum of decorrelation along an anchor chain (re-anchoring every `step`), so slow drift
    and fast motion are both counted without accumulating per-frame noise."""
    if len(m) < 2:
        return 0.0
    anchor, total = 0, 0.0
    for i in range(1, len(m)):
        d = decorrelation(m.signatures[anchor], m.signatures[i])
        if d >= step:
            total += d
            anchor = i
    return round(total, 3)
