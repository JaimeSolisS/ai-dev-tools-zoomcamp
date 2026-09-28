import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Download,
  Eye,
  EyeOff,
  History,
  Lock,
  LockOpen,
  Magnet,
  Maximize,
  MoreHorizontal,
  PanelRight,
  Play,
  Redo2,
  RotateCcw,
  Share2,
  Square,
  Trash2,
  Undo2,
  UserX,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  createConnector,
  createShape,
  DEFAULT_CONNECTOR_STYLE,
  endpointFor,
  groupElements,
  idsToDelete,
  moveElements,
  reorder,
  ungroupElements,
  type LayerMove,
} from '../canvas/editing';
import { elementBounds, fitViewport, GRID_SIZE, indexElements, screenToWorld, unionRects, zoomAt, type Viewport } from '../canvas/geometry';
import { cloneElements } from '../canvas/model';
import type { CanvasElement, ComponentType, ShapeElement } from '../canvas/types';
import { CanvasView, type Tool, type ToolOptions } from '../components/canvas/CanvasView';
import { ComponentLibrary } from '../components/room/ComponentLibrary';
import { ConnectionIndicator } from '../components/room/ConnectionIndicator';
import { Participants } from '../components/room/Participants';
import { PropertiesPanel, type PanelActions } from '../components/room/PropertiesPanel';
import { ShareDialog } from '../components/room/ShareDialog';
import { Timer } from '../components/room/Timer';
import { Toolbar, TOOL_SHORTCUTS } from '../components/room/Toolbar';
import { ConfirmDialog, FullPageMessage, IconButton, Modal, Spinner, StateBadge } from '../components/ui';
import { useRoom } from '../hooks/useRoom';
import { formatDateTime } from '../lib/format';
import { errorMessage, isApiError, type CanvasSnapshotInfo, type Participant } from '../services';
import { useBackend } from '../services/ServiceProvider';

type Confirm = 'end' | 'clear' | { remove: Participant } | null;

function isTypingTarget(t: EventTarget | null): boolean {
  return t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));
}

export function InterviewRoomPage() {
  const { sessionId = '' } = useParams();
  const room = useRoom(sessionId);
  const backend = useBackend();
  const navigate = useNavigate();

  const [selection, setSelectionState] = useState<Set<string>>(new Set());
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });
  const [size, setSize] = useState({ width: 1000, height: 700 });
  const [tool, setTool] = useState<Tool>('select');
  const [toolOptions, setToolOptions] = useState<ToolOptions>({
    penColor: '#0f172a',
    penWidth: 2,
    highlighterColor: '#facc15',
    connector: DEFAULT_CONNECTOR_STYLE,
  });
  const [snapToGrid, setSnapToGrid] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [snapshotsOpen, setSnapshotsOpen] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [busy, setBusy] = useState(false);
  const clipboard = useRef<CanvasElement[]>([]);
  const pasteCount = useRef(0);
  const fitted = useRef(false);

  const { elements, permissions, session, me, commit, updatePresence } = room;
  const canEdit = !!permissions?.canEdit;
  const index = useMemo(() => indexElements(elements), [elements]);

  const setSelection = useCallback(
    (next: Set<string>) => {
      setSelectionState(next);
      updatePresence({ selection: [...next] });
    },
    [updatePresence],
  );

  // Drop selected ids that no longer exist (deleted remotely).
  useEffect(() => {
    if ([...selection].some((id) => !index.has(id))) setSelection(new Set([...selection].filter((id) => index.has(id))));
  }, [index, selection, setSelection]);

  // Leave editing tools when editing becomes unavailable (lock, end).
  useEffect(() => {
    if (!canEdit) {
      setTool((t) => (t === 'hand' ? t : 'select'));
      setEditingId(null);
      setLibraryOpen(false);
    }
  }, [canEdit]);

  const zoomToFit = useCallback(() => {
    const bounds = unionRects(elements.map((el) => elementBounds(el, index)));
    setViewport(fitViewport(bounds, size));
  }, [elements, index, size]);

  const resetView = useCallback(() => setViewport({ x: size.width / 2, y: size.height / 2, zoom: 1 }), [size]);

  // Fit the content once after load.
  useEffect(() => {
    if (!room.loading && !room.error && !fitted.current && size.width > 0) {
      fitted.current = true;
      if (elements.length) zoomToFit();
      else resetView();
    }
  }, [room.loading, room.error, elements.length, size, zoomToFit, resetView]);

  const nextZ = useCallback(() => elements.reduce((m, e) => Math.max(m, e.z), 0) + 1, [elements]);

  const viewCenter = useCallback(() => screenToWorld(viewport, { x: size.width / 2, y: size.height / 2 }), [viewport, size]);

  // ------------------------------------------------------------ actions --

  const selectedElements = useMemo(() => elements.filter((e) => selection.has(e.id)), [elements, selection]);

  const addComponent = useCallback(
    (type: ComponentType) => {
      if (!me) return;
      const offset = (pasteCount.current++ % 5) * 16;
      const c = viewCenter();
      const shape = createShape(type, { x: c.x + offset, y: c.y + offset }, me.id, nextZ(), { snap: snapToGrid });
      commit([shape]);
      setSelection(new Set([shape.id]));
    },
    [me, viewCenter, nextZ, snapToGrid, commit, setSelection],
  );

  const deleteSelection = useCallback(() => {
    if (!selection.size) return;
    commit([], idsToDelete(selection, elements));
    setSelection(new Set());
  }, [selection, elements, commit, setSelection]);

  const paste = useCallback(
    (source: CanvasElement[]) => {
      if (!me || source.length === 0) return;
      pasteCount.current += 1;
      const clones = cloneElements(source, { dx: 24, dy: 24 }, { actor: me.id, zStart: nextZ() });
      commit(clones);
      setSelection(new Set(clones.map((c) => c.id)));
      clipboard.current = clones;
    },
    [me, nextZ, commit, setSelection],
  );

  const duplicate = useCallback(() => paste(selectedElements), [paste, selectedElements]);

  const copy = useCallback(() => {
    clipboard.current = selectedElements;
  }, [selectedElements]);

  const nudge = useCallback(
    (dx: number, dy: number) => {
      if (!selectedElements.length) return;
      commit(moveElements(selectedElements, dx, dy));
    },
    [selectedElements, commit],
  );

  const layer = useCallback((move: LayerMove) => commit(reorder(selection, elements, move)), [selection, elements, commit]);

  const connectTo = useCallback(
    (targetId: string) => {
      const from = selectedElements[0];
      const to = index.get(targetId);
      if (!me || from?.kind !== 'shape' || to?.kind !== 'shape') return;
      const connector = createConnector(endpointFor(from, { x: from.x, y: from.y }), endpointFor(to as ShapeElement, { x: to.x, y: to.y }), me.id, nextZ(), toolOptions.connector);
      commit([connector]);
      setSelection(new Set([connector.id]));
    },
    [selectedElements, index, me, nextZ, toolOptions.connector, commit, setSelection],
  );

  const panelActions: PanelActions = {
    update: (el) => commit([el]),
    beginEdit: room.beginGesture,
    endEdit: room.endGesture,
    remove: deleteSelection,
    duplicate,
    group: () => commit(groupElements(selectedElements)),
    ungroup: () => commit(ungroupElements(selectedElements)),
    reorder: layer,
    connectTo,
  };

  const zoomBy = useCallback((factor: number) => setViewport((vp) => zoomAt(vp, { x: size.width / 2, y: size.height / 2 }, vp.zoom * factor)), [size]);

  // ---------------------------------------------------------- shortcuts --

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target) || document.querySelector('.modal')) return;
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();

      if (mod && key === 'z') {
        e.preventDefault();
        if (e.shiftKey) room.redo();
        else room.undo();
        return;
      }
      if (mod && key === 'y') {
        e.preventDefault();
        room.redo();
        return;
      }
      if (mod && key === 'a') {
        e.preventDefault();
        setSelection(new Set(elements.map((el) => el.id)));
        return;
      }
      if (mod && key === 'c') {
        copy();
        return;
      }
      if (mod && key === 'x' && canEdit) {
        copy();
        deleteSelection();
        return;
      }
      if (mod && key === 'v' && canEdit) {
        e.preventDefault();
        paste(clipboard.current);
        return;
      }
      if (mod && key === 'd' && canEdit) {
        e.preventDefault();
        duplicate();
        return;
      }
      if (mod && key === 'g' && canEdit) {
        e.preventDefault();
        commit(e.shiftKey ? ungroupElements(selectedElements) : groupElements(selectedElements));
        return;
      }
      if ((e.key === ']' || e.key === '[') && canEdit) {
        e.preventDefault();
        layer(e.key === ']' ? (mod ? 'front' : 'forward') : mod ? 'back' : 'backward');
        return;
      }
      if (mod && (key === '=' || key === '+' || key === '-')) {
        e.preventDefault();
        zoomBy(key === '-' ? 1 / 1.2 : 1.2);
        return;
      }
      if (mod) return;

      if (e.key === 'Escape') {
        setSelection(new Set());
        setTool('select');
        setLibraryOpen(false);
        return;
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && canEdit) {
        e.preventDefault();
        deleteSelection();
        return;
      }
      if (e.key === 'Enter' && canEdit && selectedElements.length === 1 && selectedElements[0].kind !== 'stroke') {
        e.preventDefault();
        setEditingId(selectedElements[0].id);
        return;
      }
      if (e.key.startsWith('Arrow') && selectedElements.length && canEdit) {
        e.preventDefault();
        const step = e.shiftKey ? GRID_SIZE * 2 : snapToGrid ? GRID_SIZE : 2;
        const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
        const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0;
        nudge(dx, dy);
        return;
      }
      if (e.shiftKey && (e.key === '!' || e.code === 'Digit1')) {
        zoomToFit();
        return;
      }
      if (e.shiftKey && (e.key === ')' || e.code === 'Digit0')) {
        resetView();
        return;
      }
      if (e.key === '+' || e.key === '=') return zoomBy(1.2);
      if (e.key === '-') return zoomBy(1 / 1.2);
      if (key === 'l' && canEdit) {
        setLibraryOpen((o) => !o);
        return;
      }
      const t = TOOL_SHORTCUTS[key];
      if (t && !e.shiftKey && !e.altKey && (canEdit || t === 'select' || t === 'hand')) setTool(t);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [room, elements, selectedElements, canEdit, snapToGrid, copy, paste, duplicate, deleteSelection, layer, nudge, zoomBy, zoomToFit, resetView, commit, setSelection]);

  // ----------------------------------------------------- session control --

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      room.notify('error', errorMessage(err));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const updateSession = (patch: Parameters<typeof backend.sessions.update>[1]) =>
    run(async () => room.setSession(await backend.sessions.update(sessionId, patch)));

  const exportJson = () => {
    if (!session) return;
    const data = { exportedAt: new Date().toISOString(), session, canvas: room.doc };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.title.replace(/[^\w-]+/g, '-').toLowerCase() || 'interview'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // --------------------------------------------------------------- render --

  if (room.removed) {
    return (
      <FullPageMessage title="You were removed from this interview" icon={<UserX size={36} className="accent" aria-hidden />}>
        <p className="muted">The host removed you from the session. If this was a mistake, ask them for a new invitation link.</p>
      </FullPageMessage>
    );
  }

  if (room.loading) {
    return (
      <FullPageMessage title="Opening interview…">
        <Spinner />
      </FullPageMessage>
    );
  }

  if (room.error || !session || !me || !permissions) {
    const err = room.error;
    if (isApiError(err, 'UNAUTHENTICATED')) {
      return (
        <FullPageMessage title="Join with your invitation link">
          <p className="muted">Candidates join through the link the interviewer shared. Interviewers can sign in to open their sessions.</p>
          <Link to="/login" state={{ from: `/sessions/${sessionId}` }} className="button primary">
            Interviewer sign in
          </Link>
        </FullPageMessage>
      );
    }
    if (isApiError(err, 'SESSION_ENDED')) {
      return (
        <FullPageMessage title="This interview has ended">
          <p className="muted">Thanks for participating. The canvas has been saved for the interviewers.</p>
        </FullPageMessage>
      );
    }
    return (
      <FullPageMessage title="Interview not available">
        <p className="muted">{err ? errorMessage(err) : 'Something went wrong.'}</p>
        <Link to="/" className="button">
          Go to dashboard
        </Link>
      </FullPageMessage>
    );
  }

  const isStaff = me.role === 'owner' || me.role === 'interviewer';
  const isOwner = me.role === 'owner';
  const ended = session.state === 'ended' || session.state === 'archived';

  let banner: { kind: 'info' | 'warning'; text: string } | null = null;
  if (ended) banner = { kind: 'info', text: isStaff ? 'This interview has ended. You are viewing the final canvas (read-only).' : 'The interview has ended. Thank you for participating!' };
  else if (me.role === 'observer') banner = { kind: 'info', text: 'You are observing. The canvas is view-only.' };
  else if (me.role === 'candidate' && session.state === 'draft') banner = { kind: 'info', text: 'Waiting for the interviewer to start the interview. You can read the prompt in the meantime.' };
  else if (me.role === 'candidate' && !session.candidateEditingEnabled) banner = { kind: 'warning', text: 'The interviewer has paused candidate editing.' };
  else if (isStaff && session.state === 'draft') banner = { kind: 'info', text: 'Draft: prepare the canvas, then share the link and start the interview.' };

  return (
    <div className="room">
      <header className="room-topbar">
        <div className="topbar-left">
          {isStaff && (
            <IconButton label="Back to dashboard" onClick={() => navigate('/')}>
              <ArrowLeft size={18} />
            </IconButton>
          )}
          <h1 className="room-title" title={session.title}>
            {session.title}
          </h1>
          <StateBadge state={session.state} />
          <ConnectionIndicator status={room.status} pending={room.pendingCount} />
        </div>
        <div className="topbar-right">
          <Timer session={session} />
          <Participants
            participants={room.participants}
            presence={room.presence}
            meId={me.id}
            canRemove={permissions.canRemoveParticipants}
            onRemove={(p) => setConfirm({ remove: p })}
          />
          {permissions.canLockEditing && (
            <button
              type="button"
              className={`button small${session.candidateEditingEnabled ? '' : ' warning'}`}
              onClick={() => void updateSession({ candidateEditingEnabled: !session.candidateEditingEnabled })}
              aria-pressed={!session.candidateEditingEnabled}
              disabled={busy}
            >
              {session.candidateEditingEnabled ? <LockOpen size={15} aria-hidden /> : <Lock size={15} aria-hidden />}
              {session.candidateEditingEnabled ? 'Candidate can edit' : 'Candidate locked'}
            </button>
          )}
          {permissions.canShare && (
            <button type="button" className="button small" onClick={() => setShareOpen(true)}>
              <Share2 size={15} aria-hidden /> Share
            </button>
          )}
          {isOwner && session.state === 'draft' && (
            <button type="button" className="button small primary" disabled={busy} onClick={() => void run(async () => room.setSession(await backend.sessions.start(sessionId)))}>
              <Play size={15} aria-hidden /> Start interview
            </button>
          )}
          {isOwner && session.state === 'ended' && (
            <button type="button" className="button small" disabled={busy} onClick={() => void run(async () => room.setSession(await backend.sessions.reopen(sessionId)))}>
              <RotateCcw size={15} aria-hidden /> Reopen
            </button>
          )}
          {(isStaff || ended) && (
            <div className="menu-wrap">
              <IconButton label="More actions" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen} aria-haspopup="menu">
                <MoreHorizontal size={18} />
              </IconButton>
              {menuOpen && (
                <div className="popover menu" role="menu" onClick={() => setMenuOpen(false)}>
                  <button type="button" role="menuitem" onClick={exportJson}>
                    <Download size={15} aria-hidden /> Export canvas (JSON)
                  </button>
                  {permissions.canEditSettings && (
                    <button type="button" role="menuitem" onClick={() => void updateSession({ showCursors: !session.showCursors })}>
                      {session.showCursors ? <EyeOff size={15} aria-hidden /> : <Eye size={15} aria-hidden />}
                      {session.showCursors ? 'Hide cursors for everyone' : 'Show cursors'}
                    </button>
                  )}
                  {isOwner && (
                    <button type="button" role="menuitem" onClick={() => setSnapshotsOpen(true)}>
                      <History size={15} aria-hidden /> Saved snapshots
                    </button>
                  )}
                  {permissions.canClearCanvas && (
                    <button type="button" role="menuitem" className="danger" onClick={() => setConfirm('clear')}>
                      <Trash2 size={15} aria-hidden /> Clear canvas…
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          {isOwner && session.state === 'live' && (
            <>
              <span className="topbar-divider" aria-hidden />
              <button type="button" className="button small danger" onClick={() => setConfirm('end')}>
                <Square size={14} aria-hidden /> End interview
              </button>
            </>
          )}
        </div>
      </header>

      {banner && (
        <div className={`room-banner ${banner.kind}`} role="status">
          {banner.text}
        </div>
      )}

      <div className="room-body">
        <Toolbar
          tool={tool}
          onTool={setTool}
          canEdit={canEdit}
          libraryOpen={libraryOpen}
          onToggleLibrary={() => setLibraryOpen((o) => !o)}
          options={toolOptions}
          onOptions={setToolOptions}
        />
        {libraryOpen && canEdit && <ComponentLibrary onAdd={addComponent} onClose={() => setLibraryOpen(false)} />}

        <div className="canvas-area">
          <CanvasView
            elements={elements}
            selection={selection}
            onSelectionChange={setSelection}
            viewport={viewport}
            onViewportChange={setViewport}
            onSizeChange={setSize}
            tool={tool}
            toolOptions={toolOptions}
            onToolDone={() => setTool('select')}
            canEdit={canEdit}
            snapToGrid={snapToGrid}
            me={me}
            presence={room.presence}
            showCursors={session.showCursors}
            editingId={editingId}
            onEditingChange={setEditingId}
            commit={commit}
            beginGesture={room.beginGesture}
            endGesture={room.endGesture}
            onCursor={(p) => updatePresence({ cursor: p })}
            nextZ={nextZ}
          />
          {elements.length === 0 && canEdit && (
            <div className="canvas-empty-hint" aria-hidden>
              Open the component library (L) or pick a tool to start designing.
            </div>
          )}

          <div className="bottom-controls" role="toolbar" aria-label="View and history">
            <IconButton label="Undo" shortcut="⌘Z" onClick={room.undo} disabled={!room.canUndo}>
              <Undo2 size={17} />
            </IconButton>
            <IconButton label="Redo" shortcut="⇧⌘Z" onClick={room.redo} disabled={!room.canRedo}>
              <Redo2 size={17} />
            </IconButton>
            <span className="controls-sep" />
            <IconButton label="Zoom out" shortcut="−" onClick={() => zoomBy(1 / 1.2)}>
              <ZoomOut size={17} />
            </IconButton>
            <button type="button" className="zoom-level" onClick={resetView} aria-label="Reset view (100%)" data-tooltip="Reset view (⇧0)">
              {Math.round(viewport.zoom * 100)}%
            </button>
            <IconButton label="Zoom in" shortcut="+" onClick={() => zoomBy(1.2)}>
              <ZoomIn size={17} />
            </IconButton>
            <IconButton label="Zoom to fit" shortcut="⇧1" onClick={zoomToFit}>
              <Maximize size={17} />
            </IconButton>
            <span className="controls-sep" />
            <IconButton label="Snap to grid" active={snapToGrid} onClick={() => setSnapToGrid((s) => !s)}>
              <Magnet size={17} />
            </IconButton>
            {!panelOpen && (
              <IconButton label="Show side panel" onClick={() => setPanelOpen(true)}>
                <PanelRight size={17} />
              </IconButton>
            )}
          </div>
          <div className="notices" aria-live="polite">
            {room.notices.map((n) => (
              <div key={n.id} className={`notice ${n.kind}`} role={n.kind === 'error' ? 'alert' : 'status'}>
                <span>{n.text}</span>
                <button type="button" className="icon-button" aria-label="Dismiss" onClick={() => room.dismissNotice(n.id)}>
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>

        {panelOpen && (
          <PropertiesPanel
            selected={selectedElements}
            elements={elements}
            canEdit={canEdit}
            session={session}
            permissions={permissions}
            actions={panelActions}
            onSavePrompt={async (prompt) => {
              await updateSession({ prompt });
            }}
            onCollapse={() => setPanelOpen(false)}
          />
        )}
      </div>

      {shareOpen && <ShareDialog sessionId={sessionId} onClose={() => setShareOpen(false)} />}
      {snapshotsOpen && (
        <SnapshotsDialog
          sessionId={sessionId}
          canRestore={permissions.canClearCanvas}
          onClose={() => setSnapshotsOpen(false)}
          onRestored={() => room.notify('info', 'Snapshot restored.')}
        />
      )}

      {confirm === 'end' && (
        <ConfirmDialog
          title="End the interview?"
          message={<p>The canvas becomes read-only for everyone and a final snapshot is saved. You can reopen it later from this page.</p>}
          confirmLabel="End interview"
          destructive
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void run(async () => room.setSession(await backend.sessions.end(sessionId)))}
        />
      )}
      {confirm === 'clear' && (
        <ConfirmDialog
          title="Clear the canvas?"
          message={<p>Everything on the canvas is removed for all participants. A snapshot is saved first, so you can restore it from “Saved snapshots”.</p>}
          confirmLabel="Clear canvas"
          destructive
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void run(() => backend.sessions.clearCanvas(sessionId))}
        />
      )}
      {confirm && typeof confirm === 'object' && (
        <ConfirmDialog
          title={`Remove ${confirm.remove.displayName}?`}
          message={<p>They will be disconnected and cannot rejoin with their current access. Their changes on the canvas are kept.</p>}
          confirmLabel="Remove"
          destructive
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() =>
            void run(async () => {
              await backend.sessions.removeParticipant(sessionId, confirm.remove.id);
              await room.refreshParticipants();
            })
          }
        />
      )}
    </div>
  );
}

const REASON: Record<CanvasSnapshotInfo['reason'], string> = {
  final: 'Final (interview ended)',
  'before-clear': 'Before canvas was cleared',
  'before-restore': 'Before a restore',
  periodic: 'Automatic',
};

function SnapshotsDialog({ sessionId, canRestore, onClose, onRestored }: { sessionId: string; canRestore: boolean; onClose(): void; onRestored(): void }) {
  const backend = useBackend();
  const [snapshots, setSnapshots] = useState<CanvasSnapshotInfo[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    backend.sessions
      .listSnapshots(sessionId)
      .then(setSnapshots)
      .catch((err) => setError(errorMessage(err)));
  }, [backend, sessionId]);

  return (
    <Modal title="Saved snapshots" onClose={onClose}>
      {error && <p className="error-text">{error}</p>}
      {!snapshots ? (
        <Spinner />
      ) : snapshots.length === 0 ? (
        <p className="muted">No snapshots yet. Snapshots are saved when the canvas is cleared and when the interview ends.</p>
      ) : (
        <ul className="link-list">
          {snapshots.map((s) => (
            <li key={s.id}>
              <span>
                <strong>{REASON[s.reason]}</strong>
                <span className="muted">
                  {' '}
                  · {formatDateTime(s.createdAt)} · {s.elementCount} objects
                </span>
              </span>
              {canRestore && (
                <button
                  type="button"
                  className="button small"
                  onClick={async () => {
                    try {
                      await backend.sessions.restoreSnapshot(sessionId, s.id);
                      onRestored();
                      onClose();
                    } catch (err) {
                      setError(errorMessage(err));
                    }
                  }}
                >
                  Restore
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
