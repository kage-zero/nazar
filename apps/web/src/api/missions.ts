import type {
  Asset,
  AuthState,
  Credentials,
  Mission,
  PreflightReport,
  UserPublic,
} from '@nazar/contracts';
import { API_BASE, request } from './client';

export const auth = {
  state: (signal?: AbortSignal) => request<AuthState>('GET', '/api/auth/state', undefined, signal),
  setup: (body: Credentials) => request<UserPublic>('POST', '/api/auth/setup', body),
  login: (body: Credentials) => request<UserPublic>('POST', '/api/auth/login', body),
  logout: () => request<undefined>('POST', '/api/auth/logout'),
};

export const missions = {
  list: (signal?: AbortSignal) => request<Mission[]>('GET', '/api/missions', undefined, signal),
  get: (id: string, signal?: AbortSignal) =>
    request<Mission>('GET', `/api/missions/${id}`, undefined, signal),
  create: (name: string) => request<Mission>('POST', '/api/missions', { name }),
};

export const assets = {
  register: (missionId: string, file: { name: string; size: number }) =>
    request<Asset>('POST', `/api/missions/${missionId}/assets`, {
      kind: 'video',
      filename: file.name,
      byte_size: file.size,
    }),
  get: (id: string, signal?: AbortSignal) =>
    request<Asset>('GET', `/api/assets/${id}`, undefined, signal),
  remove: (id: string) => request<undefined>('DELETE', `/api/assets/${id}`),
  retry: (id: string) => request<Asset>('POST', `/api/assets/${id}/retry`),
  preflight: (id: string, signal?: AbortSignal) =>
    request<PreflightReport>('GET', `/api/assets/${id}/preflight`, undefined, signal),
  imageUrl: (id: string, kind: 'thumbs' | 'keyframes', image: number) =>
    `${API_BASE}/api/assets/${id}/${kind}/${image}.jpg`,
};
