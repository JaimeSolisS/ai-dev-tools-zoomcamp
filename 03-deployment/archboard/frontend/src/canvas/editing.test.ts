import { describe, expect, it } from 'vitest';
import {
  createConnector,
  createShape,
  endpointFor,
  groupElements,
  idsToDelete,
  moveElements,
  reorder,
  resizeShape,
  ungroupElements,
} from './editing';
import type { ConnectorElement, ShapeElement } from './types';

const at = (x: number, y: number) => ({ x, y });

describe('editing operations', () => {
  it('creates shapes centred on a point, optionally snapped', () => {
    const s = createShape('server', at(100, 100), 'me', 3);
    expect(s).toMatchObject({ kind: 'shape', componentType: 'server', w: 150, h: 72, x: 25, y: 64, z: 3, label: 'Server' });
    const snapped = createShape('server', at(107, 103), 'me', 3, { snap: true });
    expect(snapped.x % 20).toBe(0);
    expect(snapped.y % 20).toBe(0);
    expect(createShape('sticky', at(0, 0), 'me', 1).label).toBe('');
    expect(createShape('boundary', at(0, 0), 'me', 5).z).toBeLessThan(0);
  });

  it('moves shapes, strokes and free connector ends', () => {
    const s = createShape('server', at(0, 0), 'me', 1);
    const free = createConnector({ x: 0, y: 0 }, endpointFor(s, at(0, 0)), 'me', 2);
    const [movedShape, movedConn] = moveElements([s, free], 10, 5) as [ShapeElement, ConnectorElement];
    expect(movedShape.x).toBe(s.x + 10);
    expect(movedConn.from).toEqual({ x: 10, y: 5 });
    expect(movedConn.to.elementId).toBe(s.id); // attached end follows the element instead
  });

  it('resizes from any corner without going below the minimum size', () => {
    const s = { ...createShape('server', at(100, 100), 'me', 1), x: 0, y: 0, w: 100, h: 100 };
    expect(resizeShape(s, { x: 0, y: 0, w: 100, h: 100 }, 'se', at(200, 150))).toMatchObject({ x: 0, y: 0, w: 200, h: 150 });
    expect(resizeShape(s, { x: 0, y: 0, w: 100, h: 100 }, 'nw', at(-50, -20))).toMatchObject({ x: -50, y: -20, w: 150, h: 120 });
    const tiny = resizeShape(s, { x: 0, y: 0, w: 100, h: 100 }, 'se', at(1, 1));
    expect(tiny.w).toBe(60);
    expect(tiny.h).toBe(40);
  });

  it('deletes connectors attached to deleted shapes', () => {
    const a = createShape('server', at(0, 0), 'me', 1);
    const b = createShape('cache', at(300, 0), 'me', 2);
    const c = createConnector(endpointFor(a, at(0, 0)), endpointFor(b, at(0, 0)), 'me', 3);
    expect(idsToDelete(new Set([a.id]), [a, b, c]).sort()).toEqual([a.id, c.id].sort());
  });

  it('groups and ungroups', () => {
    const a = createShape('server', at(0, 0), 'me', 1);
    const b = createShape('cache', at(300, 0), 'me', 2);
    const grouped = groupElements([a, b]);
    expect(grouped[0].groupId).toBeTruthy();
    expect(grouped[0].groupId).toBe(grouped[1].groupId);
    expect(ungroupElements(grouped).every((e) => e.groupId === null)).toBe(true);
  });

  it('reorders layers', () => {
    const [a, b, c] = [1, 2, 3].map((z) => createShape('server', at(0, 0), 'me', z));
    const all = [a, b, c];
    const order = (changed: ShapeElement[]) => {
      const byId = new Map(all.map((e) => [e.id, e.z]));
      for (const e of changed) byId.set(e.id, e.z);
      return [...all].sort((x, y) => byId.get(x.id)! - byId.get(y.id)!).map((e) => e.id);
    };
    expect(order(reorder(new Set([a.id]), all, 'front') as ShapeElement[])).toEqual([b.id, c.id, a.id]);
    expect(order(reorder(new Set([c.id]), all, 'back') as ShapeElement[])).toEqual([c.id, a.id, b.id]);
    expect(order(reorder(new Set([a.id]), all, 'forward') as ShapeElement[])).toEqual([b.id, a.id, c.id]);
    expect(order(reorder(new Set([c.id]), all, 'backward') as ShapeElement[])).toEqual([a.id, c.id, b.id]);
    expect(reorder(new Set([c.id]), all, 'forward')).toEqual([]);
  });
});
