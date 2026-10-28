"""Sensor alignment: fit the reconstructed camera path to GNSS telemetry with a similarity
transform (scale, rotation, translation), and accept it only when the evidence supports it.

The reconstruction's camera centres are in a local, unitless frame. Telemetry positions are
converted to east-north-up (ENU) metres around the first fix (never lat/lon as metres). A
Umeyama fit maps local -> ENU. Two separate claims can be accepted:

- **scale** (metres per local unit) needs enough matched keyframes, a baseline that dwarfs
  GNSS noise, and a low residual;
- **orientation** (an ENU georeference) additionally needs altitude and a path that is not a
  straight line, since rotation about a line is undetermined.

A rejected claim leaves the job in its local frame, with the reason recorded.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from nazar_contracts import AltitudeKind
from nazar_media.telemetry import Track, sample_at
from nazar_worker.utm import enu_to_utm

MIN_MATCHED = 5
MIN_COVERAGE = 0.5
MIN_BASELINE_M = 20.0
"""Consumer GNSS is good to a few metres; a shorter path gives a scale dominated by noise."""
MAX_RMS_FLOOR_M = 3.0
MAX_RMS_REL = 0.05
MIN_PLANARITY = 0.15
"""Second / first singular value of the matched ENU path; below this it is close to a line."""
OFFSET_SEARCH_S = 2.0
OFFSET_STEP_S = 0.1
OFFSET_MIN_GAIN_M = 0.05


@dataclass
class Alignment:
    scale_accepted: bool
    orientation_accepted: bool
    reasons: list[str] = field(default_factory=list)
    """Why a claim was rejected (empty when both were accepted)."""
    metres_per_unit: float | None = None
    rotation: npt.NDArray[np.float64] | None = None
    translation: npt.NDArray[np.float64] | None = None
    time_offset_s: float = 0.0
    matched: int = 0
    used: int = 0
    placed: int = 0
    residual_rms_m: float | None = None
    baseline_m: float | None = None
    planarity: float | None = None
    scale_uncertainty_rel: float | None = None

    origin: tuple[float, float, float] | None = None
    """ENU origin: latitude, longitude (deg) and height (m, the track's altitude kind)."""

    def to_enu(self, xyz: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        assert self.metres_per_unit and self.rotation is not None and self.translation is not None
        return np.asarray(self.metres_per_unit * xyz @ self.rotation.T + self.translation)

    def to_utm(self, xyz: npt.NDArray[np.float64]) -> tuple[npt.NDArray[np.float64], int]:
        """Local points -> UTM easting, northing, height (zone of the ENU origin) + EPSG."""
        assert self.orientation_accepted and self.origin is not None
        return enu_to_utm(self.to_enu(xyz), *self.origin)

    def report(self) -> dict[str, Any]:
        def r(v: float | None, n: int = 3) -> float | None:
            return None if v is None else round(float(v), n)

        return {
            "scale_accepted": self.scale_accepted,
            "orientation_accepted": self.orientation_accepted,
            "rejected_because": self.reasons,
            "metres_per_unit": r(self.metres_per_unit, 5),
            "time_offset_s": r(self.time_offset_s, 2),
            "keyframes_placed": self.placed,
            "keyframes_with_position": self.matched,
            "keyframes_used": self.used,
            "residual_rms_m": r(self.residual_rms_m, 2),
            "baseline_m": r(self.baseline_m, 1),
            "planarity": r(self.planarity),
            "scale_uncertainty_rel_approx": r(self.scale_uncertainty_rel, 4),
            "thresholds": {
                "min_matched_keyframes": MIN_MATCHED,
                "min_coverage": MIN_COVERAGE,
                "min_baseline_m": MIN_BASELINE_M,
                "max_residual_rms_m": f"max({MAX_RMS_FLOOR_M}, {MAX_RMS_REL} x baseline)",
                "min_planarity_for_orientation": MIN_PLANARITY,
            },
        }


def umeyama(
    src: npt.NDArray[np.float64], dst: npt.NDArray[np.float64]
) -> tuple[float, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Least-squares s, R, t with dst ~ s R src + t (Umeyama 1991), R a proper rotation."""
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    a, b = src - mu_s, dst - mu_d
    var_s = float((a**2).sum() / len(src))
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    sign = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2, 2] = -1
    rot = u @ sign @ vt
    s = float(np.trace(np.diag(d) @ sign) / var_s) if var_s > 0 else 0.0
    return s, rot, mu_d - s * rot @ mu_s


def _fit(
    src: npt.NDArray[np.float64], dst: npt.NDArray[np.float64]
) -> tuple[float, npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Fit, drop gross outliers (GNSS glitches, bad poses) once, refit."""
    s, rot, t = umeyama(src, dst)
    res = np.linalg.norm(dst - (s * src @ rot.T + t), axis=1)
    inl = res <= max(3 * float(np.median(res)), 1.0)
    if inl.sum() >= MIN_MATCHED and not inl.all():
        s, rot, t = umeyama(src[inl], dst[inl])
    else:
        inl = np.ones(len(src), dtype=bool)
    return s, rot, t, inl


def align(
    centres: npt.NDArray[np.float64], times: npt.NDArray[np.float64], track: Track
) -> Alignment:
    """`centres[i]` is the local camera centre of the keyframe at video time `times[i]`."""
    out = Alignment(scale_accepted=False, orientation_accepted=False, placed=len(centres))
    if track.altitude_kind is AltitudeKind.NONE:
        out.reasons.append("The telemetry has no altitude, so a 3D alignment is not possible.")
        return out
    best: tuple[float, float] | None = None  # (rms, offset)
    steps = round(OFFSET_SEARCH_S / OFFSET_STEP_S)
    for offset in np.round(np.arange(-steps, steps + 1) * OFFSET_STEP_S, 3):
        enu = sample_at(track, times + offset)
        ok = np.isfinite(enu).all(axis=1)
        if ok.sum() < MIN_MATCHED:
            continue
        s, rot, t, inl = _fit(centres[ok], enu[ok])
        res = enu[ok][inl] - (s * centres[ok][inl] @ rot.T + t)
        rms = float(np.sqrt((res**2).sum(axis=1).mean()))
        # Prefer zero offset unless another is clearly better (5 % and 5 cm): on a
        # constant-speed orbit a time shift equals a rotation, so offsets fit equally well and
        # picking one by float noise would rotate the whole georeference.
        score = rms if abs(offset) < 1e-9 else rms * 1.05 + OFFSET_MIN_GAIN_M
        if best is None or score < best[0]:
            best = (score, float(offset))
    if best is None:
        out.reasons.append(
            f"Fewer than {MIN_MATCHED} keyframes fall inside the telemetry's time span "
            "(outside gaps)."
        )
        return out
    offset = best[1]
    enu = sample_at(track, times + offset)
    ok = np.isfinite(enu).all(axis=1)
    src, dst = centres[ok], enu[ok]
    s, rot, t, inl = _fit(src, dst)
    res = dst[inl] - (s * src[inl] @ rot.T + t)
    rms = float(np.sqrt((res**2).sum(axis=1).mean()))
    centred = dst[inl] - dst[inl].mean(axis=0)
    sv = np.linalg.svd(centred, compute_uv=False)
    spread = float(np.sqrt((centred**2).sum(axis=1).mean()))
    baseline = float(np.max(np.linalg.norm(dst[inl][:, None] - dst[inl][None], axis=2)))
    out.time_offset_s = offset
    out.matched, out.used = int(ok.sum()), int(inl.sum())
    out.residual_rms_m, out.baseline_m = rms, baseline
    out.planarity = float(sv[1] / sv[0]) if sv[0] > 0 else 0.0
    out.scale_uncertainty_rel = rms / spread / np.sqrt(out.used) if spread > 0 else None

    max_rms = max(MAX_RMS_FLOOR_M, MAX_RMS_REL * baseline)
    if out.matched / max(out.placed, 1) < MIN_COVERAGE:
        out.reasons.append(
            f"Only {out.matched} of {out.placed} placed keyframes have a telemetry position."
        )
    if baseline < MIN_BASELINE_M:
        out.reasons.append(
            f"The flight path spans {baseline:.1f} m; at least {MIN_BASELINE_M:.0f} m is needed "
            "for GNSS noise not to dominate the scale."
        )
    if rms > max_rms:
        out.reasons.append(
            f"The camera path does not match the telemetry: residual {rms:.1f} m RMS exceeds "
            f"{max_rms:.1f} m. Check that the telemetry belongs to this video."
        )
    if not s > 0:
        out.reasons.append("Degenerate camera path (all keyframes at one place).")
    if out.reasons:
        return out
    out.scale_accepted = True
    out.metres_per_unit = s
    if out.planarity < MIN_PLANARITY:
        out.reasons.append(
            "The flight path is close to a straight line, so the rotation about it is "
            "undetermined: scale is accepted, georeferencing is not."
        )
        return out
    out.orientation_accepted = True
    out.rotation, out.translation = rot, t
    out.origin = (float(track.lat[0]), float(track.lon[0]), float(track.alt[0]))
    return out
