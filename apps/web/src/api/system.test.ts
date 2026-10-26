import type { HealthResponse, ReadinessResponse } from '@nazar/contracts';
import { describe, expect, it } from 'vitest';
import { blockingChecks, summarizeStatus } from './system';

const health: HealthResponse = {
  status: 'ok',
  service: 'nazar-api',
  version: '0.1.0',
  environment: 'test',
  time: '2026-10-26T00:00:00Z',
};

const readiness = (ready: boolean): ReadinessResponse => ({
  ready,
  checks: [
    { name: 'database', status: 'ok', detail: 'ok', required: true },
    {
      name: 'config:NAZAR_SECRET_KEY',
      status: ready ? 'ok' : 'not_configured',
      detail: '',
      required: true,
    },
    { name: 'gpu', status: 'not_implemented', detail: '', required: false },
  ],
});

describe('summarizeStatus', () => {
  it('is ready only when the API says so', () => {
    expect(summarizeStatus(health, readiness(true)).state).toBe('ready');
    expect(summarizeStatus(health, readiness(false)).state).toBe('not-ready');
  });

  it('lists only required failing checks as blocking', () => {
    expect(blockingChecks(readiness(false)).map((c) => c.name)).toEqual([
      'config:NAZAR_SECRET_KEY',
    ]);
  });
});
