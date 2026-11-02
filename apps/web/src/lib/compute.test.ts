import { describe, expect, it } from 'vitest';
import { presenceText } from './compute';

describe('compute presence text', () => {
  it('says how to bring an offline worker online', () => {
    expect(presenceText('college', undefined)).toContain('College GPU worker: offline');
    expect(
      presenceText('local', { location: 'local', online: false, last_seen_s: 300, geometry: null }),
    ).toContain('pnpm worker');
  });

  it('names the method an online worker will use', () => {
    expect(
      presenceText('college', {
        location: 'college',
        online: true,
        last_seen_s: 2,
        geometry: 'fast3r',
      }),
    ).toBe('College GPU worker: online · Fast3R on its GPU.');
    expect(
      presenceText('local', {
        location: 'local',
        online: true,
        last_seen_s: 2,
        geometry: 'cpu-baseline',
      }),
    ).toContain('CPU baseline');
  });
});
