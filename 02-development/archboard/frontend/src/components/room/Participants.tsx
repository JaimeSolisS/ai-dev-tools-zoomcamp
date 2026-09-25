import { useEffect, useRef, useState } from 'react';
import { UserMinus, Users } from 'lucide-react';
import { initials } from '../../lib/format';
import type { Participant, Presence } from '../../services';

const ROLE: Record<Participant['role'], string> = {
  owner: 'Host',
  interviewer: 'Interviewer',
  candidate: 'Candidate',
  observer: 'Observer',
};

interface Props {
  participants: Participant[];
  presence: Presence[];
  meId: string;
  canRemove: boolean;
  onRemove(p: Participant): void;
}

export function Participants({ participants, presence, meId, canRemove, onRemove }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const online = new Set([meId, ...presence.map((p) => p.participantId)]);
  const sorted = [...participants].sort((a, b) => Number(online.has(b.id)) - Number(online.has(a.id)));

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  return (
    <div className="participants" ref={ref}>
      <button
        type="button"
        className="avatar-stack"
        aria-expanded={open}
        aria-label={`Participants: ${online.size} online of ${participants.length}`}
        onClick={() => setOpen((o) => !o)}
      >
        {sorted.slice(0, 4).map((p) => (
          <span
            key={p.id}
            className={`avatar${online.has(p.id) ? '' : ' away'}`}
            style={{ background: p.color }}
            title={`${p.displayName} (${ROLE[p.role]})${online.has(p.id) ? '' : ' — away'}`}
          >
            {initials(p.displayName)}
          </span>
        ))}
        {sorted.length > 4 && <span className="avatar more">+{sorted.length - 4}</span>}
        <Users size={15} aria-hidden className="muted" />
      </button>
      {open && (
        <div className="popover participants-popover" role="dialog" aria-label="Participants">
          <h3>Participants</h3>
          <ul>
            {sorted.map((p) => (
              <li key={p.id}>
                <span className="avatar small" style={{ background: p.color }} aria-hidden>
                  {initials(p.displayName)}
                </span>
                <span className="p-name">
                  {p.displayName}
                  {p.id === meId && <span className="muted"> (you)</span>}
                  <span className="p-meta">
                    {ROLE[p.role]} · <span className={online.has(p.id) ? 'online' : 'muted'}>{online.has(p.id) ? '● Online' : '○ Away'}</span>
                  </span>
                </span>
                {canRemove && p.role !== 'owner' && (
                  <button type="button" className="icon-button" aria-label={`Remove ${p.displayName}`} data-tooltip="Remove" onClick={() => onRemove(p)}>
                    <UserMinus size={16} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
