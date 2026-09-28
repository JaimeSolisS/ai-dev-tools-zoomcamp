import { LogOut } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { useBackend } from '../services/ServiceProvider';

export function Logo() {
  return (
    <Link to="/" className="logo" aria-label="Archboard home">
      <svg viewBox="0 0 32 32" width={26} height={26} aria-hidden>
        <rect width="32" height="32" rx="7" fill="#5b4bdb" />
        <rect x="6" y="7" width="9" height="7" rx="1.5" fill="#fff" />
        <rect x="17" y="18" width="9" height="7" rx="1.5" fill="#fff" />
        <path d="M10.5 14v7.5H17" stroke="#fff" strokeWidth="2" fill="none" />
      </svg>
      <span>Archboard</span>
    </Link>
  );
}

export function AppHeader() {
  const { user, signOut } = useAuth();
  const backend = useBackend();
  return (
    <header className="app-header">
      <Logo />
      {backend.kind === 'mock' && (
        <span className="mock-pill" title="All data lives in this browser. No backend is running.">
          Mock backend
        </span>
      )}
      <div className="spacer" />
      {user && (
        <div className="user-menu">
          <span className="user-name">{user.displayName}</span>
          <span className="user-email">{user.email}</span>
          <button type="button" className="button ghost small" onClick={() => void signOut()}>
            <LogOut size={16} aria-hidden /> Sign out
          </button>
        </div>
      )}
    </header>
  );
}
