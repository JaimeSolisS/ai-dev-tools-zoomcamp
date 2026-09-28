import { useCallback, useEffect, useState } from 'react';
import { Archive, CopyPlus, FolderOpen, Link2, Plus } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { AppHeader } from '../components/AppHeader';
import { ConfirmDialog, ErrorText, Spinner, StateBadge } from '../components/ui';
import { formatDate, formatDateTime, formatRelative } from '../lib/format';
import { copyText, joinUrl, recallLinkToken, rememberLinkToken } from '../lib/linkVault';
import { errorMessage, type SessionSummary } from '../services';
import { useBackend } from '../services/ServiceProvider';

export function DashboardPage() {
  const backend = useBackend();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState<SessionSummary | null>(null);

  const load = useCallback(async () => {
    try {
      setSessions(await backend.sessions.list());
      setError('');
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [backend]);

  useEffect(() => {
    void load();
  }, [load]);

  const announce = (text: string) => {
    setStatus(text);
    setTimeout(() => setStatus((s) => (s === text ? '' : s)), 3000);
  };

  const copyLink = async (s: SessionSummary) => {
    try {
      let token = s.activeGuestLink ? recallLinkToken(s.activeGuestLink.id) : null;
      if (!token) {
        const created = await backend.sessions.createGuestLink(s.id);
        rememberLinkToken(created.link.id, created.token);
        token = created.token;
        void load();
      }
      const ok = await copyText(joinUrl(token));
      announce(ok ? `Candidate link for “${s.title}” copied.` : `Candidate link: ${joinUrl(token)}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const duplicate = async (s: SessionSummary) => {
    try {
      const copy = await backend.sessions.duplicate(s.id);
      navigate(`/sessions/${copy.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const archive = async () => {
    if (!archiving) return;
    try {
      await backend.sessions.archive(archiving.id);
      announce(`“${archiving.title}” archived.`);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setArchiving(null);
    }
  };

  const visible = sessions?.filter((s) => showArchived || s.state !== 'archived') ?? [];
  const archivedCount = sessions?.filter((s) => s.state === 'archived').length ?? 0;

  return (
    <div className="page">
      <AppHeader />
      <main className="container">
        <div className="page-title-row">
          <div>
            <h1>Interviews</h1>
            <p className="muted">Create a session, share the candidate link, and design together on a live canvas.</p>
          </div>
          <Link to="/sessions/new" className="button primary">
            <Plus size={18} aria-hidden /> New interview
          </Link>
        </div>

        <ErrorText>{error}</ErrorText>
        <p className="sr-only" role="status" aria-live="polite">
          {status}
        </p>
        {status && <div className="inline-status">{status}</div>}

        {sessions === null ? (
          <Spinner label="Loading interviews" />
        ) : visible.length === 0 ? (
          <div className="empty-state card">
            <h2>No interviews yet</h2>
            <p className="muted">Start your first system-design interview.</p>
            <Link to="/sessions/new" className="button primary">
              <Plus size={18} aria-hidden /> New interview
            </Link>
          </div>
        ) : (
          <div className="table-wrap card">
            <table className="sessions-table">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">State</th>
                  <th scope="col">Created</th>
                  <th scope="col">Session time</th>
                  <th scope="col">Participants</th>
                  <th scope="col">Last modified</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/sessions/${s.id}`} className="session-title">
                        {s.title}
                      </Link>
                    </td>
                    <td>
                      <StateBadge state={s.state} />
                    </td>
                    <td>{formatDate(s.createdAt)}</td>
                    <td>{s.startedAt ? formatDateTime(s.startedAt) : s.scheduledAt ? `Scheduled ${formatDateTime(s.scheduledAt)}` : '—'}</td>
                    <td className="participants-cell">{s.participantNames.length ? s.participantNames.join(', ') : <span className="muted">—</span>}</td>
                    <td title={s.lastModifiedAt}>{formatRelative(s.lastModifiedAt)}</td>
                    <td>
                      <div className="row-actions">
                        <Link to={`/sessions/${s.id}`} className="button small" aria-label={`Open ${s.title}`}>
                          <FolderOpen size={15} aria-hidden /> Open
                        </Link>
                        {(s.state === 'draft' || s.state === 'live') && (
                          <button type="button" className="button small" onClick={() => void copyLink(s)} aria-label={`Copy candidate link for ${s.title}`}>
                            <Link2 size={15} aria-hidden /> Copy link
                          </button>
                        )}
                        <button type="button" className="button small" onClick={() => void duplicate(s)} aria-label={`Duplicate ${s.title}`}>
                          <CopyPlus size={15} aria-hidden /> Duplicate
                        </button>
                        {s.state !== 'archived' && (
                          <button type="button" className="button small ghost-danger" onClick={() => setArchiving(s)} aria-label={`Archive ${s.title}`}>
                            <Archive size={15} aria-hidden /> Archive
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {archivedCount > 0 && (
          <label className="checkbox-row">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show archived ({archivedCount})
          </label>
        )}
      </main>

      {archiving && (
        <ConfirmDialog
          title="Archive interview?"
          message={
            <p>
              “{archiving.title}” will be closed to all participants and its links will stop working. The final canvas is kept for
              review.
            </p>
          }
          confirmLabel="Archive"
          destructive
          onConfirm={() => void archive()}
          onCancel={() => setArchiving(null)}
        />
      )}
    </div>
  );
}
