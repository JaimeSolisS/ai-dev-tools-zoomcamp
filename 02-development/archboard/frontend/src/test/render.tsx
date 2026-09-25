import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import type { BackendService } from '../services';
import { ServiceProvider } from '../services/ServiceProvider';

export function renderApp(backend: BackendService, route = '/') {
  return render(
    <ServiceProvider backend={backend}>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
      </MemoryRouter>
    </ServiceProvider>,
  );
}

export function withBackend(backend: BackendService) {
  return ({ children }: { children: ReactNode }) => <ServiceProvider backend={backend}>{children}</ServiceProvider>;
}
