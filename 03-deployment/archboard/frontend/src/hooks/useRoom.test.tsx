import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createShape } from '../canvas/editing';
import type { ShapeElement } from '../canvas/types';
import { withBackend } from '../test/render';
import { createWorld, signIn } from '../test/world';
import { useRoom } from './useRoom';

async function setup() {
  const world = createWorld();
  const owner = world.client();
  await signIn(owner);
  const session = await owner.sessions.create({ title: 'Hook test' });
  await owner.sessions.start(session.id);
  const { token } = await owner.sessions.createGuestLink(session.id);
  const candidate = world.client();
  await candidate.join.join(token, 'Linus');

  const a = renderHook(() => useRoom(session.id), { wrapper: withBackend(owner) });
  const b = renderHook(() => useRoom(session.id), { wrapper: withBackend(candidate) });
  await waitFor(() => expect(a.result.current.status).toBe('connected'));
  await waitFor(() => expect(b.result.current.status).toBe('connected'));
  return { world, owner, candidate, session, a, b };
}

describe('useRoom', () => {
  it('loads the room with identity and permissions', async () => {
    const { a, b } = await setup();
    expect(a.result.current.me?.role).toBe('owner');
    expect(b.result.current.me?.role).toBe('candidate');
    expect(b.result.current.permissions?.canEdit).toBe(true);
    expect(b.result.current.permissions?.canShare).toBe(false);
  });

  it('syncs local edits to other participants', async () => {
    const { a, b } = await setup();
    const shape = createShape('server', { x: 0, y: 0 }, a.result.current.me!.id, 1);
    act(() => a.result.current.commit([shape]));
    expect(a.result.current.elements).toHaveLength(1);
    await waitFor(() => expect(b.result.current.elements.map((e) => e.id)).toEqual([shape.id]));
    await waitFor(() => expect(a.result.current.pendingCount).toBe(0));
  });

  it('undo and redo only affect the local participant’s own changes', async () => {
    const { a, b } = await setup();
    const mine = createShape('server', { x: 0, y: 0 }, a.result.current.me!.id, 1);
    const theirs = createShape('cache', { x: 300, y: 0 }, b.result.current.me!.id, 2);
    act(() => a.result.current.commit([mine]));
    act(() => b.result.current.commit([theirs]));
    await waitFor(() => expect(a.result.current.elements).toHaveLength(2));
    act(() => a.result.current.undo());
    await waitFor(() => expect(b.result.current.elements.map((e) => e.id)).toEqual([theirs.id]));
    expect(a.result.current.canRedo).toBe(true);
    act(() => a.result.current.redo());
    await waitFor(() => expect(b.result.current.elements).toHaveLength(2));
  });

  it('records a gesture as a single undo step', async () => {
    const { a } = await setup();
    const s = createShape('server', { x: 0, y: 0 }, a.result.current.me!.id, 1);
    act(() => a.result.current.commit([s]));
    act(() => a.result.current.beginGesture());
    for (let i = 1; i <= 5; i++) {
      const current = a.result.current.elements[0] as ShapeElement;
      act(() => a.result.current.commit([{ ...current, x: current.x + 10 }]));
    }
    act(() => a.result.current.endGesture());
    expect((a.result.current.elements[0] as ShapeElement).x).toBe(s.x + 50);
    act(() => a.result.current.undo());
    expect((a.result.current.elements[0] as ShapeElement).x).toBe(s.x);
  });

  it('queues edits while offline and converges after reconnecting', async () => {
    const { a, b, candidate } = await setup();
    act(() => candidate.network.set(false));
    await waitFor(() => expect(b.result.current.status).toBe('offline'));
    const offlineEdit = createShape('queue', { x: 0, y: 0 }, b.result.current.me!.id, 1);
    act(() => b.result.current.commit([offlineEdit]));
    expect(b.result.current.pendingCount).toBe(1);
    const ownerEdit = createShape('cdn', { x: 200, y: 0 }, a.result.current.me!.id, 2);
    act(() => a.result.current.commit([ownerEdit]));
    await waitFor(() => expect(a.result.current.pendingCount).toBe(0));
    expect(a.result.current.elements).toHaveLength(1);

    act(() => candidate.network.set(true));
    await waitFor(() => expect(b.result.current.status).toBe('connected'));
    const ids = [offlineEdit.id, ownerEdit.id].sort();
    await waitFor(() => expect(b.result.current.elements.map((e) => e.id).sort()).toEqual(ids));
    await waitFor(() => expect(a.result.current.elements.map((e) => e.id).sort()).toEqual(ids));
    expect(b.result.current.pendingCount).toBe(0);
  });

  it('blocks candidate edits when locked and reflects it in permissions', async () => {
    const { a, b, owner, session } = await setup();
    await act(async () => {
      a.result.current.setSession(await owner.sessions.update(session.id, { candidateEditingEnabled: false }));
    });
    await waitFor(() => expect(b.result.current.permissions?.canEdit).toBe(false));
    const s = createShape('server', { x: 0, y: 0 }, b.result.current.me!.id, 1);
    act(() => b.result.current.commit([s]));
    expect(b.result.current.elements).toHaveLength(0);
  });

  it('rolls back to the server state when an edit is rejected', async () => {
    const { b, owner, session } = await setup();
    // Lock on the server without the client knowing yet: the optimistic edit must be rolled back.
    owner.db.sessions.put(session.id, { ...owner.db.sessions.get(session.id)!, candidateEditingEnabled: false });
    const s = createShape('server', { x: 0, y: 0 }, b.result.current.me!.id, 1);
    act(() => b.result.current.commit([s]));
    expect(b.result.current.elements).toHaveLength(1);
    await waitFor(() => expect(b.result.current.elements).toHaveLength(0));
    expect(b.result.current.notices.some((n) => /locked/i.test(n.text))).toBe(true);
  });

  it('shows remote presence and handles removal', async () => {
    const { a, b, owner, session } = await setup();
    act(() => b.result.current.updatePresence({ cursor: { x: 5, y: 6 }, selection: [] }));
    await waitFor(() => expect(a.result.current.presence[0]?.cursor).toEqual({ x: 5, y: 6 }));
    expect(a.result.current.presence[0].displayName).toBe('Linus');
    await act(async () => owner.sessions.removeParticipant(session.id, b.result.current.me!.id));
    await waitFor(() => expect(b.result.current.removed).toBe(true));
  });

  it('marks the room read-only when the session ends', async () => {
    const { a, b, owner, session } = await setup();
    await act(async () => {
      a.result.current.setSession(await owner.sessions.end(session.id));
    });
    await waitFor(() => expect(b.result.current.session?.state).toBe('ended'));
    expect(b.result.current.permissions?.canEdit).toBe(false);
    expect(a.result.current.permissions?.canEdit).toBe(false);
  });
});
