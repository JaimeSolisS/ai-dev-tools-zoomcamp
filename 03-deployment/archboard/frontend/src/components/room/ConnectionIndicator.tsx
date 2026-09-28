import { CloudUpload, LoaderCircle, Wifi, WifiOff } from 'lucide-react';
import type { ConnectionStatus } from '../../services';

const TEXT: Record<ConnectionStatus, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  reconnecting: 'Reconnecting…',
  offline: 'Offline',
  closed: 'Disconnected',
};

export function ConnectionIndicator({ status, pending }: { status: ConnectionStatus; pending: number }) {
  const Icon = status === 'connected' ? (pending ? CloudUpload : Wifi) : status === 'offline' || status === 'closed' ? WifiOff : LoaderCircle;
  const label = status === 'connected' && pending ? 'Saving…' : status === 'connected' ? 'All changes saved' : TEXT[status];
  return (
    <span className={`connection connection-${status}`} role="status" aria-live="polite" data-testid="connection-status">
      <Icon size={15} aria-hidden className={status === 'connecting' || status === 'reconnecting' ? 'spin' : undefined} />
      <span>{label}</span>
      {status === 'offline' && pending > 0 && <span className="muted"> · {pending} queued</span>}
    </span>
  );
}
