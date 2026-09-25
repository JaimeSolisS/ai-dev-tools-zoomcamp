import { useEffect, useState, type FormEvent } from 'react';
import { AlertTriangle, Link2Off } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Logo } from '../components/AppHeader';
import { ErrorText, FullPageMessage, Spinner } from '../components/ui';
import { errorMessage, type JoinInfo } from '../services';
import { useBackend } from '../services/ServiceProvider';

function browserWarning(): string | null {
  const missing = [
    typeof window.PointerEvent === 'undefined' && 'pointer events',
    typeof window.ResizeObserver === 'undefined' && 'ResizeObserver',
    typeof window.WebSocket === 'undefined' && 'WebSockets',
  ].filter(Boolean);
  if (missing.length) return `Your browser is missing features this app needs (${missing.join(', ')}). Please use the latest Chrome, Edge, Firefox or Safari.`;
  if (window.matchMedia?.('(max-width: 700px)').matches) return 'Editing on phones is not supported. For the best experience, join from a desktop browser.';
  return null;
}

const ROLE_TEXT = {
  candidate: 'You are joining as the candidate.',
  interviewer: 'You are joining as an interviewer.',
  observer: 'You are joining as an observer (view only).',
} as const;

export function LobbyPage() {
  const { token = '' } = useParams();
  const backend = useBackend();
  const navigate = useNavigate();
  const [info, setInfo] = useState<JoinInfo | null>(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [warning] = useState(browserWarning);

  useEffect(() => {
    backend.join
      .getInfo(token)
      .then(setInfo)
      .catch((err) => setLoadError(errorMessage(err)));
  }, [backend, token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!accepted) {
      setError('Please accept the notice to continue.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const { sessionId } = await backend.join.join(token, name);
      navigate(`/sessions/${sessionId}`, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  if (loadError) {
    return (
      <FullPageMessage title="Can’t join this interview" icon={<Link2Off size={36} className="accent" aria-hidden />}>
        <p className="muted" role="alert">
          {loadError}
        </p>
      </FullPageMessage>
    );
  }

  if (!info) {
    return (
      <FullPageMessage title="Checking your invitation…">
        <Spinner />
      </FullPageMessage>
    );
  }

  return (
    <main className="auth-page">
      <div className="card narrow">
        <Logo />
        <p className="eyebrow">System design interview</p>
        <h1>{info.sessionTitle}</h1>
        <p className="muted">{ROLE_TEXT[info.roleGranted]}</p>
        {warning && (
          <div className="warning-box" role="note">
            <AlertTriangle size={18} aria-hidden /> {warning}
          </div>
        )}
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>Your name</span>
            <input required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="How others will see you" autoFocus />
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
            <span>
              I understand that everything I draw on the shared canvas is saved and visible to the interviewers, including after the
              interview.
            </span>
          </label>
          <ErrorText>{error}</ErrorText>
          <button className="button primary block" disabled={busy}>
            {busy ? 'Joining…' : 'Join interview'}
          </button>
        </form>
        <p className="microcopy">Canvas activity is saved automatically. No audio or video is recorded.</p>
      </div>
    </main>
  );
}
