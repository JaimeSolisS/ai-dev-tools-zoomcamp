// @vitest-environment node
/**
 * Runs the HTTP client against a real, freshly started backend.
 * Skipped unless ARCHBOARD_API_URL is set — use `make test-integration` from app/.
 */
import { describe, expect, it, vi } from 'vitest';
import WebSocket from 'ws';
import { buildOperation, LamportClock, liveElements } from '../../canvas/model';
import { createShape } from '../../canvas/editing';
import type { RealtimeConnection } from '../api';
import { isApiError } from '../errors';
import { createMemoryStorage } from '../mock/storage';
import { controllableNetwork } from '../network';
import type { ServerMessage } from '../types';
import { createHttpBackend } from './httpBackend';

const API_URL = process.env.ARCHBOARD_API_URL;

function client() {
  return createHttpBackend({
    baseUrl: API_URL!,
    storage: createMemoryStorage(),
    tabStorage: createMemoryStorage(),
    network: controllableNetwork(true),
    // Node has no browser WebSocket; `ws` implements the same interface.
    WebSocket: WebSocket as unknown as new (url: string) => globalThis.WebSocket,
  });
}

function listen(conn: RealtimeConnection) {
  const messages: ServerMessage[] = [];
  conn.onMessage((m) => messages.push(m));
  return messages;
}

const waitFor = (fn: () => void) => vi.waitFor(fn, { timeout: 5000, interval: 25 });

describe.skipIf(!API_URL)('HTTP backend against a live server', () => {
  it('runs an interview end to end', async () => {
    const owner = client();
    const { devToken } = await owner.auth.requestMagicLink('ada@example.com');
    expect(devToken).toBeTruthy();
    const ada = await owner.auth.verifyMagicLink(devToken!);
    expect(ada.displayName).toBe('Ada Lovelace');
    expect((await owner.auth.getCurrentUser())?.id).toBe(ada.id);
    expect((await owner.sessions.list()).map((s) => s.title)).toContain('Design a chat app');

    const session = await owner.sessions.create({ title: 'Integration', prompt: 'Scale it' });
    await owner.sessions.start(session.id);
    const { token } = await owner.sessions.createGuestLink(session.id);

    const candidate = client();
    expect(await candidate.join.getInfo(token)).toMatchObject({ sessionTitle: 'Integration', roleGranted: 'candidate' });
    const { participant } = await candidate.join.join(token, 'Linus');
    const ownerRoom = await owner.canvas.openRoom(session.id);
    const candRoom = await candidate.canvas.openRoom(session.id);
    expect(candRoom.me.id).toBe(participant.id);
    expect(candRoom.permissions.canEdit).toBe(true);
    expect(ownerRoom.participants.map((p) => p.displayName)).toEqual(['Ada Lovelace', 'Linus']);

    const ownerConn = owner.realtime.connect(session.id);
    const candConn = candidate.realtime.connect(session.id);
    const ownerMsgs = listen(ownerConn);
    const candMsgs = listen(candConn);
    await waitFor(() => expect(ownerMsgs.some((m) => m.type === 'room_joined')).toBe(true));
    await waitFor(() => expect(candMsgs.some((m) => m.type === 'room_joined')).toBe(true));

    // Candidate edit reaches the owner and is persisted.
    const shape = createShape('cache', { x: 0, y: 0 }, participant.id, 1);
    const op = buildOperation(new LamportClock(participant.id), [shape]);
    candConn.send({ type: 'document_update', op });
    await waitFor(() => expect(candMsgs.find((m) => m.type === 'document_ack')).toMatchObject({ opId: op.id }));
    await waitFor(() => expect(ownerMsgs.find((m) => m.type === 'document_update')).toBeTruthy());
    expect(liveElements((await owner.canvas.openRoom(session.id)).canvas).map((e) => e.id)).toEqual([shape.id]);

    // Locking is broadcast and enforced.
    await owner.sessions.update(session.id, { candidateEditingEnabled: false });
    await waitFor(() => expect(candMsgs.some((m) => m.type === 'session_updated')).toBe(true));
    const blocked = buildOperation(new LamportClock(participant.id, 10), [shape]);
    candConn.send({ type: 'document_update', op: blocked });
    await waitFor(() => expect(candMsgs.find((m) => m.type === 'error')).toMatchObject({ code: 'EDIT_LOCKED', opId: blocked.id }));

    // Guests cannot use owner endpoints; removal disconnects them.
    expect(isApiError(await candidate.sessions.end(session.id).catch((e) => e), 'UNAUTHENTICATED')).toBe(true);
    await owner.sessions.removeParticipant(session.id, participant.id);
    await waitFor(() => expect(candMsgs.some((m) => m.type === 'participant_removed')).toBe(true));
    await waitFor(() => expect(candConn.status).toBe('closed'));
    expect(isApiError(await candidate.canvas.openRoom(session.id).catch((e) => e), 'PARTICIPANT_REMOVED')).toBe(true);

    ownerConn.close();
    await owner.auth.signOut();
    expect(await owner.auth.getCurrentUser()).toBeNull();
  });
});
