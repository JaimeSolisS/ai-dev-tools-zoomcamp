import type { Anchor, CanvasElement, ConnectorElement, Endpoint, Routing, ShapeElement, StrokeElement } from './types';

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const GRID_SIZE = 20;

export function snap(value: number, grid = GRID_SIZE): number {
  return Math.round(value / grid) * grid;
}

export function normalizeRect(a: Point, b: Point): Rect {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) };
}

export function rectsIntersect(a: Rect, b: Rect): boolean {
  return a.x <= b.x + b.w && a.x + a.w >= b.x && a.y <= b.y + b.h && a.y + a.h >= b.y;
}

export function rectContainsPoint(r: Rect, p: Point, pad = 0): boolean {
  return p.x >= r.x - pad && p.x <= r.x + r.w + pad && p.y >= r.y - pad && p.y <= r.y + r.h + pad;
}

export function unionRects(rects: Rect[]): Rect | null {
  if (rects.length === 0) return null;
  let x1 = Infinity;
  let y1 = Infinity;
  let x2 = -Infinity;
  let y2 = -Infinity;
  for (const r of rects) {
    x1 = Math.min(x1, r.x);
    y1 = Math.min(y1, r.y);
    x2 = Math.max(x2, r.x + r.w);
    y2 = Math.max(y2, r.y + r.h);
  }
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

export function center(r: Rect): Point {
  return { x: r.x + r.w / 2, y: r.y + r.h / 2 };
}

export function anchorPoint(r: Rect, anchor: Exclude<Anchor, 'auto'>): Point {
  switch (anchor) {
    case 'top':
      return { x: r.x + r.w / 2, y: r.y };
    case 'right':
      return { x: r.x + r.w, y: r.y + r.h / 2 };
    case 'bottom':
      return { x: r.x + r.w / 2, y: r.y + r.h };
    case 'left':
      return { x: r.x, y: r.y + r.h / 2 };
  }
}

export const ANCHORS: Exclude<Anchor, 'auto'>[] = ['top', 'right', 'bottom', 'left'];

/** Point where the ray from the rect centre towards `toward` leaves the rect. */
export function rectBoundaryPoint(r: Rect, toward: Point): Point {
  const c = center(r);
  const dx = toward.x - c.x;
  const dy = toward.y - c.y;
  if (dx === 0 && dy === 0) return c;
  const sx = dx === 0 ? Infinity : r.w / 2 / Math.abs(dx);
  const sy = dy === 0 ? Infinity : r.h / 2 / Math.abs(dy);
  const s = Math.min(sx, sy);
  return { x: c.x + dx * s, y: c.y + dy * s };
}

/** Which side of `r` a boundary point lies on (used to orient elbow/curve routes). */
export function sideOf(r: Rect, p: Point): Exclude<Anchor, 'auto'> {
  const d = [
    ['top', Math.abs(p.y - r.y)],
    ['right', Math.abs(p.x - (r.x + r.w))],
    ['bottom', Math.abs(p.y - (r.y + r.h))],
    ['left', Math.abs(p.x - r.x)],
  ] as const;
  return d.reduce((best, cur) => (cur[1] < best[1] ? cur : best))[0];
}

export function shapeRect(el: ShapeElement): Rect {
  return { x: el.x, y: el.y, w: el.w, h: el.h };
}

export function strokeBounds(el: StrokeElement): Rect {
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < el.points.length; i += 2) {
    xs.push(el.points[i]);
    ys.push(el.points[i + 1]);
  }
  if (xs.length === 0) return { x: 0, y: 0, w: 0, h: 0 };
  const pad = el.width / 2;
  const x = Math.min(...xs) - pad;
  const y = Math.min(...ys) - pad;
  return { x, y, w: Math.max(...xs) + pad - x, h: Math.max(...ys) + pad - y };
}

export type ElementIndex = Map<string, CanvasElement>;

export function indexElements(elements: CanvasElement[]): ElementIndex {
  return new Map(elements.map((el) => [el.id, el]));
}

interface ResolvedEnd {
  point: Point;
  side: Exclude<Anchor, 'auto'> | null;
}

function attachedRect(ep: Endpoint, index: ElementIndex): Rect | null {
  if (!ep.elementId) return null;
  const el = index.get(ep.elementId);
  return el && el.kind === 'shape' ? shapeRect(el) : null;
}

function resolveEnd(ep: Endpoint, other: Endpoint, index: ElementIndex): ResolvedEnd {
  const rect = attachedRect(ep, index);
  if (!rect) return { point: { x: ep.x, y: ep.y }, side: null };
  if (ep.anchor && ep.anchor !== 'auto') return { point: anchorPoint(rect, ep.anchor), side: ep.anchor };
  const otherRect = attachedRect(other, index);
  const target = otherRect ? center(otherRect) : { x: other.x, y: other.y };
  const point = rectBoundaryPoint(rect, target);
  return { point, side: sideOf(rect, point) };
}

export interface ConnectorGeometry {
  start: Point;
  end: Point;
  path: string;
  mid: Point;
  /** Direction of travel at each end (for arrowheads), as angles in radians. */
  startAngle: number;
  endAngle: number;
}

const OUT: Record<Exclude<Anchor, 'auto'>, Point> = {
  top: { x: 0, y: -1 },
  right: { x: 1, y: 0 },
  bottom: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
};

export function connectorGeometry(el: ConnectorElement, index: ElementIndex): ConnectorGeometry {
  const a = resolveEnd(el.from, el.to, index);
  const b = resolveEnd(el.to, el.from, index);
  return routeBetween(el.routing, a, b);
}

export function routeBetween(routing: Routing, a: ResolvedEnd, b: ResolvedEnd): ConnectorGeometry {
  const s = a.point;
  const e = b.point;
  const angle = (from: Point, to: Point) => Math.atan2(to.y - from.y, to.x - from.x);

  if (routing === 'elbow') {
    const horizontalFirst = a.side ? a.side === 'left' || a.side === 'right' : Math.abs(e.x - s.x) >= Math.abs(e.y - s.y);
    let pts: Point[];
    if (horizontalFirst) {
      const mx = (s.x + e.x) / 2;
      pts = [s, { x: mx, y: s.y }, { x: mx, y: e.y }, e];
    } else {
      const my = (s.y + e.y) / 2;
      pts = [s, { x: s.x, y: my }, { x: e.x, y: my }, e];
    }
    const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${round(p.x)} ${round(p.y)}`).join(' ');
    return {
      start: s,
      end: e,
      path,
      mid: { x: (pts[1].x + pts[2].x) / 2, y: (pts[1].y + pts[2].y) / 2 },
      startAngle: angle(pts[1], s),
      endAngle: angle(pts[2], e),
    };
  }

  if (routing === 'curved') {
    const dist = Math.max(40, Math.hypot(e.x - s.x, e.y - s.y) / 2.5);
    const dirA = a.side ? OUT[a.side] : unit(s, e);
    const dirB = b.side ? OUT[b.side] : unit(e, s);
    const c1 = { x: s.x + dirA.x * dist, y: s.y + dirA.y * dist };
    const c2 = { x: e.x + dirB.x * dist, y: e.y + dirB.y * dist };
    const path = `M${round(s.x)} ${round(s.y)} C${round(c1.x)} ${round(c1.y)} ${round(c2.x)} ${round(c2.y)} ${round(e.x)} ${round(e.y)}`;
    const mid = {
      x: 0.125 * s.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * e.x,
      y: 0.125 * s.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * e.y,
    };
    return { start: s, end: e, path, mid, startAngle: angle(c1, s), endAngle: angle(c2, e) };
  }

  return {
    start: s,
    end: e,
    path: `M${round(s.x)} ${round(s.y)} L${round(e.x)} ${round(e.y)}`,
    mid: { x: (s.x + e.x) / 2, y: (s.y + e.y) / 2 },
    startAngle: angle(e, s),
    endAngle: angle(s, e),
  };
}

function unit(from: Point, to: Point): Point {
  const d = Math.hypot(to.x - from.x, to.y - from.y) || 1;
  return { x: (to.x - from.x) / d, y: (to.y - from.y) / d };
}

function round(v: number): number {
  return Math.round(v * 10) / 10;
}

export function arrowHead(tip: Point, angle: number, size: number): string {
  const spread = Math.PI / 7;
  const p1 = { x: tip.x - size * Math.cos(angle - spread), y: tip.y - size * Math.sin(angle - spread) };
  const p2 = { x: tip.x - size * Math.cos(angle + spread), y: tip.y - size * Math.sin(angle + spread) };
  return `M${round(p1.x)} ${round(p1.y)} L${round(tip.x)} ${round(tip.y)} L${round(p2.x)} ${round(p2.y)} Z`;
}

export function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  let t = len2 === 0 ? 0 : ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** True when a circle of `radius` around `p` touches the stroke. */
export function strokeHit(el: StrokeElement, p: Point, radius: number): boolean {
  const pts = el.points;
  const reach = radius + el.width / 2;
  if (pts.length === 2) return Math.hypot(p.x - pts[0], p.y - pts[1]) <= reach;
  for (let i = 0; i + 3 < pts.length; i += 2) {
    if (distanceToSegment(p, { x: pts[i], y: pts[i + 1] }, { x: pts[i + 2], y: pts[i + 3] }) <= reach) return true;
  }
  return false;
}

/** Smooth SVG path through freehand points using quadratic midpoints. */
export function strokePath(points: number[]): string {
  if (points.length < 2) return '';
  if (points.length === 2) {
    const [x, y] = points;
    return `M${round(x)} ${round(y)} L${round(x + 0.1)} ${round(y + 0.1)}`;
  }
  let d = `M${round(points[0])} ${round(points[1])}`;
  for (let i = 2; i + 2 < points.length; i += 2) {
    const mx = (points[i] + points[i + 2]) / 2;
    const my = (points[i + 1] + points[i + 3]) / 2;
    d += ` Q${round(points[i])} ${round(points[i + 1])} ${round(mx)} ${round(my)}`;
  }
  const n = points.length;
  d += ` L${round(points[n - 2])} ${round(points[n - 1])}`;
  return d;
}

export function elementBounds(el: CanvasElement, index: ElementIndex): Rect {
  switch (el.kind) {
    case 'shape':
      return shapeRect(el);
    case 'stroke':
      return strokeBounds(el);
    case 'connector': {
      const g = connectorGeometry(el, index);
      return normalizeRect(g.start, g.end);
    }
  }
}

// ---------------------------------------------------------------------------
// Alignment guides
// ---------------------------------------------------------------------------

export interface Guide {
  orientation: 'vertical' | 'horizontal';
  /** x for vertical guides, y for horizontal guides. */
  position: number;
}

/**
 * Snap a moving box to the edges/centres of other boxes. Returns the
 * correction to apply and the guides to draw.
 */
export function alignToOthers(moving: Rect, others: Rect[], threshold = 6): { dx: number; dy: number; guides: Guide[] } {
  const xs = [moving.x, moving.x + moving.w / 2, moving.x + moving.w];
  const ys = [moving.y, moving.y + moving.h / 2, moving.y + moving.h];
  let bestX: { delta: number; pos: number } | null = null;
  let bestY: { delta: number; pos: number } | null = null;
  for (const o of others) {
    for (const ox of [o.x, o.x + o.w / 2, o.x + o.w]) {
      for (const mx of xs) {
        const delta = ox - mx;
        if (Math.abs(delta) <= threshold && (!bestX || Math.abs(delta) < Math.abs(bestX.delta))) bestX = { delta, pos: ox };
      }
    }
    for (const oy of [o.y, o.y + o.h / 2, o.y + o.h]) {
      for (const my of ys) {
        const delta = oy - my;
        if (Math.abs(delta) <= threshold && (!bestY || Math.abs(delta) < Math.abs(bestY.delta))) bestY = { delta, pos: oy };
      }
    }
  }
  const guides: Guide[] = [];
  if (bestX) guides.push({ orientation: 'vertical', position: bestX.pos });
  if (bestY) guides.push({ orientation: 'horizontal', position: bestY.pos });
  return { dx: bestX?.delta ?? 0, dy: bestY?.delta ?? 0, guides };
}

// ---------------------------------------------------------------------------
// Viewport
// ---------------------------------------------------------------------------

export interface Viewport {
  /** Screen-space offset of the world origin. */
  x: number;
  y: number;
  zoom: number;
}

export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 4;

export function clampZoom(z: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

export function screenToWorld(vp: Viewport, p: Point): Point {
  return { x: (p.x - vp.x) / vp.zoom, y: (p.y - vp.y) / vp.zoom };
}

export function worldToScreen(vp: Viewport, p: Point): Point {
  return { x: p.x * vp.zoom + vp.x, y: p.y * vp.zoom + vp.y };
}

/** Zoom around a screen point, keeping that point fixed. */
export function zoomAt(vp: Viewport, screen: Point, nextZoom: number): Viewport {
  const zoom = clampZoom(nextZoom);
  const world = screenToWorld(vp, screen);
  return { zoom, x: screen.x - world.x * zoom, y: screen.y - world.y * zoom };
}

export function fitViewport(bounds: Rect | null, size: { width: number; height: number }, padding = 60): Viewport {
  if (!bounds || bounds.w === 0 || bounds.h === 0) return { x: size.width / 2, y: size.height / 2, zoom: 1 };
  const zoom = clampZoom(
    Math.min((size.width - padding * 2) / bounds.w, (size.height - padding * 2) / bounds.h, 1.5),
  );
  return {
    zoom,
    x: size.width / 2 - (bounds.x + bounds.w / 2) * zoom,
    y: size.height / 2 - (bounds.y + bounds.h / 2) * zoom,
  };
}
