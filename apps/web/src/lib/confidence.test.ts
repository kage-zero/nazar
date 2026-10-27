import { Color } from 'three';
import { describe, expect, it } from 'vitest';
import { confidenceColors, countConfidence } from './confidence';

describe('confidence classes', () => {
  it('counts each class and ignores unknown codes', () => {
    expect(countConfidence(Uint8Array.from([1, 2, 2, 3, 0, 9]))).toEqual({
      observed: 1,
      estimated: 2,
      inferred: 1,
    });
  });

  it('colours points by class in the renderer working colour space', () => {
    const colors = confidenceColors(Uint8Array.from([1, 2]));
    expect(colors).toHaveLength(6);
    const observed = new Color().setRGB(colors[0] ?? 0, colors[1] ?? 0, colors[2] ?? 0);
    const estimated = new Color().setRGB(colors[3] ?? 0, colors[4] ?? 0, colors[5] ?? 0);
    expect(observed.getHexString()).toBe('3987e5');
    expect(estimated.getHexString()).toBe('d95926');
  });
});
