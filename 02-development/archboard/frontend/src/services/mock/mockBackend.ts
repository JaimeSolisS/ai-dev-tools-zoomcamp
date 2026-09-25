/**
 * In-browser implementation of `BackendService`.
 *
 * It behaves like the real backend described in the spec: it authorizes every
 * call, stores only hashes of bearer tokens, validates guest links, persists
 * the canvas and fans real-time messages out to other participants. State is
 * kept in (local)Storage and real-time traffic travels over a `MessageBus`, so
 * the app works across several tabs with no server at all.
 */
import { applyOperation, emptyDoc, isTombstone, LIMITS, newId, validateOperation } from '../../canvas/model';
import type { CanvasDoc, CanvasOperation } from '../../canvas/types';
import type {
  AuthService,
  BackendService,
  CanvasService,
  JoinService,
  RealtimeConnection,
  RealtimeService,
  SessionService,
} from '../api';
import { ApiError } from '../errors';
import { computePermissions } from '../permissions';
import {
  PROTOCOL_VERSION,
  type ClientMessage,
  type ConnectionStatus,
  type CreatedGuestLink,
  type CreateGuestLinkInput,
  type CreateSessionInput,
  type Envelope,
  type GuestLink,
  type InterviewSession,
  type JoinInfo,
  type Participant,
  type Role,
  type ServerMessage,
  type SessionSummary,
  type UpdateSessionInput,
  type User,
} from '../types';
import { createInProcessBus, type MessageBus } from './bus';
import { randomToken, sha256 } from './crypto';
import { MockDatabase, type StoredCanvas, type StoredGuestLink, type StoredParticipant, type StoredSnapshot } from './db';
import { seedExampleSession } from './seed';
import { browserNetworkMonitor, type NetworkMonitor } from '../network';
import { createMemoryStorage, type KeyValueStorage } from './storage';

export { browserNetworkMonitor, controllableNetwork, type NetworkMonitor } from '../network';

export const MAX_PARTICIPANTS = 10;
const ACTIVE_WINDOW_MS = 30_000;
const SNAPSHOT_EVERY_OPS = 200;
const PARTICIPANT_COLORS = ['#2563eb', '#db2777', '#059669', '#d97706', '#7c3aed', '#0891b2', '#dc2626', '#4f46e5', '#65a30d', '#c026d3'];

const AUTH_KEY = 'archboard:auth';
const guestKey = (sessionId: string) => `archboard:guest:${sessionId}`;

export interface MockBackendOptions {
  /** "Server" database storage. Shared by every simulated client. */
  serverStorage?: KeyValueStorage;
  /** Per-browser storage holding the interviewer's auth token (a cookie jar). */
  browserStorage?: KeyValueStorage;
  /** Per-tab storage holding guest credentials. */
  tabStorage?: KeyValueStorage;
  bus?: MessageBus;
  latencyMs?: number;
  network?: NetworkMonitor;
  now?: () => Date;
  /** Create an example session for new users (default true). */
  seedExamples?: boolean;
}

type Principal = { user: User | null; participant: StoredParticipant };

export interface MockBackend extends BackendService {
  readonly kind: 'mock';
  /** Test/dev helper: direct database access. */
  readonly db: MockDatabase;
}

export function createMockBackend(options: MockBackendOptions = {}): MockBackend {
  const serverStorage = options.serverStorage ?? createMemoryStorage();
  const browserStorage = options.browserStorage ?? createMemoryStorage();
  const tabStorage = options.tabStorage ?? createMemoryStorage();
  const bus = options.bus ?? createInProcessBus();
  const latency = options.latencyMs ?? 0;
  const network = options.network ?? browserNetworkMonitor();
  const now = options.now ?? (() => new Date());
  const seedExamples = options.seedExamples ?? true;
  const db = new MockDatabase(serverStorage);

  const iso = () => now().toISOString();
  const delay = (ms = latency) => (ms > 0 ? new Promise<void>((r) => setTimeout(r, ms)) : Promise.resolve());
  /** Run a request handler after simulated network latency. */
  async function request<T>(handler: () => Promise<T> | T): Promise<T> {
    await delay();
    const result = await handler();
    return result === undefined ? result : structuredClone(result);
  }

  function publish(sessionId: string, payload: ServerMessage, origin: string | null = null) {
    bus.publish({ sessionId, origin, payload });
  }

  // ------------------------------------------------------------------ auth --

  async function currentUser(): Promise<User | null> {
    const token = browserStorage.getItem(AUTH_KEY);
    if (!token) return null;
    const userId = db.authTokens.get(await sha256(token));
    return (userId && db.users.get(userId)) || null;
  }

  async function requireUser(): Promise<User> {
    const user = await currentUser();
    if (!user) throw new ApiError('UNAUTHENTICATED', 'Please sign in to continue.');
    return user;
  }

  function getSessionOr404(id: string): InterviewSession {
    const session = db.sessions.get(id);
    if (!session) throw new ApiError('NOT_FOUND', 'Interview not found.');
    return session;
  }

  /** Owner-only access. Non-owners get NOT_FOUND so ids cannot be probed. */
  async function requireOwner(sessionId: string): Promise<{ user: User; session: InterviewSession }> {
    const user = await requireUser();
    const session = getSessionOr404(sessionId);
    if (session.ownerUserId !== user.id) throw new ApiError('NOT_FOUND', 'Interview not found.');
    return { user, session };
  }

  function nextColor(sessionId: string): string {
    const used = db.participants.values().filter((p) => p.sessionId === sessionId).length;
    return PARTICIPANT_COLORS[used % PARTICIPANT_COLORS.length];
  }

  function createParticipant(input: {
    sessionId: string;
    userId: string | null;
    displayName: string;
    role: Role;
    credentialHash: string | null;
  }): StoredParticipant {
    const participant: StoredParticipant = {
      id: newId('p'),
      sessionId: input.sessionId,
      userId: input.userId,
      displayName: input.displayName,
      role: input.role,
      color: input.role === 'owner' ? PARTICIPANT_COLORS[0] : nextColor(input.sessionId),
      joinedAt: iso(),
      leftAt: null,
      removedAt: null,
      lastSeenAt: iso(),
      credentialHash: input.credentialHash,
    };
    return db.participants.put(participant.id, participant);
  }

  /** Resolve who is calling for a given session: a guest credential (this tab) or the signed-in user. */
  async function resolvePrincipal(sessionId: string): Promise<Principal> {
    const session = getSessionOr404(sessionId);
    const credential = tabStorage.getItem(guestKey(sessionId));
    if (credential) {
      const hash = await sha256(credential);
      const participant = db.participants.values().find((p) => p.sessionId === sessionId && p.credentialHash === hash);
      if (participant) {
        if (participant.removedAt) throw new ApiError('PARTICIPANT_REMOVED', 'You were removed from this interview.');
        return { user: null, participant };
      }
      tabStorage.removeItem(guestKey(sessionId));
    }
    const user = await currentUser();
    if (!user) throw new ApiError('UNAUTHENTICATED', 'Join this interview through its invitation link.');
    const mine = db.participants.values().find((p) => p.sessionId === sessionId && p.userId === user.id && !p.credentialHash);
    if (session.ownerUserId === user.id) {
      return {
        user,
        participant:
          mine ??
          createParticipant({ sessionId, userId: user.id, displayName: user.displayName, role: 'owner', credentialHash: null }),
      };
    }
    if (mine && !mine.removedAt) return { user, participant: mine };
    throw new ApiError('NOT_FOUND', 'Interview not found.');
  }

  function toParticipant(p: StoredParticipant): Participant {
    const { credentialHash: _hidden, ...rest } = p;
    void _hidden;
    return rest;
  }

  function toGuestLink(l: StoredGuestLink): GuestLink {
    const { tokenHash: _hidden, ...rest } = l;
    void _hidden;
    return rest;
  }

  function linkActive(l: StoredGuestLink): boolean {
    return !l.revokedAt && !(l.expiresAt && new Date(l.expiresAt) <= now()) && !(l.maxUses != null && l.uses >= l.maxUses);
  }

  function ensureCanvas(sessionId: string): StoredCanvas {
    return (
      db.canvases.get(sessionId) ??
      db.canvases.put(sessionId, { sessionId, doc: emptyDoc(), cursor: 0, recentOpIds: [], updatedAt: iso() })
    );
  }

  function saveSnapshot(sessionId: string, reason: StoredSnapshot['reason']): StoredSnapshot {
    const canvas = ensureCanvas(sessionId);
    const snapshot: StoredSnapshot = {
      id: newId('snap'),
      sessionId,
      reason,
      operationCursor: canvas.cursor,
      elementCount: Object.values(canvas.doc.elements).filter((e) => !isTombstone(e)).length,
      createdAt: iso(),
      doc: canvas.doc,
    };
    return db.snapshots.put(snapshot.id, snapshot);
  }

  function touchSession(session: InterviewSession, patch: Partial<InterviewSession>): InterviewSession {
    const next = { ...session, ...patch, updatedAt: iso() };
    db.sessions.put(next.id, next);
    return next;
  }

  function audit(sessionId: string, actor: string, action: string, details?: Record<string, unknown>) {
    db.audit({ id: newId('audit'), sessionId, actor, action, at: iso(), details });
  }

  const auth: AuthService = {
    getCurrentUser: () => request(currentUser),

    requestMagicLink: (email) =>
      request(async () => {
        const normalized = email.trim().toLowerCase();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) throw new ApiError('VALIDATION', 'Enter a valid email address.');
        const token = randomToken();
        db.magicLinks.put(await sha256(token), {
          email: normalized,
          expiresAt: new Date(now().getTime() + 15 * 60_000).toISOString(),
        });
        return { sent: true as const, devToken: token };
      }),

    verifyMagicLink: (token) =>
      request(async () => {
        const hash = await sha256(token);
        const link = db.magicLinks.get(hash);
        if (!link || new Date(link.expiresAt) <= now()) throw new ApiError('LINK_INVALID', 'This sign-in link is invalid or has expired.');
        db.magicLinks.delete(hash);
        let user = db.users.values().find((u) => u.email === link.email);
        if (!user) {
          const id = newId('u');
          const local = link.email.split('@')[0];
          user = db.users.put(id, {
            id,
            email: link.email,
            displayName: local.charAt(0).toUpperCase() + local.slice(1),
            organizationId: null,
            createdAt: iso(),
          });
          if (seedExamples) seedExampleSession(db, user, iso());
        }
        const sessionToken = randomToken();
        db.authTokens.put(await sha256(sessionToken), user.id);
        browserStorage.setItem(AUTH_KEY, sessionToken);
        return user;
      }),

    signOut: () =>
      request(async () => {
        const token = browserStorage.getItem(AUTH_KEY);
        if (token) db.authTokens.delete(await sha256(token));
        browserStorage.removeItem(AUTH_KEY);
      }),
  };

  // -------------------------------------------------------------- sessions --

  function summarize(session: InterviewSession): SessionSummary {
    const participants = db.participants.values().filter((p) => p.sessionId === session.id && !p.removedAt);
    const canvas = db.canvases.get(session.id);
    const active = db.guestLinks
      .values()
      .filter((l) => l.sessionId === session.id && l.roleGranted === 'candidate' && linkActive(l))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
    const lastModifiedAt = [session.updatedAt, canvas?.updatedAt].filter(Boolean).sort().at(-1)!;
    return {
      ...session,
      participantNames: participants.filter((p) => p.role !== 'owner').map((p) => p.displayName),
      lastModifiedAt,
      activeGuestLink: active ? toGuestLink(active) : null,
    };
  }

  function validateTitle(title: string): string {
    const t = title.trim();
    if (!t) throw new ApiError('VALIDATION', 'Title is required.');
    if (t.length > 120) throw new ApiError('VALIDATION', 'Title must be at most 120 characters.');
    return t;
  }

  function validateDuration(minutes: number | null | undefined): number | null {
    if (minutes == null) return null;
    if (!Number.isFinite(minutes) || minutes < 5 || minutes > 480) throw new ApiError('VALIDATION', 'Duration must be between 5 and 480 minutes.');
    return Math.round(minutes);
  }

  function newSession(owner: User, input: CreateSessionInput): InterviewSession {
    const t = iso();
    const session: InterviewSession = {
      id: newId('s'),
      ownerUserId: owner.id,
      title: validateTitle(input.title),
      prompt: (input.prompt ?? '').slice(0, LIMITS.maxTextLength * 5),
      state: 'draft',
      candidateEditingEnabled: true,
      showCursors: true,
      durationMinutes: validateDuration(input.durationMinutes),
      scheduledAt: input.scheduledAt ?? null,
      startedAt: null,
      endedAt: null,
      createdAt: t,
      updatedAt: t,
    };
    return db.sessions.put(session.id, session);
  }

  function copyCanvas(fromSessionId: string, toSessionId: string) {
    const source = db.canvases.get(fromSessionId);
    const doc: CanvasDoc = source ? structuredClone(source.doc) : emptyDoc();
    db.canvases.put(toSessionId, { sessionId: toSessionId, doc, cursor: 0, recentOpIds: [], updatedAt: iso() });
  }

  const sessions: SessionService = {
    list: () =>
      request(async () => {
        const user = await requireUser();
        const invited = new Set(
          db.participants
            .values()
            .filter((p) => p.userId === user.id && !p.removedAt)
            .map((p) => p.sessionId),
        );
        return db.sessions
          .values()
          .filter((s) => s.ownerUserId === user.id || invited.has(s.id))
          .map(summarize)
          .sort((a, b) => b.lastModifiedAt.localeCompare(a.lastModifiedAt));
      }),

    create: (input) =>
      request(async () => {
        const user = await requireUser();
        if (input.templateSessionId) await requireOwner(input.templateSessionId);
        const session = newSession(user, input);
        if (input.templateSessionId) copyCanvas(input.templateSessionId, session.id);
        else ensureCanvas(session.id);
        audit(session.id, user.id, 'session.created');
        return session;
      }),

    get: (id) =>
      request(async () => {
        await resolvePrincipal(id);
        return getSessionOr404(id);
      }),

    update: (id, patch) =>
      request(async () => {
        const { participant } = await resolvePrincipal(id);
        const session = getSessionOr404(id);
        const perms = computePermissions(participant.role, session);
        const settingsKeys: (keyof UpdateSessionInput)[] = ['title', 'prompt', 'durationMinutes', 'scheduledAt', 'showCursors'];
        const touchesSettings = settingsKeys.some((k) => k in patch);
        if (touchesSettings && !perms.canEditSettings) throw new ApiError('FORBIDDEN', 'Only the owner can change interview settings.');
        if ('candidateEditingEnabled' in patch && !perms.canLockEditing) throw new ApiError('FORBIDDEN', 'You cannot change editing permissions.');
        const next: Partial<InterviewSession> = {};
        if (patch.title !== undefined) next.title = validateTitle(patch.title);
        if (patch.prompt !== undefined) next.prompt = patch.prompt;
        if (patch.durationMinutes !== undefined) next.durationMinutes = validateDuration(patch.durationMinutes);
        if (patch.scheduledAt !== undefined) next.scheduledAt = patch.scheduledAt;
        if (patch.showCursors !== undefined) next.showCursors = patch.showCursors;
        if (patch.candidateEditingEnabled !== undefined) next.candidateEditingEnabled = patch.candidateEditingEnabled;
        const updated = touchSession(session, next);
        if ('candidateEditingEnabled' in patch) {
          audit(id, participant.id, 'permissions.changed', { candidateEditingEnabled: updated.candidateEditingEnabled });
        }
        publish(id, { type: 'session_updated', session: updated });
        return updated;
      }),

    start: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (session.state !== 'draft') throw new ApiError('CONFLICT', 'Only draft interviews can be started.');
        const updated = touchSession(session, { state: 'live', startedAt: iso() });
        audit(id, user.id, 'session.started');
        publish(id, { type: 'session_updated', session: updated });
        return updated;
      }),

    end: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (session.state !== 'live' && session.state !== 'draft') throw new ApiError('CONFLICT', 'This interview is not running.');
        saveSnapshot(id, 'final');
        const updated = touchSession(session, { state: 'ended', endedAt: iso() });
        audit(id, user.id, 'session.ended');
        publish(id, { type: 'session_ended', session: updated });
        return updated;
      }),

    reopen: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (session.state !== 'ended') throw new ApiError('CONFLICT', 'Only ended interviews can be reopened.');
        const updated = touchSession(session, { state: 'live', endedAt: null });
        audit(id, user.id, 'session.reopened');
        publish(id, { type: 'session_updated', session: updated });
        return updated;
      }),

    archive: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (session.state === 'live') saveSnapshot(id, 'final');
        const updated = touchSession(session, {
          state: 'archived',
          endedAt: session.endedAt ?? (session.state === 'live' ? iso() : null),
        });
        audit(id, user.id, 'session.archived');
        publish(id, { type: 'session_ended', session: updated });
        return updated;
      }),

    duplicate: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        const copy = newSession(user, {
          title: `${session.title} (copy)`.slice(0, 120),
          prompt: session.prompt,
          durationMinutes: session.durationMinutes,
        });
        copyCanvas(id, copy.id);
        audit(copy.id, user.id, 'session.created', { duplicatedFrom: id });
        return copy;
      }),

    listParticipants: (id) =>
      request(async () => {
        await resolvePrincipal(id);
        return db.participants
          .values()
          .filter((p) => p.sessionId === id && !p.removedAt)
          .sort((a, b) => a.joinedAt.localeCompare(b.joinedAt))
          .map(toParticipant);
      }),

    removeParticipant: (id, participantId) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        const p = db.participants.get(participantId);
        if (!p || p.sessionId !== session.id) throw new ApiError('NOT_FOUND', 'Participant not found.');
        if (p.role === 'owner') throw new ApiError('VALIDATION', 'The owner cannot be removed.');
        db.participants.put(p.id, { ...p, removedAt: iso(), leftAt: iso() });
        audit(id, user.id, 'participant.removed', { participantId });
        publish(id, { type: 'participant_removed', participantId });
        publish(id, { type: 'participants_changed' });
      }),

    listGuestLinks: (id) =>
      request(async () => {
        await requireOwner(id);
        return db.guestLinks
          .values()
          .filter((l) => l.sessionId === id)
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
          .map(toGuestLink);
      }),

    createGuestLink: (id, input: CreateGuestLinkInput = {}) =>
      request(async (): Promise<CreatedGuestLink> => {
        const { user, session } = await requireOwner(id);
        if (session.state === 'ended' || session.state === 'archived') {
          throw new ApiError('SESSION_ENDED', 'Reopen the interview before sharing it.');
        }
        const role = input.roleGranted ?? 'candidate';
        if (input.maxUses != null && (!Number.isInteger(input.maxUses) || input.maxUses < 1)) {
          throw new ApiError('VALIDATION', 'Maximum uses must be a positive whole number.');
        }
        if (input.rotate) {
          for (const l of db.guestLinks.values()) {
            if (l.sessionId === id && l.roleGranted === role && !l.revokedAt) {
              db.guestLinks.put(l.id, { ...l, revokedAt: iso() });
            }
          }
        }
        const token = randomToken();
        const link: StoredGuestLink = {
          id: newId('gl'),
          sessionId: id,
          roleGranted: role,
          expiresAt: input.expiresAt ?? null,
          maxUses: input.maxUses ?? null,
          uses: 0,
          revokedAt: null,
          createdAt: iso(),
          tokenHash: await sha256(token),
        };
        db.guestLinks.put(link.id, link);
        audit(id, user.id, input.rotate ? 'link.rotated' : 'link.created', { linkId: link.id, role });
        return { link: toGuestLink(link), token };
      }),

    revokeGuestLink: (id, linkId) =>
      request(async () => {
        const { user } = await requireOwner(id);
        const link = db.guestLinks.get(linkId);
        if (!link || link.sessionId !== id) throw new ApiError('NOT_FOUND', 'Link not found.');
        if (!link.revokedAt) db.guestLinks.put(linkId, { ...link, revokedAt: iso() });
        audit(id, user.id, 'link.revoked', { linkId });
      }),

    clearCanvas: (id) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (!computePermissions('owner', session).canClearCanvas) throw new ApiError('SESSION_ENDED', 'This interview has ended.');
        saveSnapshot(id, 'before-clear');
        const canvas = ensureCanvas(id);
        db.canvases.put(id, { ...canvas, doc: emptyDoc(), cursor: canvas.cursor + 1, recentOpIds: [], updatedAt: iso() });
        audit(id, user.id, 'canvas.cleared');
        publish(id, { type: 'canvas_reset' });
      }),

    listSnapshots: (id) =>
      request(async () => {
        await requireOwner(id);
        return db.snapshots
          .values()
          .filter((s) => s.sessionId === id)
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
          .map(({ doc: _doc, ...info }) => {
            void _doc;
            return info;
          });
      }),

    restoreSnapshot: (id, snapshotId) =>
      request(async () => {
        const { user, session } = await requireOwner(id);
        if (!computePermissions('owner', session).canClearCanvas) throw new ApiError('SESSION_ENDED', 'This interview has ended.');
        const snapshot = db.snapshots.get(snapshotId);
        if (!snapshot || snapshot.sessionId !== id) throw new ApiError('NOT_FOUND', 'Snapshot not found.');
        saveSnapshot(id, 'before-restore');
        const canvas = ensureCanvas(id);
        db.canvases.put(id, { ...canvas, doc: snapshot.doc, cursor: canvas.cursor + 1, recentOpIds: [], updatedAt: iso() });
        audit(id, user.id, 'canvas.restored', { snapshotId });
        publish(id, { type: 'canvas_reset' });
      }),
  };

  // ------------------------------------------------------------------ join --

  async function findLink(token: string): Promise<{ link: StoredGuestLink; session: InterviewSession }> {
    const hash = await sha256(token);
    const link = db.guestLinks.values().find((l) => l.tokenHash === hash);
    if (!link) throw new ApiError('LINK_INVALID', 'This invitation link is not valid.');
    const session = db.sessions.get(link.sessionId);
    if (!session) throw new ApiError('LINK_INVALID', 'This invitation link is not valid.');
    return { link, session };
  }

  function assertJoinable(link: StoredGuestLink, session: InterviewSession, returning: boolean) {
    if (session.state === 'archived') throw new ApiError('SESSION_ARCHIVED', 'This interview has been archived.');
    if (session.state === 'ended') throw new ApiError('SESSION_ENDED', 'This interview has already ended.');
    if (link.revokedAt) throw new ApiError('LINK_REVOKED', 'This invitation link has been revoked. Ask your interviewer for a new one.');
    if (link.expiresAt && new Date(link.expiresAt) <= now()) throw new ApiError('LINK_EXPIRED', 'This invitation link has expired.');
    if (!returning && link.maxUses != null && link.uses >= link.maxUses) {
      throw new ApiError('LINK_EXHAUSTED', 'This invitation link has already been used.');
    }
  }

  function activeParticipantCount(sessionId: string): number {
    const cutoff = now().getTime() - ACTIVE_WINDOW_MS;
    return db.participants
      .values()
      .filter((p) => p.sessionId === sessionId && !p.removedAt && !p.leftAt && p.lastSeenAt && new Date(p.lastSeenAt).getTime() >= cutoff)
      .length;
  }

  const join: JoinService = {
    getInfo: (token) =>
      request(async (): Promise<JoinInfo> => {
        const { link, session } = await findLink(token);
        assertJoinable(link, session, false);
        return { sessionTitle: session.title, sessionState: session.state, roleGranted: link.roleGranted };
      }),

    join: (token, displayName) =>
      request(async () => {
        const name = displayName.trim();
        if (!name) throw new ApiError('VALIDATION', 'Please enter your name.');
        if (name.length > 60) throw new ApiError('VALIDATION', 'Name must be at most 60 characters.');
        const { link, session } = await findLink(token);

        // Reconnect: this tab already holds a valid credential for the session.
        const existingCredential = tabStorage.getItem(guestKey(session.id));
        if (existingCredential) {
          const hash = await sha256(existingCredential);
          const existing = db.participants.values().find((p) => p.sessionId === session.id && p.credentialHash === hash);
          if (existing?.removedAt) throw new ApiError('PARTICIPANT_REMOVED', 'You were removed from this interview.');
          if (existing) {
            assertJoinable(link, session, true);
            const updated = db.participants.put(existing.id, { ...existing, displayName: name, leftAt: null, lastSeenAt: iso() });
            publish(session.id, { type: 'participants_changed' });
            return { sessionId: session.id, participant: toParticipant(updated) };
          }
        }

        assertJoinable(link, session, false);
        if (activeParticipantCount(session.id) >= MAX_PARTICIPANTS) {
          throw new ApiError('SESSION_FULL', `This interview already has ${MAX_PARTICIPANTS} participants.`);
        }
        const credential = randomToken();
        const user = link.roleGranted === 'interviewer' || link.roleGranted === 'observer' ? await currentUser() : null;
        const participant = createParticipant({
          sessionId: session.id,
          userId: user?.id ?? null,
          displayName: name,
          role: link.roleGranted,
          credentialHash: await sha256(credential),
        });
        db.guestLinks.put(link.id, { ...link, uses: link.uses + 1 });
        tabStorage.setItem(guestKey(session.id), credential);
        audit(session.id, participant.id, 'participant.joined', { role: participant.role });
        publish(session.id, { type: 'participants_changed' });
        return { sessionId: session.id, participant: toParticipant(participant) };
      }),
  };

  // ---------------------------------------------------------------- canvas --

  const canvas: CanvasService = {
    openRoom: (sessionId) =>
      request(async () => {
        const { participant } = await resolvePrincipal(sessionId);
        const session = getSessionOr404(sessionId);
        const permissions = computePermissions(participant.role, session);
        if (!permissions.canView) {
          if (session.state === 'ended') throw new ApiError('SESSION_ENDED', 'This interview has ended.');
          if (session.state === 'archived') throw new ApiError('SESSION_ARCHIVED', 'This interview has been archived.');
          throw new ApiError('FORBIDDEN', 'You do not have access to this interview.');
        }
        const record = ensureCanvas(sessionId);
        const participants = db.participants
          .values()
          .filter((p) => p.sessionId === sessionId && !p.removedAt)
          .sort((a, b) => a.joinedAt.localeCompare(b.joinedAt))
          .map(toParticipant);
        return {
          session,
          me: toParticipant(participant),
          participants,
          canvas: record.doc,
          cursor: record.cursor,
          permissions,
        };
      }),
  };

  // -------------------------------------------------------------- realtime --

  /** Server-side handling of a persistent update; returns the message for the sender. */
  async function handleDocumentUpdate(sessionId: string, connectionId: string, op: CanvasOperation): Promise<ServerMessage> {
    let participant: StoredParticipant;
    try {
      participant = (await resolvePrincipal(sessionId)).participant;
    } catch (err) {
      const e = err as ApiError;
      return { type: 'error', code: e.code ?? 'FORBIDDEN', message: e.message, opId: op.id };
    }
    const session = getSessionOr404(sessionId);
    const perms = computePermissions(participant.role, session);
    if (!perms.canEdit) {
      if (session.state === 'ended' || session.state === 'archived') {
        return { type: 'error', code: 'SESSION_ENDED', message: 'The interview has ended; the canvas is read-only.', opId: op.id };
      }
      if (participant.role === 'candidate' && session.state === 'live') {
        return { type: 'error', code: 'EDIT_LOCKED', message: 'The interviewer has locked editing.', opId: op.id };
      }
      return { type: 'error', code: 'FORBIDDEN', message: 'You cannot edit this canvas.', opId: op.id };
    }
    if (op.actorId !== participant.id) {
      return { type: 'error', code: 'FORBIDDEN', message: 'Operation actor does not match the connection.', opId: op.id };
    }
    const invalid = validateOperation(op);
    if (invalid) return { type: 'error', code: 'VALIDATION', message: invalid, opId: op.id };

    const record = ensureCanvas(sessionId);
    if (record.recentOpIds.includes(op.id)) return { type: 'document_ack', opId: op.id, cursor: record.cursor };
    const doc = applyOperation(record.doc, op);
    if (Object.keys(doc.elements).length > LIMITS.maxElements) {
      return { type: 'error', code: 'VALIDATION', message: 'The canvas has too many elements.', opId: op.id };
    }
    const cursor = record.cursor + 1;
    db.canvases.put(sessionId, {
      ...record,
      doc,
      cursor,
      recentOpIds: [...record.recentOpIds, op.id].slice(-500),
      updatedAt: iso(),
    });
    if (cursor % SNAPSHOT_EVERY_OPS === 0) saveSnapshot(sessionId, 'periodic');
    publish(sessionId, { type: 'document_update', op, cursor }, connectionId);
    return { type: 'document_ack', opId: op.id, cursor };
  }

  class MockConnection implements RealtimeConnection {
    readonly id = newId('conn');
    status: ConnectionStatus = 'connecting';
    private messageListeners = new Set<(m: ServerMessage) => void>();
    private statusListeners = new Set<(s: ConnectionStatus) => void>();
    private offBus: (() => void) | null = null;
    private offNetwork: () => void;
    private participantId: string | null = null;
    private lastSeenWrite = 0;
    private closed = false;

    constructor(private sessionId: string) {
      this.offNetwork = network.subscribe((online) => (online ? void this.establish('reconnecting') : this.goOffline()));
      if (network.isOnline()) void this.establish('connecting');
      else this.setStatus('offline');
    }

    private setStatus(status: ConnectionStatus) {
      if (this.status === status) return;
      this.status = status;
      this.statusListeners.forEach((l) => l(status));
    }

    private emit(message: ServerMessage) {
      if (this.closed || this.status !== 'connected') return;
      const envelope: Envelope<ServerMessage> = { ...message, v: PROTOCOL_VERSION, sessionId: this.sessionId, id: newId('m') };
      const copy = structuredClone(envelope);
      setTimeout(() => {
        if (!this.closed && this.status === 'connected') this.messageListeners.forEach((l) => l(copy));
      }, latency / 2);
    }

    private async establish(status: 'connecting' | 'reconnecting') {
      if (this.closed) return;
      this.setStatus(status);
      await delay();
      if (this.closed || !network.isOnline()) return;
      try {
        const { participant } = await resolvePrincipal(this.sessionId);
        this.participantId = participant.id;
      } catch (err) {
        const e = err as ApiError;
        this.setStatus('connected');
        this.emit({ type: 'error', code: e.code ?? 'FORBIDDEN', message: e.message });
        setTimeout(() => this.close(), latency / 2 + 1);
        return;
      }
      this.offBus?.();
      this.offBus = bus.subscribe((m) => {
        if (m.sessionId !== this.sessionId || m.origin === this.id) return;
        this.emit(m.payload as ServerMessage);
      });
      this.setStatus('connected');
      this.emit({ type: 'room_joined', participantId: this.participantId!, cursor: ensureCanvas(this.sessionId).cursor });
    }

    private goOffline() {
      if (this.closed) return;
      this.offBus?.();
      this.offBus = null;
      this.setStatus('offline');
    }

    send(message: ClientMessage): void {
      if (this.closed) throw new Error('Connection is closed');
      if (this.status !== 'connected') throw new Error('Not connected');
      void this.handle(structuredClone(message));
    }

    private async handle(message: ClientMessage) {
      await delay(latency / 2);
      if (this.closed || this.status !== 'connected') return;
      switch (message.type) {
        case 'ping':
          this.emit({ type: 'pong' });
          return;
        case 'presence_update': {
          if (!this.participantId) return;
          const presence = { ...message.presence, participantId: this.participantId };
          publish(this.sessionId, { type: 'presence_update', presence }, this.id);
          const t = now().getTime();
          if (t - this.lastSeenWrite > 10_000) {
            this.lastSeenWrite = t;
            const p = db.participants.get(this.participantId);
            if (p) db.participants.put(p.id, { ...p, lastSeenAt: iso(), leftAt: null });
          }
          return;
        }
        case 'document_update':
          this.emit(await handleDocumentUpdate(this.sessionId, this.id, message.op));
          return;
      }
    }

    onMessage(listener: (m: ServerMessage) => void) {
      this.messageListeners.add(listener);
      return () => void this.messageListeners.delete(listener);
    }

    onStatus(listener: (s: ConnectionStatus) => void) {
      this.statusListeners.add(listener);
      return () => void this.statusListeners.delete(listener);
    }

    close() {
      if (this.closed) return;
      if (this.participantId && this.status === 'connected') {
        publish(this.sessionId, { type: 'presence_leave', participantId: this.participantId }, this.id);
      }
      this.closed = true;
      this.offBus?.();
      this.offNetwork();
      this.setStatus('closed');
    }
  }

  const realtime: RealtimeService = {
    connect: (sessionId) => new MockConnection(sessionId),
  };

  return { kind: 'mock', db, auth, sessions, join, canvas, realtime };
}
