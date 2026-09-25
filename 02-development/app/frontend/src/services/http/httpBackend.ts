import type { BackendService } from '../api';

/**
 * Placeholder for the real REST + WebSocket client. It will implement the same
 * `BackendService` interface against the real backend (see `api.ts` for the
 * endpoint each method maps to).
 */
export function createHttpBackend(baseUrl: string): BackendService {
  throw new Error(`HTTP backend is not implemented yet (base URL: ${baseUrl}). Set VITE_BACKEND=mock.`);
}
