/**
 * Canvas document model.
 *
 * The document is a last-writer-wins element map (a simple state-based CRDT):
 * every element carries a Lamport `version`, and deletions are kept as
 * tombstones so that out-of-order and duplicate operations converge.
 */

export const CANVAS_SCHEMA_VERSION = 1;

export interface Stamp {
  /** Lamport clock value. */
  clock: number;
  /** Actor (participant) id — tie-breaker for equal clocks. */
  actor: string;
}

export type Anchor = 'auto' | 'top' | 'right' | 'bottom' | 'left';

export interface Endpoint {
  /** Attached element, if any. Connectors follow the element when it moves. */
  elementId?: string;
  anchor?: Anchor;
  /** Free position (used when detached, and as a fallback). */
  x: number;
  y: number;
}

interface BaseElement {
  id: string;
  z: number;
  groupId?: string | null;
  version: Stamp;
  createdBy: string;
  createdAt: string;
  updatedBy: string;
}

export interface ShapeElement extends BaseElement {
  kind: 'shape';
  componentType: ComponentType;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  description?: string;
  fill?: string;
}

export type Routing = 'straight' | 'elbow' | 'curved';

export interface ConnectorElement extends BaseElement {
  kind: 'connector';
  from: Endpoint;
  to: Endpoint;
  routing: Routing;
  arrowStart: boolean;
  arrowEnd: boolean;
  label: string;
  dashed: boolean;
  color: string;
  width: 1 | 2 | 3;
}

export interface StrokeElement extends BaseElement {
  kind: 'stroke';
  tool: 'pen' | 'highlighter';
  /** Flat list of world coordinates: [x0, y0, x1, y1, ...]. */
  points: number[];
  color: string;
  width: number;
}

export type CanvasElement = ShapeElement | ConnectorElement | StrokeElement;

export interface Tombstone {
  id: string;
  deleted: true;
  version: Stamp;
}

export type ElementEntry = CanvasElement | Tombstone;

export interface CanvasDoc {
  schemaVersion: number;
  elements: Record<string, ElementEntry>;
}

export type Change =
  | { type: 'put'; element: CanvasElement }
  | { type: 'delete'; id: string; version: Stamp };

export interface CanvasOperation {
  /** Client-generated id; used to discard duplicates. */
  id: string;
  actorId: string;
  changes: Change[];
}

export type ComponentCategory = 'General' | 'Data' | 'Messaging' | 'Network' | 'Compute' | 'AI';

export type ComponentType =
  // General
  | 'service'
  | 'rounded'
  | 'rectangle'
  | 'ellipse'
  | 'text'
  | 'sticky'
  | 'boundary'
  | 'icon'
  // Data
  | 'sql-db'
  | 'nosql-db'
  | 'cache'
  | 'object-storage'
  | 'warehouse'
  // Messaging
  | 'queue'
  | 'stream'
  | 'pubsub'
  // Network
  | 'client'
  | 'browser'
  | 'mobile'
  | 'api-gateway'
  | 'load-balancer'
  | 'cdn'
  | 'external-api'
  // Compute
  | 'server'
  | 'worker'
  | 'function'
  | 'cluster'
  // AI
  | 'llm'
  | 'embedding'
  | 'vector-db'
  | 'agent';
