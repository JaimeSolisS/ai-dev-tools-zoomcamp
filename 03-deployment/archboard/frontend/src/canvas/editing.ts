/** Pure editing operations. Each returns the elements to write (puts) and/or delete. */
import { getComponent } from './catalog';
import { anchorPoint, center, shapeRect, snap as snapValue, type Point, type Rect } from './geometry';
import { newId } from './model';
import type { Anchor, CanvasElement, ComponentType, ConnectorElement, Endpoint, Routing, ShapeElement, StrokeElement } from './types';

const PLACEHOLDER_VERSION = { clock: 0, actor: '' };

function meta(actor: string, z: number) {
  return {
    id: newId('el'),
    z,
    groupId: null,
    version: { ...PLACEHOLDER_VERSION, actor },
    createdBy: actor,
    createdAt: new Date().toISOString(),
    updatedBy: actor,
  };
}

export function createShape(type: ComponentType, at: Point, actor: string, z: number, opts: { snap?: boolean } = {}): ShapeElement {
  const def = getComponent(type);
  let x = at.x - def.width / 2;
  let y = at.y - def.height / 2;
  if (opts.snap) {
    x = snapValue(x);
    y = snapValue(y);
  }
  return {
    ...meta(actor, type === 'boundary' ? -Math.abs(z) - 1 : z),
    kind: 'shape',
    componentType: type,
    x,
    y,
    w: def.width,
    h: def.height,
    label: type === 'sticky' || type === 'text' ? '' : def.defaultLabel,
    description: '',
    ...(type === 'sticky' ? { fill: def.fill } : {}),
  };
}

export interface ConnectorStyle {
  routing: Routing;
  color: string;
  width: 1 | 2 | 3;
  dashed: boolean;
}

export const DEFAULT_CONNECTOR_STYLE: ConnectorStyle = { routing: 'straight', color: '#334155', width: 2, dashed: false };

export function endpointFor(shape: ShapeElement | null, point: Point, anchor: Anchor = 'auto'): Endpoint {
  if (!shape) return { x: point.x, y: point.y };
  const p = anchor === 'auto' ? center(shapeRect(shape)) : anchorPoint(shapeRect(shape), anchor);
  return { elementId: shape.id, anchor, x: p.x, y: p.y };
}

export function createConnector(from: Endpoint, to: Endpoint, actor: string, z: number, style: ConnectorStyle = DEFAULT_CONNECTOR_STYLE): ConnectorElement {
  return {
    ...meta(actor, z),
    kind: 'connector',
    from,
    to,
    routing: style.routing,
    arrowStart: false,
    arrowEnd: true,
    label: '',
    dashed: style.dashed,
    color: style.color,
    width: style.width,
  };
}

export function createStroke(tool: 'pen' | 'highlighter', points: number[], color: string, width: number, actor: string, z: number): StrokeElement {
  return { ...meta(actor, z), kind: 'stroke', tool, points, color, width };
}

/** Move the given elements. Attached connector ends follow automatically; free ends of selected connectors move. */
export function moveElements(elements: CanvasElement[], dx: number, dy: number): CanvasElement[] {
  return elements.map((el) => {
    switch (el.kind) {
      case 'shape':
        return { ...el, x: el.x + dx, y: el.y + dy };
      case 'stroke':
        return { ...el, points: el.points.map((v, i) => v + (i % 2 === 0 ? dx : dy)) };
      case 'connector':
        return {
          ...el,
          from: el.from.elementId ? el.from : { ...el.from, x: el.from.x + dx, y: el.from.y + dy },
          to: el.to.elementId ? el.to : { ...el.to, x: el.to.x + dx, y: el.to.y + dy },
        };
    }
  });
}

export type Handle = 'nw' | 'ne' | 'sw' | 'se';

/** Resize a shape by dragging one corner to `p`, respecting minimum dimensions. */
export function resizeShape(el: ShapeElement, original: Rect, handle: Handle, p: Point, opts: { snap?: boolean } = {}): ShapeElement {
  const def = getComponent(el.componentType);
  const px = opts.snap ? snapValue(p.x) : p.x;
  const py = opts.snap ? snapValue(p.y) : p.y;
  let x1 = original.x;
  let y1 = original.y;
  let x2 = original.x + original.w;
  let y2 = original.y + original.h;
  if (handle.includes('w')) x1 = Math.min(px, x2 - def.minWidth);
  if (handle.includes('e')) x2 = Math.max(px, x1 + def.minWidth);
  if (handle.includes('n')) y1 = Math.min(py, y2 - def.minHeight);
  if (handle.includes('s')) y2 = Math.max(py, y1 + def.minHeight);
  return { ...el, x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

/** Ids to delete: the selection plus connectors attached to deleted shapes. */
export function idsToDelete(selection: Set<string>, elements: CanvasElement[]): string[] {
  const out = new Set(selection);
  for (const el of elements) {
    if (el.kind !== 'connector') continue;
    if ((el.from.elementId && selection.has(el.from.elementId)) || (el.to.elementId && selection.has(el.to.elementId))) out.add(el.id);
  }
  return [...out];
}

export function groupElements(selected: CanvasElement[]): CanvasElement[] {
  const groupId = newId('g');
  return selected.map((el) => ({ ...el, groupId }));
}

export function ungroupElements(selected: CanvasElement[]): CanvasElement[] {
  return selected.filter((el) => el.groupId).map((el) => ({ ...el, groupId: null }));
}

export type LayerMove = 'front' | 'back' | 'forward' | 'backward';

/** Change z-order of the selection. Returns only elements whose z changed. */
export function reorder(selection: Set<string>, all: CanvasElement[], move: LayerMove): CanvasElement[] {
  const sorted = [...all].sort((a, b) => a.z - b.z);
  const selected = sorted.filter((e) => selection.has(e.id));
  if (selected.length === 0) return [];
  if (move === 'front' || move === 'back') {
    const top = Math.max(...sorted.map((e) => e.z));
    const bottom = Math.min(...sorted.map((e) => e.z));
    return selected.map((el, i) => ({ ...el, z: move === 'front' ? top + 1 + i : bottom - selected.length + i }));
  }
  // Swap with the nearest non-selected neighbour.
  const order = sorted.map((e) => e.id);
  const ids = move === 'forward' ? [...order].reverse() : order;
  const result = [...ids];
  for (let i = 1; i < result.length; i++) {
    if (selection.has(result[i]) && !selection.has(result[i - 1])) {
      [result[i - 1], result[i]] = [result[i], result[i - 1]];
    }
  }
  const finalOrder = move === 'forward' ? result.reverse() : result;
  // Reuse the existing z slots; renumber when they are not distinct.
  const slots = sorted.map((e) => e.z);
  const distinct = new Set(slots).size === slots.length;
  const byId = new Map(sorted.map((e) => [e.id, e]));
  const changed: CanvasElement[] = [];
  finalOrder.forEach((id, i) => {
    const el = byId.get(id)!;
    const z = distinct ? slots[i] : slots[0] + i;
    if (el.z !== z) changed.push({ ...el, z });
  });
  return changed;
}
