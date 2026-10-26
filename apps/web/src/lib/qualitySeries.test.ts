import type { FrameFlag, FrameSeries } from '@nazar/contracts';
import { describe, expect, it } from 'vitest';
import { flaggedRuns, nearestIndex, qualityPoints } from './qualitySeries';

function series(sharpness: number[], flagged: number[] = []): FrameSeries {
  const n = sharpness.length;
  return {
    index: sharpness.map((_, i) => i),
    t: sharpness.map((_, i) => i / 10),
    sharpness,
    brightness: Array<number>(n).fill(0.5),
    change: Array<number>(n).fill(0.01),
    motion_px: Array<number>(n).fill(1),
    flags: sharpness.map((_, i): FrameFlag[] => (flagged.includes(i) ? ['blurry'] : [])),
  };
}

describe('qualityPoints', () => {
  it('keeps every frame when under the limit, relative to the median', () => {
    const points = qualityPoints(series([50, 100, 200]), 100);
    expect(points.map((p) => p.rel)).toEqual([0.5, 1, 2]);
  });

  it('downsamples but keeps blur dips and flags', () => {
    const values = Array<number>(1000).fill(100);
    values[537] = 5;
    const points = qualityPoints(series(values, [537]), 100, 100);
    expect(points).toHaveLength(100);
    expect(Math.min(...points.map((p) => p.rel))).toBe(0.05);
    expect(points.filter((p) => p.flags.length > 0)).toHaveLength(1);
  });
});

describe('flaggedRuns', () => {
  it('merges consecutive flagged points and closes a run at the end', () => {
    const points = qualityPoints(series([1, 1, 1, 1, 1, 1], [1, 2, 5]), 1);
    expect(flaggedRuns(points, 0.6)).toEqual([
      { start: 0.1, end: 0.3 },
      { start: 0.5, end: 0.6 },
    ]);
  });
});

describe('nearestIndex', () => {
  it('finds the closest time', () => {
    const points = qualityPoints(series([1, 1, 1, 1]), 1);
    expect(nearestIndex(points, 0.14)).toBe(1);
    expect(nearestIndex(points, 0.16)).toBe(2);
    expect(nearestIndex(points, 9)).toBe(3);
  });
});
