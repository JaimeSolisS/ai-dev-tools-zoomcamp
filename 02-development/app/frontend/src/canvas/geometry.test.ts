import { describe, expect, it } from 'vitest';
import {
  alignToOthers,
  connectorGeometry,
  fitViewport,
  indexElements,
  rectBoundaryPoint,
  screenToWorld,
  snap,
  strokeHit,
  worldToScreen,
  zoomAt,
} from './geometry';
import type { ConnectorElement, ShapeElement, StrokeElement } from './types';

const meta = { z: 0, version: { clock: 1, actor: 'a' }, createdBy: 'a', createdAt: '', updatedBy: 'a' };

describe('geometry', () => {
  it('snaps to the grid', () => {
    expect(snap(29)).toBe(20);
    expect(snap(31)).toBe(40);
  });

  it('finds the rectangle boundary towards a point', () => {
    expect(rectBoundaryPoint({ x: 0, y: 0, w: 100, h: 50 }, { x: 500, y: 25 })).toEqual({ x: 100, y: 25 });
    expect(rectBoundaryPoint({ x: 0, y: 0, w: 100, h: 50 }, { x: 50, y: -300 })).toEqual({ x: 50, y: 0 });
  });

  it('keeps connectors attached when elements move', () => {
    const a: ShapeElement = { ...meta, id: 'a', kind: 'shape', componentType: 'service', x: 0, y: 0, w: 100, h: 50, label: '' };
    const b: ShapeElement = { ...a, id: 'b', x: 300 };
    const c: ConnectorElement = {
      ...meta,
      id: 'c',
      kind: 'connector',
      from: { elementId: 'a', x: 0, y: 0 },
      to: { elementId: 'b', x: 0, y: 0 },
      routing: 'straight',
      arrowStart: false,
      arrowEnd: true,
      label: '',
      dashed: false,
      color: '#000',
      width: 2,
    };
    const g1 = connectorGeometry(c, indexElements([a, b, c]));
    expect(g1.start).toEqual({ x: 100, y: 25 });
    expect(g1.end).toEqual({ x: 300, y: 25 });
    const moved = { ...b, y: 400 };
    const g2 = connectorGeometry(c, indexElements([a, moved, c]));
    expect(g2.end.y).toBe(400);
    for (const routing of ['elbow', 'curved'] as const) {
      expect(connectorGeometry({ ...c, routing }, indexElements([a, b])).path).toMatch(/^M/);
    }
  });

  it('detects eraser contact with a stroke', () => {
    const s: StrokeElement = { ...meta, id: 's', kind: 'stroke', tool: 'pen', points: [0, 0, 100, 0], color: '#000', width: 4 };
    expect(strokeHit(s, { x: 50, y: 5 }, 4)).toBe(true);
    expect(strokeHit(s, { x: 50, y: 30 }, 4)).toBe(false);
  });

  it('aligns a moving box to nearby edges', () => {
    const res = alignToOthers({ x: 103, y: 500, w: 50, h: 50 }, [{ x: 100, y: 0, w: 80, h: 40 }]);
    expect(res.dx).toBe(-3);
    expect(res.guides).toEqual([{ orientation: 'vertical', position: 100 }]);
  });

  it('converts between screen and world coordinates', () => {
    const vp = { x: 100, y: 50, zoom: 2 };
    const world = screenToWorld(vp, { x: 300, y: 250 });
    expect(world).toEqual({ x: 100, y: 100 });
    expect(worldToScreen(vp, world)).toEqual({ x: 300, y: 250 });
    const zoomed = zoomAt(vp, { x: 300, y: 250 }, 4);
    expect(worldToScreen(zoomed, world)).toEqual({ x: 300, y: 250 });
  });

  it('fits content in the viewport', () => {
    const vp = fitViewport({ x: 0, y: 0, w: 1000, h: 500 }, { width: 1120, height: 620 });
    expect(vp.zoom).toBeCloseTo(1);
    expect(worldToScreen(vp, { x: 500, y: 250 })).toEqual({ x: 560, y: 310 });
  });
});
