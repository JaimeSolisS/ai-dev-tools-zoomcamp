import type { BackendService } from './api';
import { createHttpBackend } from './http/httpBackend';
import { createBroadcastBus } from './mock/bus';
import { createMockBackend } from './mock/mockBackend';

export * from './api';
export * from './errors';
export * from './permissions';
export * from './types';

export const DEFAULT_API_BASE_URL = 'http://localhost:8091';

/**
 * Build the backend selected by environment variables: the real backend by
 * default, or the in-browser mock with `VITE_BACKEND=mock`.
 */
export function createBackend(env: ImportMetaEnv = import.meta.env): BackendService {
  if (env.VITE_BACKEND !== 'mock') return createHttpBackend({ baseUrl: env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL });
  return createMockBackend({
    serverStorage: window.localStorage,
    browserStorage: window.localStorage,
    tabStorage: window.sessionStorage,
    bus: createBroadcastBus(),
    latencyMs: Number(env.VITE_MOCK_LATENCY_MS ?? 120),
  });
}
