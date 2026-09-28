import { describe, expect, it, vi } from 'vitest';
import { buildOperation, LamportClock, liveElements } from '../../canvas/model';
import type { ShapeElement } from '../../canvas/types';
import { createWorld, signIn } from '../../test/world';
import type { RealtimeConnection } from '../api';
import { isApiError } from '../errors';
import type { ServerMessage } from '../types';
import { createMockBackend, MAX_PARTICIPANTS } from './mockBackend';
import { createMemoryStorage } from './storage';

function node(id: string, actor: string, extra: Partial<ShapeElement> = {}): ShapeElement {
  return {
    id,
    kind: 'shape',
    componentType: 'server',
    x: 0,
    y: 0,
    w: 120,
    h: 60,
    label: 'Server',
    z: 1,
    version: { clock: 0, actor },
    createdBy: actor,
    createdAt: new Date().toISOString(),
    updatedBy: actor,
    ...extra,
  };
}

async function expectCode(promise: Promise<unknown>, code: string) {
  await expect(promise).rejects.toSatisfy((e: unknown) => isApiError(e) && e.code === code);
}

/** Collect messages from a connection and wait for it to connect. */
async function open(conn: RealtimeConnection) {
  const messages: ServerMessage[] = [];
  conn.onMessage((m) => messages.push(m));
  await vi.waitFor(() => expect(messages.some((m) => m.type === 'room_joined')).toBe(true));
  return messages;
}

async function setupInterview() {
  const world = createWorld();
  const owner = world.client();
  await signIn(owner);
  const session = await owner.sessions.create({ title: 'Design Twitter', prompt: 'Timeline at scale' });
  const { token } = await owner.sessions.createGuestLink(session.id);
  return { world, owner, session, token };
}

describe('auth', () => {
  it('signs in with a magic link and signs out', async () => {
    const backend = createMockBackend({ seedExamples: false });
    expect(await backend.auth.getCurrentUser()).toBeNull();
    const user = await signIn(backend, 'Grace@Example.com');
    expect(user.email).toBe('grace@example.com');
    expect((await backend.auth.getCurrentUser())?.id).toBe(user.id);
    await backend.auth.signOut();
    expect(await backend.auth.getCurrentUser()).toBeNull();
  });

  it('magic links are single-use', async () => {
    const backend = createMockBackend({ seedExamples: false });
    const { devToken } = await backend.auth.requestMagicLink('a@b.co');
    await backend.auth.verifyMagicLink(devToken!);
    await expectCode(backend.auth.verifyMagicLink(devToken!), 'LINK_INVALID');
  });

  it('rejects invalid emails', async () => {
    await expectCode(createMockBackend().auth.requestMagicLink('nope'), 'VALIDATION');
  });

  it('seeds an example session for new users', async () => {
    const backend = createMockBackend();
    await signIn(backend);
    const sessions = await backend.sessions.list();
    expect(sessions).toHaveLength(1);
    expect(sessions[0].state).toBe('ended');
    const room = await backend.canvas.openRoom(sessions[0].id);
    expect(liveElements(room.canvas).length).toBeGreaterThan(5);
  });
});

describe('sessions', () => {
  it('requires authentication', async () => {
    const backend = createMockBackend();
    await expectCode(backend.sessions.list(), 'UNAUTHENTICATED');
    await expectCode(backend.sessions.create({ title: 'x' }), 'UNAUTHENTICATED');
  });

  it('creates a draft, starts, ends and reopens it', async () => {
    const { owner, session } = await setupInterview();
    expect(session.state).toBe('draft');
    expect((await owner.sessions.start(session.id)).state).toBe('live');
    const ended = await owner.sessions.end(session.id);
    expect(ended.state).toBe('ended');
    expect(ended.endedAt).not.toBeNull();
    const snapshots = await owner.sessions.listSnapshots(session.id);
    expect(snapshots.map((s) => s.reason)).toContain('final');
    expect((await owner.sessions.reopen(session.id)).state).toBe('live');
  });

  it('validates titles and durations', async () => {
    const { owner } = await setupInterview();
    await expectCode(owner.sessions.create({ title: '   ' }), 'VALIDATION');
    await expectCode(owner.sessions.create({ title: 'ok', durationMinutes: 1 }), 'VALIDATION');
  });

  it('lists sessions with participant names and an active link', async () => {
    const { world, owner, session, token } = await setupInterview();
    const candidate = world.client();
    await candidate.join.join(token, 'Linus');
    const [summary] = await owner.sessions.list();
    expect(summary.id).toBe(session.id);
    expect(summary.participantNames).toEqual(['Linus']);
    expect(summary.activeGuestLink?.uses).toBe(1);
  });

  it('duplicates a session with its canvas as a new draft', async () => {
    const { owner, session } = await setupInterview();
    const room = await owner.canvas.openRoom(session.id);
    const conn = owner.realtime.connect(session.id);
    const messages = await open(conn);
    const clock = new LamportClock(room.me.id);
    conn.send({ type: 'document_update', op: buildOperation(clock, [node('n1', room.me.id)]) });
    await vi.waitFor(() => expect(messages.some((m) => m.type === 'document_ack')).toBe(true));
    const copy = await owner.sessions.duplicate(session.id);
    expect(copy.state).toBe('draft');
    expect(copy.title).toBe('Design Twitter (copy)');
    const copyRoom = await owner.canvas.openRoom(copy.id);
    expect(liveElements(copyRoom.canvas).map((e) => e.id)).toEqual(['n1']);
    conn.close();
  });

  it('archives a session so nobody can join', async () => {
    const { world, owner, session, token } = await setupInterview();
    await owner.sessions.archive(session.id);
    await expectCode(world.client().join.getInfo(token), 'SESSION_ARCHIVED');
  });

  it('records audit events for sensitive actions', async () => {
    const { owner, session } = await setupInterview();
    await owner.sessions.start(session.id);
    await owner.sessions.update(session.id, { candidateEditingEnabled: false });
    await owner.sessions.end(session.id);
    const actions = owner.db.auditLog().map((e) => e.action);
    expect(actions).toEqual(
      expect.arrayContaining(['session.created', 'link.created', 'session.started', 'permissions.changed', 'session.ended']),
    );
  });
});

describe('guest links and joining', () => {
  it('stores only a hash of the token', async () => {
    const { owner, token } = await setupInterview();
    const raw = JSON.stringify(owner.db.guestLinks.values());
    expect(raw).not.toContain(token);
    expect(token.length).toBeGreaterThanOrEqual(22); // >= 128 bits in base64url
  });

  it('shows lobby info and joins as a candidate', async () => {
    const { world, session, token } = await setupInterview();
    const candidate = world.client();
    expect(await candidate.join.getInfo(token)).toEqual({
      sessionTitle: 'Design Twitter',
      sessionState: 'draft',
      roleGranted: 'candidate',
    });
    const result = await candidate.join.join(token, '  Linus ');
    expect(result.sessionId).toBe(session.id);
    expect(result.participant.displayName).toBe('Linus');
    expect(result.participant.role).toBe('candidate');
    const room = await candidate.canvas.openRoom(session.id);
    expect(room.me.id).toBe(result.participant.id);
    expect(room.session.prompt).toBe('Timeline at scale');
  });

  it('rejects unknown, revoked and expired links with clear errors', async () => {
    let now = new Date('2026-09-01T10:00:00Z');
    const world = createWorld({ now: () => now });
    const owner = world.client();
    await signIn(owner);
    const session = await owner.sessions.create({ title: 'T' });
    const guest = world.client();

    await expectCode(guest.join.getInfo('not-a-token'), 'LINK_INVALID');

    const revoked = await owner.sessions.createGuestLink(session.id);
    await owner.sessions.revokeGuestLink(session.id, revoked.link.id);
    await expectCode(guest.join.join(revoked.token, 'Eve'), 'LINK_REVOKED');

    const expiring = await owner.sessions.createGuestLink(session.id, { expiresAt: '2026-09-01T11:00:00Z' });
    expect((await guest.join.getInfo(expiring.token)).sessionTitle).toBe('T');
    now = new Date('2026-09-01T12:00:00Z');
    await expectCode(guest.join.join(expiring.token, 'Eve'), 'LINK_EXPIRED');
  });

  it('rotating a link revokes the previous one but keeps current participants', async () => {
    const { world, owner, session, token } = await setupInterview();
    const candidate = world.client();
    await candidate.join.join(token, 'Linus');
    const rotated = await owner.sessions.createGuestLink(session.id, { rotate: true });
    await expectCode(world.client().join.join(token, 'Late'), 'LINK_REVOKED');
    await world.client().join.join(rotated.token, 'Newcomer');
    // Existing candidate still has access.
    expect((await candidate.canvas.openRoom(session.id)).me.displayName).toBe('Linus');
  });

  it('enforces max uses and capacity', async () => {
    const { world, owner, session } = await setupInterview();
    const single = await owner.sessions.createGuestLink(session.id, { maxUses: 1 });
    await world.client().join.join(single.token, 'One');
    await expectCode(world.client().join.join(single.token, 'Two'), 'LINK_EXHAUSTED');

    const open = await owner.sessions.createGuestLink(session.id);
    for (let i = 1; i < MAX_PARTICIPANTS; i++) await world.client().join.join(open.token, `Guest ${i}`);
    await expectCode(world.client().join.join(open.token, 'One too many'), 'SESSION_FULL');
  });

  it('rejoining from the same tab reuses the participant', async () => {
    const { world, token } = await setupInterview();
    const candidate = world.client();
    const first = await candidate.join.join(token, 'Linus');
    const second = await candidate.join.join(token, 'Linus T.');
    expect(second.participant.id).toBe(first.participant.id);
    expect(second.participant.displayName).toBe('Linus T.');
  });

  it('requires a display name', async () => {
    const { world, token } = await setupInterview();
    await expectCode(world.client().join.join(token, '  '), 'VALIDATION');
  });

  it('refuses joins to ended sessions', async () => {
    const { world, owner, session, token } = await setupInterview();
    await owner.sessions.end(session.id);
    await expectCode(world.client().join.getInfo(token), 'SESSION_ENDED');
  });
});

describe('authorization', () => {
  it('a candidate cannot access another session by changing the id', async () => {
    const { world, owner, token } = await setupInterview();
    const other = await owner.sessions.create({ title: 'Secret' });
    const candidate = world.client();
    await candidate.join.join(token, 'Mallory');
    await expectCode(candidate.canvas.openRoom(other.id), 'UNAUTHENTICATED');
    await expectCode(candidate.sessions.get(other.id), 'UNAUTHENTICATED');
  });

  it('another interviewer cannot manage a session they do not own', async () => {
    const { world, session } = await setupInterview();
    const stranger = world.client();
    await signIn(stranger, 'stranger@example.com');
    await expectCode(stranger.sessions.end(session.id), 'NOT_FOUND');
    await expectCode(stranger.canvas.openRoom(session.id), 'NOT_FOUND');
    await expectCode(stranger.sessions.listGuestLinks(session.id), 'NOT_FOUND');
  });

  it('candidates cannot change settings or lock editing', async () => {
    const { world, session, token } = await setupInterview();
    const candidate = world.client();
    await candidate.join.join(token, 'Linus');
    await expectCode(candidate.sessions.update(session.id, { title: 'Hacked' }), 'FORBIDDEN');
    await expectCode(candidate.sessions.update(session.id, { candidateEditingEnabled: true }), 'FORBIDDEN');
  });

  it('removed participants lose access', async () => {
    const { world, owner, session, token } = await setupInterview();
    const candidate = world.client();
    const { participant } = await candidate.join.join(token, 'Linus');
    await owner.sessions.removeParticipant(session.id, participant.id);
    await expectCode(candidate.canvas.openRoom(session.id), 'PARTICIPANT_REMOVED');
    expect((await owner.sessions.listParticipants(session.id)).map((p) => p.role)).toEqual(['owner']);
  });

  it('ended sessions are hidden from candidates but visible to the owner', async () => {
    const { world, owner, session, token } = await setupInterview();
    const candidate = world.client();
    await candidate.join.join(token, 'Linus');
    await owner.sessions.end(session.id);
    await expectCode(candidate.canvas.openRoom(session.id), 'SESSION_ENDED');
    const room = await owner.canvas.openRoom(session.id);
    expect(room.permissions.canEdit).toBe(false);
    expect(room.permissions.canView).toBe(true);
  });
});

describe('real-time collaboration', () => {
  async function liveRoom() {
    const ctx = await setupInterview();
    await ctx.owner.sessions.start(ctx.session.id);
    const candidate = ctx.world.client();
    await candidate.join.join(ctx.token, 'Linus');
    const ownerRoom = await ctx.owner.canvas.openRoom(ctx.session.id);
    const candRoom = await candidate.canvas.openRoom(ctx.session.id);
    const ownerConn = ctx.owner.realtime.connect(ctx.session.id);
    const candConn = candidate.realtime.connect(ctx.session.id);
    const [ownerMsgs, candMsgs] = await Promise.all([open(ownerConn), open(candConn)]);
    return { ...ctx, candidate, ownerRoom, candRoom, ownerConn, candConn, ownerMsgs, candMsgs };
  }

  it('propagates operations to other participants and persists them', async () => {
    const r = await liveRoom();
    const op = buildOperation(new LamportClock(r.candRoom.me.id), [node('db', r.candRoom.me.id)]);
    r.candConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.ownerMsgs.find((m) => m.type === 'document_update')).toBeTruthy());
    await vi.waitFor(() => expect(r.candMsgs.find((m) => m.type === 'document_ack')).toBeTruthy());
    // Sender does not receive its own update back.
    expect(r.candMsgs.some((m) => m.type === 'document_update')).toBe(false);
    const reloaded = await r.owner.canvas.openRoom(r.session.id);
    expect(liveElements(reloaded.canvas).map((e) => e.id)).toEqual(['db']);
    expect(reloaded.cursor).toBe(1);
  });

  it('acknowledges duplicate operations without re-broadcasting', async () => {
    const r = await liveRoom();
    const op = buildOperation(new LamportClock(r.candRoom.me.id), [node('x', r.candRoom.me.id)]);
    r.candConn.send({ type: 'document_update', op });
    r.candConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.candMsgs.filter((m) => m.type === 'document_ack')).toHaveLength(2));
    expect(r.ownerMsgs.filter((m) => m.type === 'document_update')).toHaveLength(1);
    expect((await r.owner.canvas.openRoom(r.session.id)).cursor).toBe(1);
  });

  it('rejects candidate edits while editing is locked', async () => {
    const r = await liveRoom();
    await r.owner.sessions.update(r.session.id, { candidateEditingEnabled: false });
    await vi.waitFor(() => expect(r.candMsgs.some((m) => m.type === 'session_updated')).toBe(true));
    const op = buildOperation(new LamportClock(r.candRoom.me.id), [node('nope', r.candRoom.me.id)]);
    r.candConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.candMsgs.find((m) => m.type === 'error')).toMatchObject({ code: 'EDIT_LOCKED', opId: op.id }));
    expect(liveElements((await r.owner.canvas.openRoom(r.session.id)).canvas)).toEqual([]);
  });

  it('rejects operations that impersonate another participant', async () => {
    const r = await liveRoom();
    const op = buildOperation(new LamportClock(r.ownerRoom.me.id), [node('spoof', r.ownerRoom.me.id)]);
    r.candConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.candMsgs.find((m) => m.type === 'error')).toMatchObject({ code: 'FORBIDDEN' }));
  });

  it('observers cannot edit', async () => {
    const r = await liveRoom();
    const { token } = await r.owner.sessions.createGuestLink(r.session.id, { roleGranted: 'observer' });
    const observer = r.world.client();
    await observer.join.join(token, 'Watcher');
    const room = await observer.canvas.openRoom(r.session.id);
    expect(room.permissions.canEdit).toBe(false);
    const conn = observer.realtime.connect(r.session.id);
    const msgs = await open(conn);
    conn.send({ type: 'document_update', op: buildOperation(new LamportClock(room.me.id), [node('o', room.me.id)]) });
    await vi.waitFor(() => expect(msgs.find((m) => m.type === 'error')).toMatchObject({ code: 'FORBIDDEN' }));
  });

  it('broadcasts presence and session lifecycle events', async () => {
    const r = await liveRoom();
    r.candConn.send({
      type: 'presence_update',
      presence: {
        participantId: 'ignored',
        displayName: 'Linus',
        color: '#000',
        role: 'candidate',
        cursor: { x: 10, y: 20 },
        selection: [],
        ts: Date.now(),
      },
    });
    await vi.waitFor(() =>
      expect(r.ownerMsgs.find((m) => m.type === 'presence_update')).toMatchObject({
        presence: { participantId: r.candRoom.me.id, cursor: { x: 10, y: 20 } },
      }),
    );
    await r.owner.sessions.end(r.session.id);
    await vi.waitFor(() => expect(r.candMsgs.some((m) => m.type === 'session_ended')).toBe(true));
    const op = buildOperation(new LamportClock(r.ownerRoom.me.id), [node('late', r.ownerRoom.me.id)]);
    r.ownerConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.ownerMsgs.find((m) => m.type === 'error')).toMatchObject({ code: 'SESSION_ENDED' }));
  });

  it('notifies a removed participant', async () => {
    const r = await liveRoom();
    await r.owner.sessions.removeParticipant(r.session.id, r.candRoom.me.id);
    await vi.waitFor(() =>
      expect(r.candMsgs.find((m) => m.type === 'participant_removed')).toMatchObject({ participantId: r.candRoom.me.id }),
    );
  });

  it('goes offline and reconnects when the network returns', async () => {
    const r = await liveRoom();
    const statuses: string[] = [];
    r.candConn.onStatus((s) => statuses.push(s));
    r.candidate.network.set(false);
    expect(r.candConn.status).toBe('offline');
    expect(() => r.candConn.send({ type: 'ping' })).toThrow();
    // Updates made while offline are not delivered…
    const op = buildOperation(new LamportClock(r.ownerRoom.me.id), [node('while-offline', r.ownerRoom.me.id)]);
    r.ownerConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.ownerMsgs.some((m) => m.type === 'document_ack')).toBe(true));
    expect(r.candMsgs.some((m) => m.type === 'document_update')).toBe(false);
    // …but after reconnecting the client is told to resync and the snapshot has them.
    r.candidate.network.set(true);
    await vi.waitFor(() => expect(r.candConn.status).toBe('connected'));
    expect(statuses).toEqual(['offline', 'reconnecting', 'connected']);
    await vi.waitFor(() => expect(r.candMsgs.filter((m) => m.type === 'room_joined')).toHaveLength(2));
    const room = await r.candidate.canvas.openRoom(r.session.id);
    expect(liveElements(room.canvas).map((e) => e.id)).toEqual(['while-offline']);
  });

  it('clears the canvas keeping a restorable snapshot', async () => {
    const r = await liveRoom();
    const op = buildOperation(new LamportClock(r.ownerRoom.me.id), [node('keep', r.ownerRoom.me.id)]);
    r.ownerConn.send({ type: 'document_update', op });
    await vi.waitFor(() => expect(r.ownerMsgs.some((m) => m.type === 'document_ack')).toBe(true));
    await r.owner.sessions.clearCanvas(r.session.id);
    await vi.waitFor(() => expect(r.candMsgs.some((m) => m.type === 'canvas_reset')).toBe(true));
    expect(liveElements((await r.owner.canvas.openRoom(r.session.id)).canvas)).toEqual([]);
    const [snap] = await r.owner.sessions.listSnapshots(r.session.id);
    expect(snap.reason).toBe('before-clear');
    await r.owner.sessions.restoreSnapshot(r.session.id, snap.id);
    expect(liveElements((await r.owner.canvas.openRoom(r.session.id)).canvas).map((e) => e.id)).toEqual(['keep']);
  });
});

describe('multi-tab identity', () => {
  it('the owner can open the candidate link in another tab and join as a guest', async () => {
    const { world, owner, session, token } = await setupInterview();
    // Same browser (shares the auth "cookie"), different tab.
    const secondTab = world.client({ storage: owner.browserStorage });
    await secondTab.join.join(token, 'Test candidate');
    expect((await secondTab.canvas.openRoom(session.id)).me.role).toBe('candidate');
    expect((await owner.canvas.openRoom(session.id)).me.role).toBe('owner');
  });

  it('memory storage helper is isolated per instance', () => {
    const a = createMemoryStorage();
    a.setItem('k', 'v');
    expect(createMemoryStorage().getItem('k')).toBeNull();
  });
});
