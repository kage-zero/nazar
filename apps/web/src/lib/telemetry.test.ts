import { describe, expect, it } from 'vitest';
import { altitudeText, coverageText } from './telemetry';

describe('telemetry text', () => {
  it('never presents relative altitude as absolute', () => {
    expect(altitudeText('relative_to_takeoff')).toBe('altitude above take-off');
    expect(altitudeText('absolute_unspecified_datum')).toContain('datum not stated');
  });

  it('describes coverage and gaps', () => {
    expect(coverageText({ video_coverage: 0.874, gaps: [] })).toBe('covers 87% of the video');
    expect(coverageText({ video_coverage: null, gaps: [{ start_s: 1, end_s: 4 }] })).toBe(
      'video coverage known once the video is validated, 1 gap',
    );
  });
});
