import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { getComponent } from '../../canvas/catalog';
import {
  createConnector,
  createShape,
  createStroke,
  endpointFor,
  moveElements,
  resizeShape,
  type ConnectorStyle,
  type Handle,
} from '../../canvas/editing';
import {
  alignToOthers,
  ANCHORS,
  anchorPoint,
  connectorGeometry,
  elementBounds,
  indexElements,
  normalizeRect,
  rectContainsPoint,
  rectsIntersect,
  screenToWorld,
  shapeRect,
  snap,
  strokeHit,
  strokePath,
  unionRects,
  worldToScreen,
  zoomAt,
  GRID_SIZE,
  type Guide,
  type Point,
  type Rect,
  type Viewport,
} from '../../canvas/geometry';
import { expandToGroups } from '../../canvas/model';
import type { Anchor, CanvasElement, ComponentType, ConnectorElement, ShapeElement } from '../../canvas/types';
import type { Presence } from '../../services';
import { describeElement, ElementView } from './ElementView';

export type Tool = 'select' | 'hand' | 'pen' | 'highlighter' | 'eraser' | 'text' | 'sticky' | 'connector';

export interface ToolOptions {
  penColor: string;
  penWidth: number;
  highlighterColor: string;
  connector: ConnectorStyle;
}

export const COMPONENT_DRAG_TYPE = 'application/x-archboard-component';

interface Props {
  elements: CanvasElement[];
  selection: Set<string>;
  onSelectionChange(selection: Set<string>): void;
  viewport: Viewport;
  onViewportChange(vp: Viewport): void;
  onSizeChange?(size: { width: number; height: number }): void;
  tool: Tool;
  toolOptions: ToolOptions;
  onToolDone(): void;
  canEdit: boolean;
  snapToGrid: boolean;
  me: { id: string; color: string; displayName: string };
  presence: Presence[];
  showCursors: boolean;
  editingId: string | null;
  onEditingChange(id: string | null): void;
  commit(puts: CanvasElement[], deletes?: string[], options?: { history?: boolean }): void;
  beginGesture(): void;
  endGesture(): void;
  onCursor(point: Point | null): void;
  nextZ(): number;
}

type Drag =
  | { mode: 'pan'; start: Point; origin: Viewport }
  | { mode: 'marquee'; start: Point; additive: boolean; base: Set<string> }
  | { mode: 'move'; start: Point; originals: CanvasElement[]; started: boolean; bbox: Rect | null }
  | { mode: 'resize'; handle: Handle; original: ShapeElement }
  | { mode: 'draw'; tool: 'pen' | 'highlighter'; points: number[] }
  | { mode: 'erase' }
  | { mode: 'connect'; from: { shape: ShapeElement | null; point: Point; anchor: Anchor } }
  | { mode: 'endpoint'; connector: ConnectorElement; end: 'from' | 'to'; started: boolean };

const MOVE_THRESHOLD = 3;

export function CanvasView(props: Props) {
  const {
    elements,
    selection,
    onSelectionChange,
    viewport,
    onViewportChange,
    onSizeChange,
    tool,
    toolOptions,
    onToolDone,
    canEdit,
    snapToGrid,
    me,
    presence,
    showCursors,
    editingId,
    onEditingChange,
    commit,
    beginGesture,
    endGesture,
    onCursor,
    nextZ,
  } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const [marquee, setMarquee] = useState<Rect | null>(null);
  const [guides, setGuides] = useState<Guide[]>([]);
  const [drawPreview, setDrawPreview] = useState<number[] | null>(null);
  const [connectPreview, setConnectPreview] = useState<{ from: Point; to: Point } | null>(null);
  const [hoverShapeId, setHoverShapeId] = useState<string | null>(null);
  const [spaceHeld, setSpaceHeld] = useState(false);

  const index = useMemo(() => indexElements(elements), [elements]);
  const shapes = useMemo(() => elements.filter((e): e is ShapeElement => e.kind === 'shape'), [elements]);
  const vpRef = useRef(viewport);
  vpRef.current = viewport;

  // Report container size (for zoom-to-fit).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el || !onSizeChange) return;
    const report = () => onSizeChange({ width: el.clientWidth, height: el.clientHeight });
    report();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(report);
    ro.observe(el);
    return () => ro.disconnect();
  }, [onSizeChange]);

  // Wheel: scroll pans, ctrl/cmd + wheel (or pinch) zooms. Needs a non-passive listener.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const vp = vpRef.current;
      if (e.ctrlKey || e.metaKey) {
        const factor = Math.exp(-e.deltaY * 0.01);
        onViewportChange(zoomAt(vp, { x: e.clientX - rect.left, y: e.clientY - rect.top }, vp.zoom * factor));
      } else {
        onViewportChange({ ...vp, x: vp.x - e.deltaX, y: vp.y - e.deltaY });
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [onViewportChange]);

  // Hold space to pan temporarily.
  useEffect(() => {
    const isTyping = (t: EventTarget | null) =>
      t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));
    const down = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !isTyping(e.target)) {
        if (!e.repeat) setSpaceHeld(true);
        e.preventDefault();
      }
    };
    const up = (e: KeyboardEvent) => e.code === 'Space' && setSpaceHeld(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  const toWorld = useCallback((clientX: number, clientY: number): Point => {
    const rect = containerRef.current!.getBoundingClientRect();
    return screenToWorld(vpRef.current, { x: clientX - rect.left, y: clientY - rect.top });
  }, []);

  /** Topmost shape under a world point; boundaries only count near their edge or header. */
  const shapeAt = useCallback(
    (p: Point, exclude?: string): ShapeElement | null => {
      for (let i = shapes.length - 1; i >= 0; i--) {
        const s = shapes[i];
        if (s.id === exclude || !rectContainsPoint(shapeRect(s), p, 4)) continue;
        if (s.componentType === 'boundary') {
          const inner = { x: s.x + 10, y: s.y + 32, w: s.w - 20, h: s.h - 42 };
          if (rectContainsPoint(inner, p)) continue;
        }
        return s;
      }
      return null;
    },
    [shapes],
  );

  const selectOnly = useCallback(
    (ids: Iterable<string>) => onSelectionChange(expandToGroups(ids, elements)),
    [elements, onSelectionChange],
  );

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button === 2) return;
    const target = e.target as Element;
    if (target.closest('.canvas-text-editor')) return;
    // We manage focus ourselves; this also stops element focus from re-selecting on shift-click.
    e.preventDefault();
    containerRef.current?.focus({ preventScroll: true });
    const world = toWorld(e.clientX, e.clientY);
    const capture = () => containerRef.current?.setPointerCapture?.(e.pointerId);

    if (e.button === 1 || tool === 'hand' || spaceHeld) {
      dragRef.current = { mode: 'pan', start: { x: e.clientX, y: e.clientY }, origin: vpRef.current };
      capture();
      return;
    }

    const handle = target.closest('[data-handle]')?.getAttribute('data-handle') as Handle | null;
    const endpoint = target.closest('[data-endpoint]')?.getAttribute('data-endpoint') as 'from' | 'to' | null;
    const hitId = target.closest('[data-element-id]')?.getAttribute('data-element-id') ?? null;

    if (tool === 'select') {
      if (handle && canEdit && selection.size === 1) {
        const el = index.get([...selection][0]);
        if (el?.kind === 'shape') {
          beginGesture();
          dragRef.current = { mode: 'resize', handle, original: el };
          capture();
          return;
        }
      }
      if (endpoint && canEdit && selection.size === 1) {
        const el = index.get([...selection][0]);
        if (el?.kind === 'connector') {
          dragRef.current = { mode: 'endpoint', connector: el, end: endpoint, started: false };
          capture();
          return;
        }
      }
      if (hitId) {
        let next = selection;
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          const group = expandToGroups([hitId], elements);
          next = new Set(selection);
          const removing = selection.has(hitId);
          for (const id of group) removing ? next.delete(id) : next.add(id);
          onSelectionChange(next);
        } else if (!selection.has(hitId)) {
          next = expandToGroups([hitId], elements);
          onSelectionChange(next);
        }
        if (canEdit && next.has(hitId)) {
          const originals = elements.filter((el) => next.has(el.id));
          const shapeRects = originals.filter((o): o is ShapeElement => o.kind === 'shape').map(shapeRect);
          dragRef.current = { mode: 'move', start: world, originals, started: false, bbox: unionRects(shapeRects) };
          capture();
        }
        return;
      }
      const additive = e.shiftKey || e.metaKey || e.ctrlKey;
      if (!additive && selection.size) onSelectionChange(new Set());
      dragRef.current = { mode: 'marquee', start: world, additive, base: additive ? selection : new Set() };
      capture();
      return;
    }

    if (!canEdit) return;

    if (tool === 'pen' || tool === 'highlighter') {
      dragRef.current = { mode: 'draw', tool, points: [world.x, world.y] };
      setDrawPreview([world.x, world.y]);
      capture();
      return;
    }
    if (tool === 'eraser') {
      beginGesture();
      dragRef.current = { mode: 'erase' };
      eraseAt(world);
      capture();
      return;
    }
    if (tool === 'text' || tool === 'sticky') {
      const shape = createShape(tool, world, me.id, nextZ(), { snap: snapToGrid });
      commit([shape]);
      onSelectionChange(new Set([shape.id]));
      onEditingChange(shape.id);
      onToolDone();
      return;
    }
    if (tool === 'connector') {
      const anchorAttr = target.closest('[data-anchor]')?.getAttribute('data-anchor') as Anchor | null;
      const shape = shapeAt(world);
      const point = shape && anchorAttr ? anchorPoint(shapeRect(shape), anchorAttr as Exclude<Anchor, 'auto'>) : world;
      dragRef.current = { mode: 'connect', from: { shape, point, anchor: anchorAttr ?? 'auto' } };
      setConnectPreview({ from: point, to: world });
      capture();
    }
  };

  const eraseAt = (p: Point) => {
    const radius = 8 / vpRef.current.zoom;
    const hits = elements.filter((el) => el.kind === 'stroke' && strokeHit(el, p, radius)).map((el) => el.id);
    if (hits.length) {
      commit([], hits);
      if (hits.some((id) => selection.has(id))) {
        onSelectionChange(new Set([...selection].filter((id) => !hits.includes(id))));
      }
    }
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const world = toWorld(e.clientX, e.clientY);
    onCursor(world);
    const drag = dragRef.current;

    if (!drag) {
      if (tool === 'connector') setHoverShapeId(shapeAt(world)?.id ?? null);
      return;
    }

    switch (drag.mode) {
      case 'pan':
        onViewportChange({
          ...drag.origin,
          x: drag.origin.x + e.clientX - drag.start.x,
          y: drag.origin.y + e.clientY - drag.start.y,
        });
        return;
      case 'marquee': {
        const rect = normalizeRect(drag.start, world);
        setMarquee(rect);
        return;
      }
      case 'move': {
        let dx = world.x - drag.start.x;
        let dy = world.y - drag.start.y;
        const zoom = vpRef.current.zoom;
        if (!drag.started) {
          if (Math.hypot(dx, dy) * zoom < MOVE_THRESHOLD) return;
          drag.started = true;
          beginGesture();
        }
        if (drag.bbox) {
          if (snapToGrid) {
            dx = snap(drag.bbox.x + dx) - drag.bbox.x;
            dy = snap(drag.bbox.y + dy) - drag.bbox.y;
            setGuides([]);
          } else {
            const movingIds = new Set(drag.originals.map((o) => o.id));
            const others = shapes.filter((s) => !movingIds.has(s.id) && s.componentType !== 'boundary').map(shapeRect);
            const moved = { ...drag.bbox, x: drag.bbox.x + dx, y: drag.bbox.y + dy };
            const align = alignToOthers(moved, others, 6 / zoom);
            dx += align.dx;
            dy += align.dy;
            setGuides(align.guides);
          }
        }
        commit(moveElements(drag.originals, dx, dy));
        return;
      }
      case 'resize':
        commit([resizeShape(drag.original, shapeRect(drag.original), drag.handle, world, { snap: snapToGrid })]);
        return;
      case 'draw': {
        const n = drag.points.length;
        const minDist = 1.5 / vpRef.current.zoom;
        if (Math.hypot(world.x - drag.points[n - 2], world.y - drag.points[n - 1]) >= minDist) {
          drag.points.push(Math.round(world.x * 10) / 10, Math.round(world.y * 10) / 10);
          setDrawPreview([...drag.points]);
        }
        return;
      }
      case 'erase':
        eraseAt(world);
        return;
      case 'connect': {
        const target = shapeAt(world, drag.from.shape?.id);
        setHoverShapeId(target?.id ?? null);
        setConnectPreview({ from: drag.from.point, to: world });
        return;
      }
      case 'endpoint': {
        if (!drag.started) {
          drag.started = true;
          beginGesture();
        }
        const target = shapeAt(world);
        setHoverShapeId(target?.id ?? null);
        commit([{ ...drag.connector, [drag.end]: { x: world.x, y: world.y } }]);
        return;
      }
    }
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;
    const world = toWorld(e.clientX, e.clientY);

    switch (drag.mode) {
      case 'marquee': {
        const rect = normalizeRect(drag.start, world);
        setMarquee(null);
        if (rect.w < 2 && rect.h < 2) return;
        const hit = elements.filter((el) => rectsIntersect(rect, elementBounds(el, index))).map((el) => el.id);
        selectOnly([...drag.base, ...hit]);
        return;
      }
      case 'move':
        setGuides([]);
        if (drag.started) endGesture();
        return;
      case 'resize':
        endGesture();
        return;
      case 'draw': {
        setDrawPreview(null);
        const isHighlighter = drag.tool === 'highlighter';
        const stroke = createStroke(
          drag.tool,
          drag.points,
          isHighlighter ? toolOptions.highlighterColor : toolOptions.penColor,
          isHighlighter ? Math.max(12, toolOptions.penWidth * 4) : toolOptions.penWidth,
          me.id,
          nextZ(),
        );
        commit([stroke]);
        return;
      }
      case 'erase':
        endGesture();
        return;
      case 'connect': {
        setConnectPreview(null);
        setHoverShapeId(null);
        const target = shapeAt(world, drag.from.shape?.id);
        const anchorAttr = (e.target as Element).closest?.('[data-anchor]')?.getAttribute('data-anchor') as Anchor | null;
        if (!target && Math.hypot(world.x - drag.from.point.x, world.y - drag.from.point.y) < 10) return;
        const from = drag.from.shape ? endpointFor(drag.from.shape, drag.from.point, drag.from.anchor) : { x: drag.from.point.x, y: drag.from.point.y };
        const to = endpointFor(target, world, target && anchorAttr ? anchorAttr : 'auto');
        const connector = createConnector(from, to, me.id, nextZ(), toolOptions.connector);
        commit([connector]);
        onSelectionChange(new Set([connector.id]));
        return;
      }
      case 'endpoint': {
        setHoverShapeId(null);
        if (!drag.started) return;
        const target = shapeAt(world);
        const other = drag.end === 'from' ? drag.connector.to : drag.connector.from;
        const valid = target && target.id !== other.elementId ? target : null;
        commit([{ ...drag.connector, [drag.end]: endpointFor(valid, world) }]);
        endGesture();
        return;
      }
      case 'pan':
        return;
    }
  };

  const onDoubleClick = (e: React.MouseEvent) => {
    if (!canEdit || tool !== 'select') return;
    const id = (e.target as Element).closest('[data-element-id]')?.getAttribute('data-element-id');
    const el = id ? index.get(id) : null;
    if (el && el.kind !== 'stroke') {
      onSelectionChange(new Set([el.id]));
      onEditingChange(el.id);
      return;
    }
    if (!id) {
      const shape = createShape('text', toWorld(e.clientX, e.clientY), me.id, nextZ(), { snap: snapToGrid });
      commit([shape]);
      onSelectionChange(new Set([shape.id]));
      onEditingChange(shape.id);
    }
  };

  const onDragOver = (e: React.DragEvent) => {
    if (canEdit && e.dataTransfer.types.includes(COMPONENT_DRAG_TYPE)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  };

  const onDrop = (e: React.DragEvent) => {
    const type = e.dataTransfer.getData(COMPONENT_DRAG_TYPE) as ComponentType;
    if (!canEdit || !type) return;
    e.preventDefault();
    const shape = createShape(type, toWorld(e.clientX, e.clientY), me.id, nextZ(), { snap: snapToGrid });
    commit([shape]);
    onSelectionChange(new Set([shape.id]));
  };

  const zoom = viewport.zoom;
  const selected = elements.filter((el) => selection.has(el.id));
  const single = selected.length === 1 ? selected[0] : null;
  const presenceColor = new Map(presence.map((p) => [p.participantId, p]));
  const cursorClass = spaceHeld || tool === 'hand' ? 'tool-hand' : `tool-${tool}`;
  const gridSize = GRID_SIZE * zoom;

  return (
    <div
      ref={containerRef}
      className={`canvas-container ${cursorClass}${canEdit ? '' : ' read-only'}`}
      tabIndex={-1}
      data-testid="canvas"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={() => onCursor(null)}
      onDoubleClick={onDoubleClick}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <svg className="canvas-svg" width="100%" height="100%" aria-label="Interview canvas" role="application">
        <defs>
          <pattern
            id="canvas-grid"
            width={gridSize}
            height={gridSize}
            patternUnits="userSpaceOnUse"
            x={viewport.x % gridSize}
            y={viewport.y % gridSize}
          >
            <circle cx={1} cy={1} r={zoom > 0.5 ? 1 : 0.6} fill="#cbd5e1" />
          </pattern>
        </defs>
        {zoom > 0.25 && <rect width="100%" height="100%" fill="url(#canvas-grid)" />}
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${zoom})`}>
          {elements.map((el) => (
            <g
              key={el.id}
              data-element-id={el.id}
              className="canvas-element"
              tabIndex={0}
              aria-label={describeElement(el)}
              aria-selected={selection.has(el.id)}
              onFocus={() => !selection.has(el.id) && selectOnly([el.id])}
            >
              <ElementView element={el} index={index} editing={editingId === el.id} />
            </g>
          ))}

          {drawPreview && (
            <path
              d={strokePath(drawPreview)}
              fill="none"
              stroke={tool === 'highlighter' ? toolOptions.highlighterColor : toolOptions.penColor}
              strokeWidth={tool === 'highlighter' ? Math.max(12, toolOptions.penWidth * 4) : toolOptions.penWidth}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={tool === 'highlighter' ? 0.35 : 1}
              pointerEvents="none"
            />
          )}

          {connectPreview && (
            <line
              x1={connectPreview.from.x}
              y1={connectPreview.from.y}
              x2={connectPreview.to.x}
              y2={connectPreview.to.y}
              stroke={toolOptions.connector.color}
              strokeWidth={toolOptions.connector.width}
              strokeDasharray="6 4"
              pointerEvents="none"
            />
          )}

          {(tool === 'connector' || dragRef.current?.mode === 'endpoint') &&
            hoverShapeId &&
            (() => {
              const s = index.get(hoverShapeId);
              if (!s || s.kind !== 'shape') return null;
              const r = shapeRect(s);
              return (
                <g className="anchor-points">
                  <rect x={r.x - 3} y={r.y - 3} width={r.w + 6} height={r.h + 6} rx={6} fill="none" stroke="#6366f1" strokeWidth={1.5 / zoom} pointerEvents="none" />
                  {ANCHORS.map((a) => {
                    const p = anchorPoint(r, a);
                    return <circle key={a} data-anchor={a} cx={p.x} cy={p.y} r={5 / zoom} fill="#fff" stroke="#6366f1" strokeWidth={1.5 / zoom} />;
                  })}
                </g>
              );
            })()}

          {/* Remote selections, labelled with the participant's name (not colour alone). */}
          {presence.map((p) =>
            p.selection.map((id) => {
              const el = index.get(id);
              if (!el) return null;
              const b = elementBounds(el, index);
              const pad = 6 / zoom;
              return (
                <g key={`${p.participantId}-${id}`} pointerEvents="none">
                  <rect x={b.x - pad} y={b.y - pad} width={b.w + pad * 2} height={b.h + pad * 2} fill="none" stroke={p.color} strokeWidth={2 / zoom} rx={4 / zoom} />
                  <g transform={`translate(${b.x - pad} ${b.y - pad}) scale(${1 / zoom})`}>
                    <rect y={-18} height={16} width={p.displayName.length * 6.5 + 10} rx={3} fill={p.color} />
                    <text x={5} y={-6} className="presence-tag">
                      {p.displayName}
                    </text>
                  </g>
                </g>
              );
            }),
          )}

          {/* Local selection */}
          {selected.map((el) => {
            const b = elementBounds(el, index);
            const pad = 4 / zoom;
            return (
              <rect
                key={`sel-${el.id}`}
                x={b.x - pad}
                y={b.y - pad}
                width={b.w + pad * 2}
                height={b.h + pad * 2}
                fill="none"
                stroke={me.color}
                strokeWidth={1.5 / zoom}
                strokeDasharray={`${4 / zoom} ${3 / zoom}`}
                pointerEvents="none"
              />
            );
          })}
          {canEdit && single?.kind === 'shape' && (
            <g>
              {(['nw', 'ne', 'sw', 'se'] as Handle[]).map((h) => {
                const s = 9 / zoom;
                const x = h.includes('w') ? single.x : single.x + single.w;
                const y = h.includes('n') ? single.y : single.y + single.h;
                return (
                  <rect
                    key={h}
                    data-handle={h}
                    className={`resize-handle handle-${h}`}
                    x={x - s / 2}
                    y={y - s / 2}
                    width={s}
                    height={s}
                    fill="#fff"
                    stroke={me.color}
                    strokeWidth={1.5 / zoom}
                    aria-label={`Resize ${h}`}
                  />
                );
              })}
            </g>
          )}
          {canEdit && single?.kind === 'connector' && (
            <g>
              {(['from', 'to'] as const).map((end) => {
                const g = connectorGeometry(single, index);
                const p = end === 'from' ? g.start : g.end;
                return (
                  <circle key={end} data-endpoint={end} className="endpoint-handle" cx={p.x} cy={p.y} r={6 / zoom} fill="#fff" stroke={me.color} strokeWidth={2 / zoom} />
                );
              })}
            </g>
          )}

          {guides.map((g, i) =>
            g.orientation === 'vertical' ? (
              <line key={i} x1={g.position} x2={g.position} y1={-1e5} y2={1e5} stroke="#ec4899" strokeWidth={1 / zoom} pointerEvents="none" />
            ) : (
              <line key={i} y1={g.position} y2={g.position} x1={-1e5} x2={1e5} stroke="#ec4899" strokeWidth={1 / zoom} pointerEvents="none" />
            ),
          )}

          {marquee && (
            <rect
              x={marquee.x}
              y={marquee.y}
              width={marquee.w}
              height={marquee.h}
              fill="rgba(99,102,241,0.08)"
              stroke="#6366f1"
              strokeWidth={1 / zoom}
              pointerEvents="none"
            />
          )}

          {showCursors &&
            presence
              .filter((p) => p.cursor)
              .map((p) => (
                <g
                  key={`cursor-${p.participantId}`}
                  transform={`translate(${p.cursor!.x} ${p.cursor!.y}) scale(${1 / zoom})`}
                  pointerEvents="none"
                  className="remote-cursor"
                >
                  <path d="M0 0 L0 16 L4.5 12 L8 19 L10.5 18 L7 11 L13 11 Z" fill={presenceColor.get(p.participantId)?.color} stroke="#fff" strokeWidth={1.2} />
                  <rect x={12} y={16} height={18} width={p.displayName.length * 7 + 12} rx={4} fill={p.color} />
                  <text x={18} y={29} className="presence-tag">
                    {p.displayName}
                  </text>
                </g>
              ))}
        </g>
      </svg>

      {editingId && (
        <TextEditor
          key={editingId}
          element={index.get(editingId) ?? null}
          index={index}
          viewport={viewport}
          onDone={(label) => {
            const el = index.get(editingId);
            onEditingChange(null);
            if (label !== null && el && el.kind !== 'stroke' && el.label !== label) commit([{ ...el, label }]);
            containerRef.current?.focus({ preventScroll: true });
          }}
        />
      )}
    </div>
  );
}

function TextEditor({
  element,
  index,
  viewport,
  onDone,
}: {
  element: CanvasElement | null;
  index: ReturnType<typeof indexElements>;
  viewport: Viewport;
  onDone(label: string | null): void;
}) {
  const [value, setValue] = useState(element && element.kind !== 'stroke' ? element.label : '');
  const ref = useRef<HTMLTextAreaElement>(null);
  const done = useRef(false);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  if (!element || element.kind === 'stroke') return null;

  let box: Rect;
  let className = 'canvas-text-editor';
  if (element.kind === 'shape') {
    const def = getComponent(element.componentType);
    box = shapeRect(element);
    if (def.shape === 'sticky') className += ' sticky';
    if (def.shape === 'text') className += ' text';
    if (def.shape === 'boundary') box = { ...box, h: 30 };
  } else {
    const mid = connectorGeometry(element, index).mid;
    box = { x: mid.x - 70, y: mid.y - 14, w: 140, h: 28 };
  }
  const tl = worldToScreen(viewport, { x: box.x, y: box.y });

  const finish = (label: string | null) => {
    if (done.current) return;
    done.current = true;
    onDone(label);
  };

  return (
    <textarea
      ref={ref}
      className={className}
      aria-label="Edit label"
      value={value}
      maxLength={2000}
      style={{
        left: tl.x,
        top: tl.y,
        width: box.w * viewport.zoom,
        height: box.h * viewport.zoom,
        fontSize: 13 * viewport.zoom,
      }}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => finish(value)}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === 'Escape') finish(null);
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          finish(value);
        }
      }}
    />
  );
}
