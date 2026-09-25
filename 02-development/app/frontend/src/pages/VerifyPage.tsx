import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { FullPageMessage, Spinner } from '../components/ui';
import { errorMessage } from '../services';
import { useBackend } from '../services/ServiceProvider';

export function VerifyPage() {
  const backend = useBackend();
  const { setUser } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState('');
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = params.get('token') ?? '';
    backend.auth
      .verifyMagicLink(token)
      .then((user) => {
        setUser(user);
        navigate((location.state as { from?: string } | null)?.from ?? '/', { replace: true });
      })
      .catch((err) => setError(errorMessage(err)));
  }, [backend, params, navigate, location.state, setUser]);

  if (error) {
    return (
      <FullPageMessage title="Sign-in link not valid">
        <p className="muted">{error}</p>
        <Link to="/login" className="button primary">
          Request a new link
        </Link>
      </FullPageMessage>
    );
  }
  return (
    <FullPageMessage title="Signing you in…">
      <Spinner />
    </FullPageMessage>
  );
}
