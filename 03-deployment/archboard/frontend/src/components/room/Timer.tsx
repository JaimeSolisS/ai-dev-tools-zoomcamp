import { useEffect, useState } from 'react';
import { Timer as TimerIcon } from 'lucide-react';
import { formatClock } from '../../lib/format';
import type { InterviewSession } from '../../services';

/** Visible timer only; it never changes the session state (spec §18.8). */
export function Timer({ session }: { session: InterviewSession }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (session.state !== 'live') return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [session.state]);

  if (!session.startedAt) {
    return session.durationMinutes ? (
      <span className="timer muted">
        <TimerIcon size={15} aria-hidden /> {session.durationMinutes} min
      </span>
    ) : null;
  }
  const end = session.endedAt ? new Date(session.endedAt).getTime() : now;
  const elapsed = (end - new Date(session.startedAt).getTime()) / 1000;
  const total = session.durationMinutes ? session.durationMinutes * 60 : null;
  const over = total !== null && elapsed > total;
  const text = total === null ? formatClock(elapsed) : over ? `+${formatClock(elapsed - total)} over` : `${formatClock(total - elapsed)} left`;
  return (
    <span className={`timer${over ? ' over' : ''}`} aria-label={`Timer: ${text}`}>
      <TimerIcon size={15} aria-hidden /> {text}
    </span>
  );
}
