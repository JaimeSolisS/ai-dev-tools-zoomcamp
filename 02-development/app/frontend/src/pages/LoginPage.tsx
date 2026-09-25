import { useState, type FormEvent } from 'react';
import { MailCheck } from 'lucide-react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Logo } from '../components/AppHeader';
import { ErrorText } from '../components/ui';
import { errorMessage } from '../services';
import { useBackend } from '../services/ServiceProvider';

export function LoginPage() {
  const backend = useBackend();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const returnTo = (location.state as { from?: string } | null)?.from ?? '/';
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [devToken, setDevToken] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  if (user) return <Navigate to={returnTo} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await backend.auth.requestMagicLink(email);
      setSent(true);
      setDevToken(res.devToken ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="card narrow">
        <Logo />
        {!sent ? (
          <>
            <h1>Sign in to run interviews</h1>
            <p className="muted">We’ll email you a magic link. Candidates don’t need an account — they join with the link you share.</p>
            <form onSubmit={submit} className="stack">
              <label className="field">
                <span>Work email</span>
                <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
              </label>
              <ErrorText>{error}</ErrorText>
              <button className="button primary block" disabled={busy}>
                {busy ? 'Sending…' : 'Email me a sign-in link'}
              </button>
            </form>
          </>
        ) : (
          <>
            <MailCheck size={36} className="accent" aria-hidden />
            <h1>Check your inbox</h1>
            <p className="muted">
              We sent a sign-in link to <strong>{email}</strong>.
            </p>
            {devToken && (
              <div className="dev-note">
                <p>Mock backend: no email is sent. Use the link directly.</p>
                <button
                  type="button"
                  className="button primary block"
                  onClick={() => navigate(`/auth/verify?token=${encodeURIComponent(devToken)}`, { state: { from: returnTo } })}
                >
                  Open sign-in link
                </button>
              </div>
            )}
            <button type="button" className="button ghost" onClick={() => setSent(false)}>
              Use a different email
            </button>
          </>
        )}
      </div>
    </main>
  );
}
