import type { AltitudeKind, TelemetrySummary } from '@nazar/contracts';

export const TELEMETRY_EXTENSIONS = ['.srt', '.csv'];
export const TELEMETRY_MAX_BYTES = 20 * 1024 * 1024;

const ALTITUDE_TEXT: Record<AltitudeKind, string> = {
  relative_to_takeoff: 'altitude above take-off',
  absolute_unspecified_datum: 'altitude, datum not stated',
  none: 'no altitude',
};

export function altitudeText(kind: AltitudeKind): string {
  return ALTITUDE_TEXT[kind];
}

export function coverageText(s: Pick<TelemetrySummary, 'video_coverage' | 'gaps'>): string {
  const gaps = s.gaps.length ? `, ${s.gaps.length} gap${s.gaps.length > 1 ? 's' : ''}` : '';
  if (s.video_coverage === null) {
    return `video coverage known once the video is validated${gaps}`;
  }
  return `covers ${Math.round(s.video_coverage * 100)}% of the video${gaps}`;
}
