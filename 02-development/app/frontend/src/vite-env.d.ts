/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND?: 'mock' | 'http';
  readonly VITE_MOCK_LATENCY_MS?: string;
  readonly VITE_API_BASE_URL?: string;
}
