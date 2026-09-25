import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  applyOperation,
  buildOperation,
  emptyHistory,
  isTombstone,
  LamportClock,
  liveElements,
  maxClock,
  recordHistory,
  redoStep,
  statesToChanges,
  undoStep,
  type History,
} from '../canvas/model';
import type { CanvasDoc, CanvasElement, CanvasOperation } from '../canvas/types';
import {
  computePermissions,
  errorMessage,
  isApiError,
  type ApiError,
  type ConnectionStatus,
  type InterviewSession,
  type Participant,
  type Permissions,
  type Presence,
  type RealtimeConnection,
  type ServerMessage,
} from '../services';
import { useBackend } from '../services/ServiceProvider';

const PRESENCE_THROTTLE_MS = 50;
const PRESENCE_HEARTBEAT_MS = 3000;
const PRESENCE_TTL_MS = 10000;

export interface RoomNotice {
  id: number;
  kind: 'info' | 'warning' | 'error';
  text: string;
}

export interface CommitOptions {
  /** Record an undo entry (default true). Ignored during a gesture. */
  history?: boolean;
}

export interface RoomState {
  loading: boolean;
  error: ApiError | Error | null;
  session: InterviewSession | null;
  me: Participant | null;
  participants: Participant[];
  permissions: Permissions | null;
  doc: CanvasDoc;
  elements: CanvasElement[];
  status: ConnectionStatus;
  presence: Presence[];
  removed: boolean;
  pendingCount: number;
  notices: RoomNotice[];
  canUndo: boolean;
  canRedo: boolean;
  commit(puts: CanvasElement[], deletes?: string[], options?: CommitOptions): void;
  beginGesture(): void;
  endGesture(): void;
  undo(): void;
  redo(): void;
  updatePresence(patch: Partial<Pick<Presence, 'cursor' | 'selection'>>): void;
  setSession(session: InterviewSession): void;
  refreshParticipants(): Promise<void>;
  dismissNotice(id: number): void;
  notify(kind: RoomNotice['kind'], text: string): void;
}

/**
 * Connects the UI to one interview room: loads the snapshot, keeps the local
 * canvas document, applies local edits optimistically and syncs them through
 * the realtime connection. All backend access goes through `useBackend()`.
 */
export function useRoom(sessionId: string): RoomState {
  const backend = useBackend();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [session, setSessionState] = useState<InterviewSession | null>(null);
  const [me, setMe] = useState<Participant | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [doc, setDocState] = useState<CanvasDoc>({ schemaVersion: 1, elements: {} });
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [presenceMap, setPresenceMap] = useState<Record<string, Presence>>({});
  const [removed, setRemoved] = useState(false);
  const [notices, setNotices] = useState<RoomNotice[]>([]);
  const [history, setHistoryState] = useState<History>(emptyHistory());
  const [pendingCount, setPendingCount] = useState(0);

  const docRef = useRef(doc);
  const historyRef = useRef(history);
  const clockRef = useRef<LamportClock | null>(null);
  const connRef = useRef<RealtimeConnection | null>(null);
  /** Operations not yet acknowledged by the server, in order. */
  const pendingRef = useRef(new Map<string, CanvasOperation>());
  const gestureRef = useRef<Record<string, CanvasElement | null> | null>(null);
  const presenceRef = useRef<Presence | null>(null);
  const presenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noticeId = useRef(0);
  const connectedOnce = useRef(false);

  const setDoc = useCallback((next: CanvasDoc) => {
    docRef.current = next;
    setDocState(next);
  }, []);

  const setHistory = useCallback((next: History) => {
    historyRef.current = next;
    setHistoryState(next);
  }, []);

  const notify = useCallback((kind: RoomNotice['kind'], text: string) => {
    const id = ++noticeId.current;
    setNotices((n) => [...n.filter((x) => x.text !== text), { id, kind, text }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 5000);
  }, []);

  const syncPending = useCallback(() => setPendingCount(pendingRef.current.size), []);

  const sendPending = useCallback(() => {
    const conn = connRef.current;
    if (!conn || conn.status !== 'connected') return;
    for (const op of pendingRef.current.values()) conn.send({ type: 'document_update', op });
  }, []);

  /** Replace local state with the authoritative snapshot, then re-apply unacknowledged local ops. */
  const resync = useCallback(async () => {
    try {
      const access = await backend.canvas.openRoom(sessionId);
      let next = access.canvas;
      for (const op of pendingRef.current.values()) next = applyOperation(next, op);
      clockRef.current?.observe(maxClock(next));
      setDoc(next);
      setSessionState(access.session);
      setParticipants(access.participants);
      setMe(access.me);
      sendPending();
    } catch (err) {
      if (isApiError(err, 'PARTICIPANT_REMOVED')) setRemoved(true);
      else notify('error', `Could not refresh the canvas: ${errorMessage(err)}`);
    }
  }, [backend, sessionId, notify, sendPending, setDoc]);

  const refreshParticipants = useCallback(async () => {
    try {
      setParticipants(await backend.sessions.listParticipants(sessionId));
    } catch {
      /* ignore: next resync will refresh */
    }
  }, [backend, sessionId]);

  // Initial load + realtime connection.
  useEffect(() => {
    let cancelled = false;
    let conn: RealtimeConnection | null = null;
    const pending = pendingRef.current;
    setLoading(true);
    setError(null);
    connectedOnce.current = false;

    backend.canvas
      .openRoom(sessionId)
      .then((access) => {
        if (cancelled) return;
        clockRef.current = new LamportClock(access.me.id, maxClock(access.canvas));
        setDoc(access.canvas);
        setSessionState(access.session);
        setMe(access.me);
        setParticipants(access.participants);
        setLoading(false);
        presenceRef.current = {
          participantId: access.me.id,
          displayName: access.me.displayName,
          color: access.me.color,
          role: access.me.role,
          cursor: null,
          selection: [],
          ts: Date.now(),
        };

        conn = backend.realtime.connect(sessionId);
        connRef.current = conn;
        setStatus(conn.status);
        conn.onStatus((s) => {
          setStatus(s);
          if (s === 'offline') notify('warning', 'You are offline. Changes will sync when the connection returns.');
        });
        conn.onMessage((m) => handleMessage(m));
      })
      .catch((err) => {
        if (cancelled) return;
        if (isApiError(err, 'PARTICIPANT_REMOVED')) setRemoved(true);
        setError(err);
        setLoading(false);
      });

    function handleMessage(m: ServerMessage) {
      switch (m.type) {
        case 'room_joined':
          if (connectedOnce.current) {
            void resync();
          } else {
            connectedOnce.current = true;
            sendPending();
          }
          sendPresenceNow();
          return;
        case 'document_update':
          for (const change of m.op.changes) {
            clockRef.current?.observe(change.type === 'put' ? change.element.version.clock : change.version.clock);
          }
          setDoc(applyOperation(docRef.current, m.op));
          return;
        case 'document_ack':
          pending.delete(m.opId);
          syncPending();
          return;
        case 'error':
          if (m.opId) {
            pending.delete(m.opId);
            syncPending();
            notify('error', m.message);
            void resync();
          } else if (m.code === 'PARTICIPANT_REMOVED') {
            setRemoved(true);
          } else {
            notify('error', m.message);
          }
          return;
        case 'presence_update':
          setPresenceMap((p) => ({ ...p, [m.presence.participantId]: { ...m.presence, ts: Date.now() } }));
          return;
        case 'presence_leave':
          setPresenceMap((p) => {
            const next = { ...p };
            delete next[m.participantId];
            return next;
          });
          return;
        case 'participants_changed':
          void refreshParticipants();
          return;
        case 'participant_removed':
          if (m.participantId === presenceRef.current?.participantId) {
            setRemoved(true);
            connRef.current?.close();
          } else {
            setParticipants((ps) => ps.filter((p) => p.id !== m.participantId));
            setPresenceMap((p) => {
              const next = { ...p };
              delete next[m.participantId];
              return next;
            });
          }
          return;
        case 'session_updated':
          setSessionState(m.session);
          return;
        case 'session_ended':
          setSessionState(m.session);
          pending.clear();
          syncPending();
          notify('info', 'The interview has ended. The canvas is now read-only.');
          return;
        case 'canvas_reset':
          pending.clear();
          syncPending();
          setHistory(emptyHistory());
          notify('info', 'The canvas was reset by the interviewer.');
          void resync();
          return;
        case 'pong':
          return;
      }
    }

    function sendPresenceNow() {
      const c = connRef.current;
      if (!c || c.status !== 'connected' || !presenceRef.current) return;
      presenceRef.current = { ...presenceRef.current, ts: Date.now() };
      c.send({ type: 'presence_update', presence: presenceRef.current });
    }

    const heartbeat = setInterval(() => {
      sendPresenceNow();
      const cutoff = Date.now() - PRESENCE_TTL_MS;
      setPresenceMap((p) => {
        const stale = Object.values(p).filter((x) => x.ts < cutoff);
        if (stale.length === 0) return p;
        const next = { ...p };
        for (const s of stale) delete next[s.participantId];
        return next;
      });
    }, PRESENCE_HEARTBEAT_MS);

    const onUnload = () => connRef.current?.close();
    window.addEventListener('beforeunload', onUnload);

    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      window.removeEventListener('beforeunload', onUnload);
      conn?.close();
      connRef.current = null;
      pending.clear();
    };
  }, [backend, sessionId, notify, refreshParticipants, resync, sendPending, setDoc, setHistory, syncPending]);

  const permissions = useMemo(() => (me && session ? computePermissions(me.role, session) : null), [me, session]);
  const canEdit = !!permissions?.canEdit && !removed;

  /** Apply puts/deletes locally, send (or queue) them, and optionally record history. */
  const apply = useCallback(
    (puts: CanvasElement[], deletes: string[]) => {
      const clock = clockRef.current;
      if (!clock || (puts.length === 0 && deletes.length === 0)) return;
      const op = buildOperation(clock, puts, deletes);
      setDoc(applyOperation(docRef.current, op));
      pendingRef.current.set(op.id, op);
      syncPending();
      const conn = connRef.current;
      if (conn && conn.status === 'connected') conn.send({ type: 'document_update', op });
    },
    [setDoc, syncPending],
  );

  const currentStates = useCallback((ids: string[]) => {
    const states: Record<string, CanvasElement | null> = {};
    for (const id of ids) {
      const entry = docRef.current.elements[id];
      states[id] = entry && !isTombstone(entry) ? entry : null;
    }
    return states;
  }, []);

  const commit = useCallback(
    (puts: CanvasElement[], deletes: string[] = [], options: CommitOptions = {}) => {
      if (!canEdit) return;
      const ids = [...puts.map((p) => p.id), ...deletes];
      const before = currentStates(ids);
      if (gestureRef.current) {
        for (const id of ids) if (!(id in gestureRef.current)) gestureRef.current[id] = before[id];
      }
      apply(puts, deletes);
      if (!gestureRef.current && options.history !== false) {
        setHistory(recordHistory(historyRef.current, { before, after: currentStates(ids) }));
      }
    },
    [apply, canEdit, currentStates, setHistory],
  );

  const beginGesture = useCallback(() => {
    gestureRef.current = {};
  }, []);

  const endGesture = useCallback(() => {
    const before = gestureRef.current;
    gestureRef.current = null;
    if (!before || Object.keys(before).length === 0) return;
    setHistory(recordHistory(historyRef.current, { before, after: currentStates(Object.keys(before)) }));
  }, [currentStates, setHistory]);

  const replay = useCallback(
    (step: ReturnType<typeof undoStep>) => {
      if (!step || !canEdit) return;
      const { puts, deletes } = statesToChanges(step.states);
      apply(puts, deletes);
      setHistory(step.history);
    },
    [apply, canEdit, setHistory],
  );

  const undo = useCallback(() => replay(undoStep(historyRef.current)), [replay]);
  const redo = useCallback(() => replay(redoStep(historyRef.current)), [replay]);

  const updatePresence = useCallback((patch: Partial<Pick<Presence, 'cursor' | 'selection'>>) => {
    if (!presenceRef.current) return;
    presenceRef.current = { ...presenceRef.current, ...patch };
    if (presenceTimer.current) return;
    presenceTimer.current = setTimeout(() => {
      presenceTimer.current = null;
      const c = connRef.current;
      if (c && c.status === 'connected' && presenceRef.current) {
        c.send({ type: 'presence_update', presence: { ...presenceRef.current, ts: Date.now() } });
      }
    }, PRESENCE_THROTTLE_MS);
  }, []);

  const elements = useMemo(() => liveElements(doc), [doc]);
  const presence = useMemo(
    () => Object.values(presenceMap).filter((p) => p.participantId !== me?.id),
    [presenceMap, me],
  );

  return {
    loading,
    error,
    session,
    me,
    participants,
    permissions: permissions && { ...permissions, canEdit },
    doc,
    elements,
    status,
    presence,
    removed,
    pendingCount,
    notices,
    canUndo: canEdit && history.undo.length > 0,
    canRedo: canEdit && history.redo.length > 0,
    commit,
    beginGesture,
    endGesture,
    undo,
    redo,
    updatePresence,
    setSession: setSessionState,
    refreshParticipants,
    dismissNotice: (id) => setNotices((n) => n.filter((x) => x.id !== id)),
    notify,
  };
}
