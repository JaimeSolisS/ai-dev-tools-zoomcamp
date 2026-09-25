import type { BackendService } from './api';
import { createHttpBackend } from './http/httpBackend';
import { createBroadcastBus } from './mock/bus';
import { createMockBackend } from './mock/mockBackend';

export * from './api';
export * from './errors';
export * from './permissions';
export * from './types';

/** Build the backend selected by environment variables (mock by default). */
export function createBackend(env: ImportMetaEnv = import.meta.env): BackendService {
  if (env.VITE_BACKEND === 'http') return createHttpBackend(env.VITE_API_BASE_URL ?? 'http://localhost:8000');
  return createMockBackend({
    serverStorage: window.localStorage,
    browserStorage: window.localStorage,
    tabStorage: window.sessionStorage,
    bus: createBroadcastBus(),
    latencyMs: Number(env.VITE_MOCK_LATENCY_MS ?? 120),
  });
}
