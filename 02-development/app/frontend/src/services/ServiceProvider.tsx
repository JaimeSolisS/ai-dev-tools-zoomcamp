import { createContext, useContext, type ReactNode } from 'react';
import type { BackendService } from './api';

const ServiceContext = createContext<BackendService | null>(null);

export function ServiceProvider({ backend, children }: { backend: BackendService; children: ReactNode }) {
  return <ServiceContext.Provider value={backend}>{children}</ServiceContext.Provider>;
}

export function useBackend(): BackendService {
  const backend = useContext(ServiceContext);
  if (!backend) throw new Error('useBackend must be used inside <ServiceProvider>');
  return backend;
}
