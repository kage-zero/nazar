/**
 * Thin JSON client for the NAZAR API. Session auth uses an HttpOnly cookie, so requests
 * only need same-origin credentials; every request carries `X-Nazar-Request`, which the
 * API requires on state-changing calls as its CSRF guard.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
export const REQUEST_HEADER = { 'X-Nazar-Request': '1' } as const;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** FastAPI reports errors as `{detail: string}` or `{detail: [{msg}]}` for validation. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown; loc?: unknown };
      const field = Array.isArray(first.loc) ? String(first.loc.at(-1)) : '';
      if (typeof first.msg === 'string') return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  return fallback;
}

export async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...REQUEST_HEADER,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
  };
  if (signal) init.signal = signal;
  if (body !== undefined) init.body = JSON.stringify(body);
  const response = await fetch(`${API_BASE}${path}`, init);
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      errorMessage(payload, `Request failed (${response.status}).`),
      payload,
    );
  }
  return payload as T;
}
