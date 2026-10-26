import { describe, expect, it } from 'vitest';
import { checkVideoFile, formatBytes } from './videoFile';

const MB = 1024 * 1024;

describe('checkVideoFile', () => {
  it('accepts a video by MIME type', () => {
    const result = checkVideoFile({ name: 'pass.mp4', size: 2 * MB, type: 'video/mp4' }, 10 * MB);
    expect(result).toEqual({ ok: true, name: 'pass.mp4', sizeBytes: 2 * MB, type: 'video/mp4' });
  });

  it('accepts a known extension when the browser gives no MIME type', () => {
    expect(checkVideoFile({ name: 'PASS.MOV', size: 1, type: '' }, MB).ok).toBe(true);
  });

  it('rejects non-video files with an actionable message', () => {
    const result = checkVideoFile({ name: 'notes.txt', size: 10, type: 'text/plain' }, MB);
    expect(result.ok).toBe(false);
    expect(!result.ok && result.error).toMatch(/not a video/);
  });

  it('rejects empty and oversized files', () => {
    expect(checkVideoFile({ name: 'a.mp4', size: 0, type: 'video/mp4' }, MB).ok).toBe(false);
    const big = checkVideoFile({ name: 'a.mp4', size: 3 * MB, type: 'video/mp4' }, MB);
    expect(!big.ok && big.error).toMatch(/limit is 1.0 MB/);
  });
});

describe('formatBytes', () => {
  it('formats with binary units', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2093802)).toBe('2.0 MB');
  });
});
