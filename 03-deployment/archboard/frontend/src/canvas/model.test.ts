import { describe, expect, it } from 'vitest';
import {
  applyOperation,
  buildOperation,
  cloneElements,
  compareStamps,
  emptyDoc,
  expandToGroups,
  LamportClock,
  liveElements,
  mergeDocs,
  emptyHistory,
  recordHistory,
  redoStep,
  undoStep,
  validateOperation,
} from './model';
import type { CanvasOperation, ConnectorElement, ShapeElement } from './types';

function shape(id: string, extra: Partial<ShapeElement> = {}): ShapeElement {
  return {
    id,
    kind: 'shape',
    componentType: 'service',
    x: 0,
    y: 0,
    w: 100,
    h: 50,
    label: id,
    z: 0,
    version: { clock: 0, actor: 'x' },
    createdBy: 'x',
    createdAt: '2026-01-01T00:00:00Z',
    updatedBy: 'x',
    ...extra,
  };
}

function connector(id: string, from: string, to: string): ConnectorElement {
  return {
    id,
    kind: 'connector',
    from: { elementId: from, anchor: 'auto', x: 0, y: 0 },
    to: { elementId: to, anchor: 'auto', x: 0, y: 0 },
    routing: 'straight',
    arrowStart: false,
    arrowEnd: true,
    label: '',
    dashed: false,
    color: '#000',
    width: 2,
    z: 0,
    version: { clock: 0, actor: 'x' },
    createdBy: 'x',
    createdAt: '2026-01-01T00:00:00Z',
    updatedBy: 'x',
  };
}

describe('stamps', () => {
  it('orders by clock then actor', () => {
    expect(compareStamps({ clock: 2, actor: 'a' }, { clock: 1, actor: 'z' })).toBeGreaterThan(0);
    expect(compareStamps({ clock: 1, actor: 'b' }, { clock: 1, actor: 'a' })).toBeGreaterThan(0);
    expect(compareStamps({ clock: 1, actor: 'a' }, { clock: 1, actor: 'a' })).toBe(0);
  });

  it('lamport clock moves past observed values', () => {
    const clock = new LamportClock('me');
    clock.observe(10);
    expect(clock.next()).toEqual({ clock: 11, actor: 'me' });
    clock.observe(3);
    expect(clock.next().clock).toBe(12);
  });
});

describe('applyOperation (LWW element map)', () => {
  const alice = new LamportClock('alice');
  const bob = new LamportClock('bob');

  it('adds, updates and deletes elements', () => {
    let doc = emptyDoc();
    doc = applyOperation(doc, buildOperation(alice, [shape('a')]));
    expect(liveElements(doc).map((e) => e.id)).toEqual(['a']);
    doc = applyOperation(doc, buildOperation(alice, [shape('a', { label: 'API' })]));
    expect((liveElements(doc)[0] as ShapeElement).label).toBe('API');
    doc = applyOperation(doc, buildOperation(alice, [], ['a']));
    expect(liveElements(doc)).toEqual([]);
  });

  it('ignores duplicate operations and returns the same object', () => {
    const op = buildOperation(alice, [shape('dup')]);
    const once = applyOperation(emptyDoc(), op);
    expect(applyOperation(once, op)).toBe(once);
  });

  it('converges regardless of delivery order', () => {
    const c1 = new LamportClock('c1');
    const c2 = new LamportClock('c2');
    const create = buildOperation(c1, [shape('n')]);
    c2.observe(1);
    const move = buildOperation(c2, [shape('n', { x: 200 })]);
    const rename = buildOperation(c1, [shape('n', { label: 'renamed' })]);
    const del = buildOperation(c2, [], ['other']);
    const orders: CanvasOperation[][] = [
      [create, move, rename, del],
      [del, rename, move, create],
      [move, create, del, rename, move],
    ];
    const results = orders.map((ops) => ops.reduce(applyOperation, emptyDoc()));
    for (const r of results) expect(r).toEqual(results[0]);
  });

  it('keeps edits to different objects independent', () => {
    const base = applyOperation(emptyDoc(), buildOperation(alice, [shape('a'), shape('b')]));
    bob.observe(alice.next().clock);
    const fromAlice = buildOperation(alice, [shape('a', { x: 50 })]);
    const fromBob = buildOperation(bob, [shape('b', { x: 99 })]);
    const doc = applyOperation(applyOperation(base, fromBob), fromAlice);
    const byId = Object.fromEntries(liveElements(doc).map((e) => [e.id, e as ShapeElement]));
    expect(byId.a.x).toBe(50);
    expect(byId.b.x).toBe(99);
  });

  it('a delete with a newer stamp beats an older update (tombstones)', () => {
    const c = new LamportClock('c');
    const put = buildOperation(c, [shape('t')]);
    const del = buildOperation(c, [], ['t']);
    expect(liveElements(applyOperation(applyOperation(emptyDoc(), del), put))).toEqual([]);
  });

  it('mergeDocs is commutative', () => {
    const c1 = new LamportClock('c1');
    const c2 = new LamportClock('c2');
    const a = applyOperation(emptyDoc(), buildOperation(c1, [shape('x', { x: 1 }), shape('y')]));
    const b = applyOperation(emptyDoc(), buildOperation(c2, [shape('x', { x: 2 }), shape('z')]));
    expect(mergeDocs(a, b)).toEqual(mergeDocs(b, a));
    expect(liveElements(mergeDocs(a, b))).toHaveLength(3);
  });
});

describe('history', () => {
  it('undoes and redoes a recorded action', () => {
    let history = emptyHistory();
    history = recordHistory(history, { before: { a: null }, after: { a: shape('a') } });
    const undo = undoStep(history)!;
    expect(undo.states).toEqual({ a: null });
    const redo = redoStep(undo.history)!;
    expect(redo.states.a?.id).toBe('a');
    expect(redoStep(redo.history)).toBeNull();
  });

  it('clears redo after a new action', () => {
    let history = recordHistory(emptyHistory(), { before: { a: null }, after: { a: shape('a') } });
    history = undoStep(history)!.history;
    history = recordHistory(history, { before: { b: null }, after: { b: shape('b') } });
    expect(history.redo).toHaveLength(0);
  });
});

describe('cloneElements', () => {
  it('re-attaches connectors between copied elements and detaches others', () => {
    let n = 0;
    const clones = cloneElements(
      [shape('a'), shape('b', { x: 200 }), connector('ab', 'a', 'b'), connector('ac', 'a', 'c')],
      { dx: 20, dy: 20 },
      { actor: 'me', zStart: 10, makeId: () => `new${n++}` },
    );
    const [a, b, ab, ac] = clones as [ShapeElement, ShapeElement, ConnectorElement, ConnectorElement];
    expect(a.x).toBe(20);
    expect(b.x).toBe(220);
    expect(ab.from.elementId).toBe(a.id);
    expect(ab.to.elementId).toBe(b.id);
    expect(ac.to.elementId).toBeUndefined();
    expect(clones.map((c) => c.z)).toEqual([10, 11, 12, 13]);
  });
});

describe('groups', () => {
  it('expands a selection to whole groups', () => {
    const els = [shape('a', { groupId: 'g' }), shape('b', { groupId: 'g' }), shape('c')];
    expect([...expandToGroups(['a'], els)].sort()).toEqual(['a', 'b']);
  });
});

describe('validateOperation', () => {
  it('rejects oversized text and unknown kinds', () => {
    const clock = new LamportClock('v');
    expect(validateOperation(buildOperation(clock, [shape('a', { label: 'x'.repeat(5000) })]))).toMatch(/too long/);
    const bad = buildOperation(clock, [{ ...shape('a'), kind: 'image' } as unknown as ShapeElement]);
    expect(validateOperation(bad)).toMatch(/Unsupported/);
    expect(validateOperation(buildOperation(clock, [shape('ok')]))).toBeNull();
  });
});
