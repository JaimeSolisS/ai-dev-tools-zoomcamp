import { Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { FullPageMessage } from './components/ui';
import { DashboardPage } from './pages/DashboardPage';
import { InterviewRoomPage } from './pages/InterviewRoomPage';
import { LobbyPage } from './pages/LobbyPage';
import { LoginPage } from './pages/LoginPage';
import { NewSessionPage } from './pages/NewSessionPage';
import { VerifyPage } from './pages/VerifyPage';

export function AppRoutes() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/verify" element={<VerifyPage />} />
        <Route path="/join/:token" element={<LobbyPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />
        <Route
          path="/sessions/new"
          element={
            <RequireAuth>
              <NewSessionPage />
            </RequireAuth>
          }
        />
        {/* Room access is authorized by the backend: owners via sign-in, guests via their join credential. */}
        <Route path="/sessions/:sessionId" element={<InterviewRoomPage />} />
        <Route path="*" element={<FullPageMessage title="Page not found" />} />
      </Routes>
    </AuthProvider>
  );
}
