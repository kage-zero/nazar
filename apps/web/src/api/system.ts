import type { HealthResponse, ReadinessResponse } from '@nazar/contracts';

export type ApiStatus =
  | { state: 'checking' }
  | { state: 'offline'; reason: string }
  | { state: 'not-ready'; health: HealthResponse; readiness: ReadinessResponse }
  | { state: 'ready'; health: HealthResponse; readiness: ReadinessResponse };

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return (await response.json()) as T;
}

export function summarizeStatus(health: HealthResponse, readiness: ReadinessResponse): ApiStatus {
  return readiness.ready
    ? { state: 'ready', health, readiness }
    : { state: 'not-ready', health, readiness };
}

/** Liveness first: if /health fails the API is offline regardless of readiness. */
export async function fetchApiStatus(signal: AbortSignal): Promise<ApiStatus> {
  let health: HealthResponse;
  try {
    health = await getJson<HealthResponse>('/api/health', signal);
  } catch (error) {
    if (signal.aborted) throw error;
    return { state: 'offline', reason: 'The API did not respond to /api/health.' };
  }
  try {
    const readiness = await getJson<ReadinessResponse>('/api/ready', signal);
    return summarizeStatus(health, readiness);
  } catch (error) {
    if (signal.aborted) throw error;
    return { state: 'offline', reason: 'The API is up but /api/ready failed.' };
  }
}

export function blockingChecks(readiness: ReadinessResponse) {
  return readiness.checks.filter((c) => c.required && c.status !== 'ok');
}
