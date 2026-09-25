import {
  CANVAS_SCHEMA_VERSION,
  type CanvasDoc,
  type CanvasElement,
  type CanvasOperation,
  type Change,
  type ElementEntry,
  type Endpoint,
  type Stamp,
  type Tombstone,
} from './types';

export function newId(prefix = ''): string {
  const c = globalThis.crypto;
  const raw =
    c && typeof c.randomUUID === 'function'
      ? c.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return prefix ? `${prefix}_${raw}` : raw;
}

export function emptyDoc(): CanvasDoc {
  return { schemaVersion: CANVAS_SCHEMA_VERSION, elements: {} };
}

/** Total order on stamps: higher clock wins; actor id breaks ties. */
export function compareStamps(a: Stamp, b: Stamp): number {
  if (a.clock !== b.clock) return a.clock - b.clock;
  return a.actor < b.actor ? -1 : a.actor > b.actor ? 1 : 0;
}

export function isTombstone(entry: ElementEntry | undefined): entry is Tombstone {
  return !!entry && 'deleted' in entry && entry.deleted === true;
}

function changeEntry(change: Change): ElementEntry {
  return change.type === 'put'
    ? change.element
    : { id: change.id, deleted: true, version: change.version };
}

function changeId(change: Change): string {
  return change.type === 'put' ? change.element.id : change.id;
}

/** Returns true if `incoming` should replace `current` under LWW rules. */
function wins(incoming: ElementEntry, current: ElementEntry | undefined): boolean {
  return !current || compareStamps(incoming.version, current.version) > 0;
}

/**
 * Apply an operation. Commutative, associative and idempotent: applying the
 * same set of operations in any order (with duplicates) yields the same doc.
 * Returns the same object when nothing changed.
 */
export function applyOperation(doc: CanvasDoc, op: CanvasOperation): CanvasDoc {
  return applyChanges(doc, op.changes);
}

export function applyChanges(doc: CanvasDoc, changes: Change[]): CanvasDoc {
  let elements: Record<string, ElementEntry> | null = null;
  for (const change of changes) {
    const entry = changeEntry(change);
    const id = changeId(change);
    const current = (elements ?? doc.elements)[id];
    if (!wins(entry, current)) continue;
    elements ??= { ...doc.elements };
    elements[id] = entry;
  }
  return elements ? { ...doc, elements } : doc;
}

/** Merge two documents entry by entry (used after reconnecting). */
export function mergeDocs(a: CanvasDoc, b: CanvasDoc): CanvasDoc {
  return applyChanges(
    a,
    Object.values(b.elements).map((entry) =>
      isTombstone(entry)
        ? { type: 'delete' as const, id: entry.id, version: entry.version }
        : { type: 'put' as const, element: entry },
    ),
  );
}

/** Live (non-deleted) elements ordered by z-index, then id for determinism. */
export function liveElements(doc: CanvasDoc): CanvasElement[] {
  const out: CanvasElement[] = [];
  for (const entry of Object.values(doc.elements)) {
    if (!isTombstone(entry)) out.push(entry);
  }
  return out.sort((a, b) => a.z - b.z || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function maxClock(doc: CanvasDoc): number {
  let max = 0;
  for (const entry of Object.values(doc.elements)) max = Math.max(max, entry.version.clock);
  return max;
}

export function topZ(doc: CanvasDoc): number {
  let max = 0;
  for (const el of liveElements(doc)) max = Math.max(max, el.z);
  return max;
}

export function bottomZ(doc: CanvasDoc): number {
  let min = 0;
  for (const el of liveElements(doc)) min = Math.min(min, el.z);
  return min;
}

/** Lamport clock owned by one participant. */
export class LamportClock {
  private value: number;
  constructor(
    readonly actor: string,
    start = 0,
  ) {
    this.value = start;
  }
  observe(clock: number): void {
    if (clock > this.value) this.value = clock;
  }
  next(): Stamp {
    this.value += 1;
    return { clock: this.value, actor: this.actor };
  }
}

/** Build an operation that writes `puts` and deletes `deletes`, stamped with one clock tick. */
export function buildOperation(
  clock: LamportClock,
  puts: CanvasElement[],
  deletes: string[] = [],
): CanvasOperation {
  const version = clock.next();
  const changes: Change[] = [
    ...puts.map((el) => ({
      type: 'put' as const,
      element: { ...el, version, updatedBy: clock.actor },
    })),
    ...deletes.map((id) => ({ type: 'delete' as const, id, version })),
  ];
  return { id: newId('op'), actorId: clock.actor, changes };
}

// ---------------------------------------------------------------------------
// Undo / redo, scoped to the local participant's own actions.
// ---------------------------------------------------------------------------

/** Element states before and after one user action; null = did not exist. */
export interface HistoryEntry {
  before: Record<string, CanvasElement | null>;
  after: Record<string, CanvasElement | null>;
}

export interface History {
  undo: HistoryEntry[];
  redo: HistoryEntry[];
}

export const HISTORY_LIMIT = 200;

export function emptyHistory(): History {
  return { undo: [], redo: [] };
}

export function recordHistory(history: History, entry: HistoryEntry): History {
  if (Object.keys(entry.before).length === 0) return history;
  const undo = [...history.undo, entry].slice(-HISTORY_LIMIT);
  return { undo, redo: [] };
}

/** Turn a snapshot of element states into puts + deletes. */
export function statesToChanges(states: Record<string, CanvasElement | null>): {
  puts: CanvasElement[];
  deletes: string[];
} {
  const puts: CanvasElement[] = [];
  const deletes: string[] = [];
  for (const [id, state] of Object.entries(states)) {
    if (state) puts.push(state);
    else deletes.push(id);
  }
  return { puts, deletes };
}

export function undoStep(history: History): { history: History; states: Record<string, CanvasElement | null> } | null {
  const entry = history.undo[history.undo.length - 1];
  if (!entry) return null;
  return {
    history: { undo: history.undo.slice(0, -1), redo: [...history.redo, entry] },
    states: entry.before,
  };
}

export function redoStep(history: History): { history: History; states: Record<string, CanvasElement | null> } | null {
  const entry = history.redo[history.redo.length - 1];
  if (!entry) return null;
  return {
    history: { undo: [...history.undo, entry], redo: history.redo.slice(0, -1) },
    states: entry.after,
  };
}

// ---------------------------------------------------------------------------
// Clipboard / duplication
// ---------------------------------------------------------------------------

/**
 * Clone elements with fresh ids, offsetting positions. Connectors between
 * cloned elements are re-attached to the clones; connectors to elements
 * outside the selection are detached at their last position.
 */
export function cloneElements(
  elements: CanvasElement[],
  offset: { dx: number; dy: number },
  opts: { actor: string; zStart: number; makeId?: () => string },
): CanvasElement[] {
  const makeId = opts.makeId ?? (() => newId('el'));
  const idMap = new Map<string, string>();
  const groupMap = new Map<string, string>();
  for (const el of elements) idMap.set(el.id, makeId());
  const now = new Date().toISOString();
  const version: Stamp = { clock: 0, actor: opts.actor };

  const moveEndpoint = (ep: Endpoint): Endpoint => {
    const mapped = ep.elementId ? idMap.get(ep.elementId) : undefined;
    return mapped
      ? { ...ep, elementId: mapped, x: ep.x + offset.dx, y: ep.y + offset.dy }
      : { x: ep.x + offset.dx, y: ep.y + offset.dy };
  };

  return elements.map((el, i) => {
    let groupId: string | null = null;
    if (el.groupId) {
      if (!groupMap.has(el.groupId)) groupMap.set(el.groupId, makeId());
      groupId = groupMap.get(el.groupId)!;
    }
    const base = {
      id: idMap.get(el.id)!,
      z: opts.zStart + i,
      groupId,
      version,
      createdBy: opts.actor,
      createdAt: now,
      updatedBy: opts.actor,
    };
    switch (el.kind) {
      case 'shape':
        return { ...el, ...base, x: el.x + offset.dx, y: el.y + offset.dy };
      case 'stroke':
        return {
          ...el,
          ...base,
          points: el.points.map((v, idx) => v + (idx % 2 === 0 ? offset.dx : offset.dy)),
        };
      case 'connector':
        return { ...el, ...base, from: moveEndpoint(el.from), to: moveEndpoint(el.to) };
    }
  });
}

/** Expand a selection so that it includes every member of any touched group. */
export function expandToGroups(ids: Iterable<string>, elements: CanvasElement[]): Set<string> {
  const selected = new Set(ids);
  const groups = new Set<string>();
  for (const el of elements) if (selected.has(el.id) && el.groupId) groups.add(el.groupId);
  if (groups.size === 0) return selected;
  for (const el of elements) if (el.groupId && groups.has(el.groupId)) selected.add(el.id);
  return selected;
}

/** Connectors attached to any of the given element ids. */
export function attachedConnectors(ids: Set<string>, elements: CanvasElement[]): CanvasElement[] {
  return elements.filter(
    (el) =>
      el.kind === 'connector' &&
      !ids.has(el.id) &&
      ((el.from.elementId && ids.has(el.from.elementId)) || (el.to.elementId && ids.has(el.to.elementId))),
  );
}

// ---------------------------------------------------------------------------
// Validation (shared by client and mock server)
// ---------------------------------------------------------------------------

export const LIMITS = {
  maxElements: 5000,
  maxChangesPerOperation: 500,
  maxTextLength: 2000,
  maxStrokePoints: 20000,
};

export function validateOperation(op: CanvasOperation): string | null {
  if (!op || typeof op.id !== 'string' || !Array.isArray(op.changes)) return 'Malformed operation';
  if (op.changes.length > LIMITS.maxChangesPerOperation) return 'Operation too large';
  for (const change of op.changes) {
    if (change.type === 'delete') continue;
    if (change.type !== 'put') return 'Unknown change type';
    const el = change.element;
    if (!['shape', 'connector', 'stroke'].includes(el.kind)) return 'Unsupported element type';
    if (el.kind === 'shape') {
      if ((el.label?.length ?? 0) > LIMITS.maxTextLength) return 'Text too long';
      if ((el.description?.length ?? 0) > LIMITS.maxTextLength) return 'Text too long';
    }
    if (el.kind === 'connector' && (el.label?.length ?? 0) > LIMITS.maxTextLength) return 'Text too long';
    if (el.kind === 'stroke' && el.points.length > LIMITS.maxStrokePoints * 2) return 'Stroke too long';
  }
  return null;
}
