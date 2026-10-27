import { describe, expect, it } from 'vitest';
import { addPick, distance, distanceText } from './measure';

describe('measure', () => {
  it('computes Euclidean distance', () => {
    expect(distance([0, 0, 0], [3, 4, 12])).toBe(13);
  });

  it('labels unknown-scale distances as relative, never metres', () => {
    expect(distanceText(4.321, 'unknown')).toBe('4.32 units (relative; scale unknown)');
    expect(distanceText(12.34, undefined)).toBe('12.3 units (relative; scale unknown)');
    expect(distanceText(2, 'metric_estimated')).toBe('2.00 m (estimated scale)');
  });

  it('keeps at most two picks and restarts on the third', () => {
    let picks = addPick([], [0, 0, 0]);
    picks = addPick(picks, [1, 0, 0]);
    expect(picks).toHaveLength(2);
    expect(addPick(picks, [5, 5, 5])).toEqual([[5, 5, 5]]);
  });
});
