import { useCallback, useEffect, useState } from 'react';
import { Copy, RefreshCw, Trash2 } from 'lucide-react';
import { formatDateTime } from '../../lib/format';
import { copyText, joinUrl, recallLinkToken, rememberLinkToken } from '../../lib/linkVault';
import { errorMessage, type GuestLink, type GuestRole } from '../../services';
import { useBackend } from '../../services/ServiceProvider';
import { ErrorText, Modal } from '../ui';

const ROLE_LABEL: Record<GuestRole, string> = { candidate: 'Candidate', interviewer: 'Interviewer', observer: 'Observer (view only)' };

function linkStatus(l: GuestLink): string | null {
  if (l.revokedAt) return 'Revoked';
  if (l.expiresAt && new Date(l.expiresAt) <= new Date()) return 'Expired';
  if (l.maxUses != null && l.uses >= l.maxUses) return 'Used up';
  return null;
}

export function ShareDialog({ sessionId, onClose }: { sessionId: string; onClose(): void }) {
  const backend = useBackend();
  const [links, setLinks] = useState<GuestLink[] | null>(null);
  const [role, setRole] = useState<GuestRole>('candidate');
  const [expiresInHours, setExpiresInHours] = useState('');
  const [maxUses, setMaxUses] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState<string | null>(null);
  const [fresh, setFresh] = useState<{ id: string; url: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setLinks(await backend.sessions.listGuestLinks(sessionId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [backend, sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async (rotate: boolean) => {
    setError('');
    try {
      const { link, token } = await backend.sessions.createGuestLink(sessionId, {
        roleGranted: role,
        rotate,
        maxUses: maxUses ? Number(maxUses) : null,
        expiresAt: expiresInHours ? new Date(Date.now() + Number(expiresInHours) * 3600_000).toISOString() : null,
      });
      rememberLinkToken(link.id, token);
      const url = joinUrl(token);
      setFresh({ id: link.id, url });
      const ok = await copyText(url);
      setCopied(ok ? link.id : null);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const copy = async (link: GuestLink) => {
    const token = recallLinkToken(link.id);
    if (!token) {
      setError('This link was created in another browser. Create a new link to copy it here.');
      return;
    }
    const ok = await copyText(joinUrl(token));
    setCopied(ok ? link.id : null);
    if (!ok) setFresh({ id: link.id, url: joinUrl(token) });
  };

  const revoke = async (link: GuestLink) => {
    try {
      await backend.sessions.revokeGuestLink(sessionId, link.id);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const active = links?.filter((l) => !linkStatus(l)) ?? [];
  const inactive = links?.filter((l) => linkStatus(l)) ?? [];

  return (
    <Modal title="Share interview" onClose={onClose} width={560}>
      <p className="muted">
        Links contain a secret token. Anyone with an active link can join, so share it only with the people you invite. Revoking a link blocks new joins
        but does not disconnect people already in the room.
      </p>
      <div className="share-form">
        <label className="field">
          <span>Role</span>
          <select value={role} onChange={(e) => setRole(e.target.value as GuestRole)}>
            {(Object.keys(ROLE_LABEL) as GuestRole[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Expires</span>
          <select value={expiresInHours} onChange={(e) => setExpiresInHours(e.target.value)}>
            <option value="">Never</option>
            <option value="1">In 1 hour</option>
            <option value="24">In 24 hours</option>
            <option value="168">In 7 days</option>
          </select>
        </label>
        <label className="field">
          <span>Max uses</span>
          <input type="number" min={1} placeholder="Unlimited" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
        </label>
      </div>
      <div className="form-actions start">
        <button type="button" className="button primary" onClick={() => void create(false)}>
          Create {role} link
        </button>
        {active.some((l) => l.roleGranted === role) && (
          <button type="button" className="button" onClick={() => void create(true)}>
            <RefreshCw size={15} aria-hidden /> Rotate (revoke old {role} links)
          </button>
        )}
      </div>
      {fresh && (
        <div className="fresh-link">
          <label className="field">
            <span>{copied === fresh.id ? 'Copied to clipboard' : 'New link'}</span>
            <input readOnly value={fresh.url} onFocus={(e) => e.target.select()} aria-label="Invitation link" />
          </label>
        </div>
      )}
      <ErrorText>{error}</ErrorText>

      <h3 className="section-title">Active links</h3>
      {links === null ? null : active.length === 0 ? (
        <p className="muted">No active links.</p>
      ) : (
        <ul className="link-list">
          {active.map((l) => (
            <li key={l.id}>
              <div>
                <strong>{ROLE_LABEL[l.roleGranted]}</strong>
                <span className="muted">
                  {' '}
                  · created {formatDateTime(l.createdAt)} · {l.uses} use{l.uses === 1 ? '' : 's'}
                  {l.maxUses != null && ` of ${l.maxUses}`}
                  {l.expiresAt && ` · expires ${formatDateTime(l.expiresAt)}`}
                </span>
              </div>
              <div className="row-actions">
                <button type="button" className="button small" onClick={() => void copy(l)}>
                  <Copy size={14} aria-hidden /> {copied === l.id ? 'Copied' : 'Copy'}
                </button>
                <button type="button" className="button small ghost-danger" onClick={() => void revoke(l)}>
                  <Trash2 size={14} aria-hidden /> Revoke
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {inactive.length > 0 && (
        <details className="inactive-links">
          <summary>Inactive links ({inactive.length})</summary>
          <ul className="link-list">
            {inactive.map((l) => (
              <li key={l.id}>
                <span>
                  {ROLE_LABEL[l.roleGranted]} <span className="muted">· {linkStatus(l)} · created {formatDateTime(l.createdAt)}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Modal>
  );
}
