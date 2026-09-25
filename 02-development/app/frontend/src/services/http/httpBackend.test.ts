import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isApiError } from '../errors';
import { createMemoryStorage } from '../mock/storage';
import { controllableNetwork } from '../network';
import type { ServerMessage } from '../types';
import { createHttpBackend, NetworkError, WebSocketConnection } from './httpBackend';

const BASE = 'http://api.test';

interface Call {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** fetch stub that records calls and answers from a queue (or a fixed response). */
function fakeFetch(...responses: (Response | Error)[]) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({
      method: init.method ?? 'GET',
      url,
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    const next = responses.length > 1 ? responses.shift()! : responses[0];
    if (next instanceof Error) throw next;
    return next.clone();
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

class FakeSocket {
  static instances: FakeSocket[] = [];
  sent: unknown[] = [];
  closedWith: number | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close(code = 1000) {
    this.closedWith = code;
  }
  // Test helpers: simulate the server.
  open() {
    this.onopen?.();
  }
  receive(message: Partial<ServerMessage> & { type: string }) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  drop(code = 1006) {
    this.onclose?.({ code });
  }
}

function setup(...responses: (Response | Error)[]) {
  const fetch = fakeFetch(...(responses.length ? responses : [json(200, {})]));
  const storage = createMemoryStorage();
  const tabStorage = createMemoryStorage();
  const network = controllableNetwork(true);
  const backend = createHttpBackend({
    baseUrl: `${BASE}/`,
    fetch: fetch.fn,
    WebSocket: FakeSocket as unknown as new (url: string) => WebSocket,
    storage,
    tabStorage,
    network,
    reconnectDelays: [100, 200],
  });
  return { backend, calls: fetch.calls, storage, tabStorage, network };
}

const user = { id: 'u1', email: 'ada@example.com', displayName: 'Ada', organizationId: null, createdAt: '2026-01-01T00:00:00Z' };

beforeEach(() => {
  FakeSocket.instances = [];
});

describe('HTTP requests', () => {
  it('stores the access token from magic-link verification and sends it as a bearer token', async () => {
    const { backend, calls, storage } = setup(json(200, { user, accessToken: 'tok' }), json(200, []));
    expect(await backend.auth.verifyMagicLink('magic')).toEqual(user);
    expect(calls[0]).toMatchObject({ method: 'POST', url: `${BASE}/v1/auth/magic-link/verify`, body: { token: 'magic' } });
    expect(storage.getItem('archboard:access-token')).toBe('tok');

    await backend.sessions.list();
    expect(calls[1]).toMatchObject({ method: 'GET', url: `${BASE}/v1/sessions` });
    expect(calls[1].headers.Authorization).toBe('Bearer tok');
    expect(calls[1].headers['Content-Type']).toBeUndefined();
  });

  it('getCurrentUser skips the request without a token and forgets a rejected token', async () => {
    const { backend, calls, storage } = setup(json(401, { code: 'UNAUTHENTICATED', message: 'Please sign in.' }));
    expect(await backend.auth.getCurrentUser()).toBeNull();
    expect(calls).toHaveLength(0);

    storage.setItem('archboard:access-token', 'stale');
    expect(await backend.auth.getCurrentUser()).toBeNull();
    expect(calls).toHaveLength(1);
    expect(storage.getItem('archboard:access-token')).toBeNull();
  });

  it('signOut clears the token even if the request fails', async () => {
    const { backend, storage } = setup(new TypeError('offline'));
    storage.setItem('archboard:access-token', 'tok');
    await expect(backend.auth.signOut()).rejects.toBeInstanceOf(NetworkError);
    expect(storage.getItem('archboard:access-token')).toBeNull();
  });

  it('maps error bodies to ApiError with the server code and message', async () => {
    const { backend } = setup(json(410, { code: 'LINK_REVOKED', message: 'Revoked.' }));
    const err = await backend.join.getInfo('t').catch((e) => e);
    expect(isApiError(err, 'LINK_REVOKED')).toBe(true);
    expect(err.message).toBe('Revoked.');
    expect(err.status).toBe(410);
  });

  it('falls back to the HTTP status when the body has no known code', async () => {
    const { backend } = setup(json(404, { detail: 'nope' }), json(500, {}));
    expect(isApiError(await backend.sessions.get('x').catch((e) => e), 'NOT_FOUND')).toBe(true);
    const serverError = await backend.sessions.get('x').catch((e) => e);
    expect(isApiError(serverError)).toBe(false);
    expect(serverError.message).toBe('Request failed (500)');
  });

  it('reports network failures clearly', async () => {
    const { backend } = setup(new TypeError('Failed to fetch'));
    const err = await backend.sessions.list().catch((e) => e);
    expect(err).toBeInstanceOf(NetworkError);
    expect(err.message).toContain(BASE);
  });

  it('returns undefined for 204 responses and encodes path parameters', async () => {
    const { backend, calls } = setup(new Response(null, { status: 204 }));
    await expect(backend.sessions.revokeGuestLink('s/1', 'l 1')).resolves.toBeUndefined();
    expect(calls[0]).toMatchObject({ method: 'DELETE', url: `${BASE}/v1/sessions/s%2F1/guest-links/l%201` });
  });

  it('maps every session operation to its endpoint', async () => {
    const { backend, calls } = setup(json(200, {}));
    await backend.sessions.create({ title: 'T' });
    await backend.sessions.update('s1', { title: 'U' });
    await backend.sessions.start('s1');
    await backend.sessions.end('s1');
    await backend.sessions.reopen('s1');
    await backend.sessions.archive('s1');
    await backend.sessions.duplicate('s1');
    await backend.sessions.listParticipants('s1');
    await backend.sessions.removeParticipant('s1', 'p1');
    await backend.sessions.listGuestLinks('s1');
    await backend.sessions.createGuestLink('s1');
    await backend.sessions.clearCanvas('s1');
    await backend.sessions.listSnapshots('s1');
    await backend.sessions.restoreSnapshot('s1', 'snap1');
    await backend.canvas.openRoom('s1');
    expect(calls.map((c) => `${c.method} ${c.url.replace(BASE, '')}`)).toEqual([
      'POST /v1/sessions',
      'PATCH /v1/sessions/s1',
      'POST /v1/sessions/s1/start',
      'POST /v1/sessions/s1/end',
      'POST /v1/sessions/s1/reopen',
      'POST /v1/sessions/s1/archive',
      'POST /v1/sessions/s1/duplicate',
      'GET /v1/sessions/s1/participants',
      'DELETE /v1/sessions/s1/participants/p1',
      'GET /v1/sessions/s1/guest-links',
      'POST /v1/sessions/s1/guest-links',
      'POST /v1/sessions/s1/canvas/clear',
      'GET /v1/sessions/s1/canvas/snapshots',
      'POST /v1/sessions/s1/canvas/snapshots/snap1/restore',
      'GET /v1/sessions/s1/canvas',
    ]);
    expect(calls[0].body).toEqual({ title: 'T' });
    expect(calls[1].body).toEqual({ title: 'U' });
    expect(calls[10].body).toEqual({});
  });

  it('joining stores the guest credential and sends it only for that session', async () => {
    const participant = { id: 'p1', sessionId: 's1', displayName: 'Linus' };
    const { backend, calls, tabStorage } = setup(json(200, { sessionId: 's1', participant, credential: 'cred' }), json(200, {}));
    const result = await backend.join.join('tok', 'Linus');
    expect(result).toEqual({ sessionId: 's1', participant });
    expect(calls[0]).toMatchObject({ method: 'POST', url: `${BASE}/v1/join/tok`, body: { displayName: 'Linus' } });
    expect(tabStorage.getItem('archboard:guest:s1')).toBe('cred');

    await backend.canvas.openRoom('s1');
    await backend.sessions.get('s1');
    await backend.sessions.get('other');
    await backend.sessions.start('s1'); // owner-only: never sends guest credentials
    expect(calls.slice(1).map((c) => c.headers['X-Guest-Credential'])).toEqual(['cred', 'cred', undefined, undefined]);
  });
});

describe('WebSocket connection', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects with the guest credential in preference to the access token', () => {
    const { backend, storage, tabStorage } = setup();
    storage.setItem('archboard:access-token', 'tok');
    backend.realtime.connect('s1');
    expect(FakeSocket.instances[0].url).toBe('ws://api.test/v1/sessions/s1/ws?access_token=tok');
    tabStorage.setItem('archboard:guest:s1', 'c r');
    backend.realtime.connect('s1');
    expect(FakeSocket.instances[1].url).toBe('ws://api.test/v1/sessions/s1/ws?guest_credential=c%20r');
  });

  it('reports status, delivers messages and sends enveloped messages', () => {
    const { backend } = setup();
    const conn = backend.realtime.connect('s1');
    const statuses: string[] = [];
    const messages: ServerMessage[] = [];
    conn.onStatus((s) => statuses.push(s));
    conn.onMessage((m) => messages.push(m));
    expect(conn.status).toBe('connecting');
    expect(() => conn.send({ type: 'ping' })).toThrow('Not connected');

    const socket = FakeSocket.instances[0];
    socket.open();
    socket.receive({ type: 'room_joined', participantId: 'p1', cursor: 0 });
    expect(statuses).toEqual(['connected']);
    expect(messages[0]).toMatchObject({ type: 'room_joined', participantId: 'p1' });

    conn.send({ type: 'ping' });
    expect(socket.sent[0]).toMatchObject({ type: 'ping', v: 1, sessionId: 's1' });
    expect((socket.sent[0] as { id: string }).id).toMatch(/^m_/);
  });

  it('reconnects with backoff after an unexpected close', () => {
    const { backend } = setup();
    const conn = backend.realtime.connect('s1');
    const statuses: string[] = [];
    conn.onStatus((s) => statuses.push(s));
    FakeSocket.instances[0].open();
    FakeSocket.instances[0].drop();
    expect(conn.status).toBe('reconnecting');
    vi.advanceTimersByTime(99);
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.instances[1].drop();
    vi.advanceTimersByTime(200);
    expect(FakeSocket.instances).toHaveLength(3);
    FakeSocket.instances[2].open();
    expect(statuses).toEqual(['connected', 'reconnecting', 'connected']);
  });

  it('does not reconnect after the server rejects the connection', () => {
    const { backend } = setup();
    const conn = backend.realtime.connect('s1');
    const messages: ServerMessage[] = [];
    conn.onMessage((m) => messages.push(m));
    const socket = FakeSocket.instances[0];
    socket.open();
    socket.receive({ type: 'error', code: 'PARTICIPANT_REMOVED', message: 'Removed' });
    socket.drop(4403);
    vi.advanceTimersByTime(10_000);
    expect(conn.status).toBe('closed');
    expect(FakeSocket.instances).toHaveLength(1);
    expect(messages[0]).toMatchObject({ type: 'error', code: 'PARTICIPANT_REMOVED' });
  });

  it('follows the browser going offline and online', () => {
    const { backend, network } = setup();
    const conn = backend.realtime.connect('s1');
    FakeSocket.instances[0].open();
    network.set(false);
    expect(conn.status).toBe('offline');
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
    network.set(true);
    expect(conn.status).toBe('reconnecting');
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.instances[1].open();
    expect(conn.status).toBe('connected');
  });

  it('close() stops everything', () => {
    const { backend, network } = setup();
    const conn = backend.realtime.connect('s1') as WebSocketConnection;
    FakeSocket.instances[0].open();
    conn.close();
    expect(conn.status).toBe('closed');
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
    network.set(false);
    network.set(true);
    vi.advanceTimersByTime(10_000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(() => conn.send({ type: 'ping' })).toThrow('closed');
  });
});
