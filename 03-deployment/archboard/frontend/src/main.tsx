import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './App';
import { createBackend } from './services';
import { ServiceProvider } from './services/ServiceProvider';
import './styles.css';

const backend = createBackend();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ServiceProvider backend={backend}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ServiceProvider>
  </StrictMode>,
);
