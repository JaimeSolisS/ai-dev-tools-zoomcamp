/**
 * `BackendService` implementation that talks to the real backend over REST and
 * WebSockets, following `../../openapi.yaml`.
 *
 * Credentials (see the spec's securitySchemes):
 * - the interviewer's access token lives in localStorage (shared by tabs) and is
 *   sent as `Authorization: Bearer …`;
 * - a guest credential is kept per session in sessionStorage (per tab, so each
 *   tab can be a different participant) and sent as `X-Guest-Credential`;
 * - the WebSocket gets the same credentials as query parameters.
 */
import { newId } from '../../canvas/model';
import type { BackendService, RealtimeConnection } from '../api';
import { ApiError } from '../errors';
import { browserNetworkMonitor, type NetworkMonitor } from '../network';
import type { KeyValueStorage } from '../mock/storage';
import {
  PROTOCOL_VERSION,
  type CanvasSnapshotInfo,
  type ClientMessage,
  type ConnectionStatus,
  type CreatedGuestLink,
  type ErrorCode,
  type GuestLink,
  type InterviewSession,
  type JoinInfo,
  type MagicLinkRequest,
  type Participant,
  type RoomAccess,
  type ServerMessage,
  type SessionSummary,
  type User,
} from '../types';

const TOKEN_KEY = 'archboard:access-token';
const guestKey = (sessionId: string) => `archboard:guest:${sessionId}`;

/** Close codes after which reconnecting cannot help (see backend/app/realtime.py). */
const FATAL_CLOSE_CODES = new Set([4401, 4403, 4404]);
const DEFAULT_RECONNECT_DELAYS = [500, 1000, 2000, 5000, 10000];

const ERROR_CODES = new Set<ErrorCode>([
  'UNAUTHENTICATED',
  'FORBIDDEN',
  'NOT_FOUND',
  'VALIDATION',
  'LINK_INVALID',
  'LINK_REVOKED',
  'LINK_EXPIRED',
  'LINK_EXHAUSTED',
  'SESSION_ENDED',
  'SESSION_ARCHIVED',
  'SESSION_FULL',
  'EDIT_LOCKED',
  'PARTICIPANT_REMOVED',
  'CONFLICT',
]);

const STATUS_CODES: Record<number, ErrorCode> = {
  401: 'UNAUTHENTICATED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'VALIDATION',
};

type WebSocketFactory = new (url: string) => WebSocket;

export interface HttpBackendOptions {
  /** e.g. `http://localhost:8091` (no trailing slash needed). */
  baseUrl: string;
  fetch?: typeof fetch;
  WebSocket?: WebSocketFactory;
  /** Holds the access token (default: localStorage). */
  storage?: KeyValueStorage;
  /** Holds per-session guest credentials (default: sessionStorage). */
  tabStorage?: KeyValueStorage;
  network?: NetworkMonitor;
  reconnectDelays?: number[];
}

export class NetworkError extends Error {
  constructor(baseUrl: string) {
    super(`Could not reach the server at ${baseUrl}. Is the backend running?`);
    this.name = 'NetworkError';
  }
}

async function toError(response: Response): Promise<Error> {
  const body = (await response.json().catch(() => null)) as { code?: string; message?: string } | null;
  const message = body?.message || `Request failed (${response.status})`;
  if (body?.code && ERROR_CODES.has(body.code as ErrorCode)) return new ApiError(body.code as ErrorCode, message);
  const code = STATUS_CODES[response.status];
  return code ? new ApiError(code, message) : new Error(message);
}

export function createHttpBackend(options: HttpBackendOptions | string): BackendService {
  const opts = typeof options === 'string' ? { baseUrl: options } : options;
  const baseUrl = opts.baseUrl.replace(/\/+$/, '');
  const doFetch = opts.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const WS = opts.WebSocket ?? globalThis.WebSocket;
  const storage = opts.storage ?? window.localStorage;
  const tabStorage = opts.tabStorage ?? window.sessionStorage;
  const network = opts.network ?? browserNetworkMonitor();
  const reconnectDelays = opts.reconnectDelays ?? DEFAULT_RECONNECT_DELAYS;

  const token = () => storage.getItem(TOKEN_KEY);
  const guestCredential = (sessionId: string) => tabStorage.getItem(guestKey(sessionId));
  const enc = encodeURIComponent;

  interface RequestOptions {
    body?: unknown;
    /** Send this session's guest credential, if the tab has one. */
    sessionId?: string;
  }

  async function request<T>(method: string, path: string, { body, sessionId }: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const accessToken = token();
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const credential = sessionId ? guestCredential(sessionId) : null;
    if (credential) headers['X-Guest-Credential'] = credential;

    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new NetworkError(baseUrl);
    }
    if (!response.ok) throw await toError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  const session = (id: string) => `/v1/sessions/${enc(id)}`;

  const backend: BackendService = {
    kind: 'http',

    auth: {
      async getCurrentUser() {
        if (!token()) return null;
        try {
          return await request<User>('GET', '/v1/auth/me');
        } catch (err) {
          // The token is no longer valid (e.g. the in-memory backend restarted).
          if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
            storage.removeItem(TOKEN_KEY);
            return null;
          }
          throw err;
        }
      },
      requestMagicLink: (email) => request<MagicLinkRequest>('POST', '/v1/auth/magic-link', { body: { email } }),
      async verifyMagicLink(magicToken) {
        const result = await request<{ user: User; accessToken: string }>('POST', '/v1/auth/magic-link/verify', {
          body: { token: magicToken },
        });
        storage.setItem(TOKEN_KEY, result.accessToken);
        return result.user;
      },
      async signOut() {
        try {
          await request<void>('POST', '/v1/auth/logout');
        } finally {
          storage.removeItem(TOKEN_KEY);
        }
      },
    },

    sessions: {
      list: () => request<SessionSummary[]>('GET', '/v1/sessions'),
      create: (input) => request<InterviewSession>('POST', '/v1/sessions', { body: input }),
      get: (id) => request<InterviewSession>('GET', session(id), { sessionId: id }),
      update: (id, patch) => request<InterviewSession>('PATCH', session(id), { body: patch, sessionId: id }),
      start: (id) => request<InterviewSession>('POST', `${session(id)}/start`),
      end: (id) => request<InterviewSession>('POST', `${session(id)}/end`),
      reopen: (id) => request<InterviewSession>('POST', `${session(id)}/reopen`),
      archive: (id) => request<InterviewSession>('POST', `${session(id)}/archive`),
      duplicate: (id) => request<InterviewSession>('POST', `${session(id)}/duplicate`),
      listParticipants: (id) => request<Participant[]>('GET', `${session(id)}/participants`, { sessionId: id }),
      removeParticipant: (id, participantId) =>
        request<void>('DELETE', `${session(id)}/participants/${enc(participantId)}`),
      listGuestLinks: (id) => request<GuestLink[]>('GET', `${session(id)}/guest-links`),
      createGuestLink: (id, input = {}) =>
        request<CreatedGuestLink>('POST', `${session(id)}/guest-links`, { body: input }),
      revokeGuestLink: (id, linkId) => request<void>('DELETE', `${session(id)}/guest-links/${enc(linkId)}`),
      clearCanvas: (id) => request<void>('POST', `${session(id)}/canvas/clear`),
      listSnapshots: (id) => request<CanvasSnapshotInfo[]>('GET', `${session(id)}/canvas/snapshots`),
      restoreSnapshot: (id, snapshotId) =>
        request<void>('POST', `${session(id)}/canvas/snapshots/${enc(snapshotId)}/restore`),
    },

    join: {
      getInfo: (joinToken) => request<JoinInfo>('GET', `/v1/join/${enc(joinToken)}`),
      async join(joinToken, displayName) {
        const result = await request<{ sessionId: string; participant: Participant; credential: string }>(
          'POST',
          `/v1/join/${enc(joinToken)}`,
          { body: { displayName } },
        );
        tabStorage.setItem(guestKey(result.sessionId), result.credential);
        return { sessionId: result.sessionId, participant: result.participant };
      },
    },

    canvas: {
      openRoom: (sessionId) => request<RoomAccess>('GET', `${session(sessionId)}/canvas`, { sessionId }),
    },

    realtime: {
      connect(sessionId) {
        const url = () => {
          const wsBase = baseUrl.replace(/^http/, 'ws');
          const credential = guestCredential(sessionId);
          const accessToken = token();
          const query = credential
            ? `guest_credential=${enc(credential)}`
            : accessToken
              ? `access_token=${enc(accessToken)}`
              : '';
          return `${wsBase}${session(sessionId)}/ws${query ? `?${query}` : ''}`;
        };
        return new WebSocketConnection(sessionId, url, WS, network, reconnectDelays);
      },
    },
  };

  return backend;
}

/**
 * A realtime connection that reconnects with backoff and follows the browser's
 * online/offline state. Every (re)connect is followed by a `room_joined`
 * message from the server, which tells `useRoom` to resync.
 */
export class WebSocketConnection implements RealtimeConnection {
  status: ConnectionStatus = 'connecting';
  private socket: WebSocket | null = null;
  private attempts = 0;
  private everConnected = false;
  private closed = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly messageListeners = new Set<(m: ServerMessage) => void>();
  private readonly statusListeners = new Set<(s: ConnectionStatus) => void>();
  private readonly offNetwork: () => void;

  constructor(
    private readonly sessionId: string,
    private readonly url: () => string,
    private readonly WS: WebSocketFactory,
    private readonly network: NetworkMonitor,
    private readonly reconnectDelays: number[],
  ) {
    this.offNetwork = network.subscribe((online) => (online ? this.reconnectNow() : this.goOffline()));
    if (network.isOnline()) this.open();
    else this.setStatus('offline');
  }

  private setStatus(status: ConnectionStatus) {
    if (this.status === status) return;
    this.status = status;
    this.statusListeners.forEach((l) => l(status));
  }

  private open() {
    if (this.closed) return;
    this.setStatus(this.everConnected ? 'reconnecting' : 'connecting');
    const socket = new this.WS(this.url());
    this.socket = socket;

    socket.onopen = () => {
      if (socket !== this.socket) return;
      this.attempts = 0;
      this.everConnected = true;
      this.setStatus('connected');
    };
    socket.onmessage = (event: MessageEvent) => {
      if (socket !== this.socket || typeof event.data !== 'string') return;
      let message: ServerMessage;
      try {
        message = JSON.parse(event.data) as ServerMessage;
      } catch {
        return;
      }
      this.messageListeners.forEach((l) => l(message));
    };
    socket.onclose = (event: CloseEvent) => {
      if (socket !== this.socket) return;
      this.socket = null;
      if (this.closed) return;
      if (FATAL_CLOSE_CODES.has(event.code)) {
        // The server already sent an `error` message explaining why.
        this.setStatus('closed');
        return;
      }
      if (!this.network.isOnline()) {
        this.setStatus('offline');
        return;
      }
      this.scheduleReconnect();
    };
    socket.onerror = () => {
      // A close event always follows; reconnection is handled there.
    };
  }

  private scheduleReconnect() {
    this.setStatus(this.everConnected ? 'reconnecting' : 'connecting');
    const delay = this.reconnectDelays[Math.min(this.attempts, this.reconnectDelays.length - 1)];
    this.attempts += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.open();
    }, delay);
  }

  private dropSocket() {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000);
  }

  private reconnectNow() {
    if (this.closed || (this.socket && this.status === 'connected')) return;
    this.dropSocket();
    this.attempts = 0;
    this.open();
  }

  private goOffline() {
    if (this.closed) return;
    this.dropSocket();
    this.setStatus('offline');
  }

  send(message: ClientMessage): void {
    if (this.closed) throw new Error('Connection is closed');
    if (!this.socket || this.status !== 'connected') throw new Error('Not connected');
    this.socket.send(JSON.stringify({ ...message, v: PROTOCOL_VERSION, sessionId: this.sessionId, id: newId('m') }));
  }

  onMessage(listener: (m: ServerMessage) => void) {
    this.messageListeners.add(listener);
    return () => void this.messageListeners.delete(listener);
  }

  onStatus(listener: (s: ConnectionStatus) => void) {
    this.statusListeners.add(listener);
    return () => void this.statusListeners.delete(listener);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.offNetwork();
    this.dropSocket();
    this.setStatus('closed');
  }
}
