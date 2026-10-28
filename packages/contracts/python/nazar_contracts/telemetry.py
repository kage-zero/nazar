"""Optional flight telemetry attached to a mission: what was accepted, and how good it is."""

from enum import StrEnum

from pydantic import BaseModel, Field


class AltitudeKind(StrEnum):
    """Altitudes keep their meaning: height above take-off is not sea-level or ellipsoidal."""

    RELATIVE = "relative_to_takeoff"
    ABSOLUTE_UNSPECIFIED = "absolute_unspecified_datum"
    NONE = "none"


class TimeGap(BaseModel):
    start_s: float
    end_s: float


class TelemetrySummary(BaseModel):
    """Computed from the normalised track. Times are seconds since the video started."""

    format: str = Field(description="dji_srt, airdata_csv or csv.")
    samples: int
    start_s: float
    end_s: float
    rate_hz: float = Field(description="Median sample rate.")
    altitude_kind: AltitudeKind
    horizontal_extent_m: float = Field(
        description="Largest horizontal distance from the first position (via WGS84 ENU)."
    )
    height_range_m: float | None
    gaps: list[TimeGap] = Field(description="Pauses longer than 1.5 s; never interpolated.")
    dropped: dict[str, int] = Field(description="Rejected samples by reason.")
    video_duration_s: float | None = Field(
        description="From the video's preflight; null until the video is validated."
    )
    video_coverage: float | None = Field(
        description="Fraction of the video's duration covered by samples outside gaps."
    )
    findings: list[str] = Field(description="Plain-language notes on limits of this telemetry.")
