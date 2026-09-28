import type { ComponentCategory, ComponentType } from './types';

/** How a component is drawn on the canvas. */
export type ShapeStyle =
  | 'rect'
  | 'rounded'
  | 'ellipse'
  | 'cylinder'
  | 'queue'
  | 'text'
  | 'sticky'
  | 'boundary';

export interface ComponentDef {
  type: ComponentType;
  category: ComponentCategory;
  name: string;
  /** Name of a lucide-react icon, or null for plain shapes. */
  icon: string | null;
  shape: ShapeStyle;
  defaultLabel: string;
  width: number;
  height: number;
  minWidth: number;
  minHeight: number;
  /** Accent colour used for the icon and border; chosen for >= 3:1 contrast on white. */
  accent: string;
  fill: string;
}

const node = (
  type: ComponentType,
  category: ComponentCategory,
  name: string,
  icon: string | null,
  accent: string,
  fill: string,
  shape: ShapeStyle = 'rounded',
  size: [number, number] = [150, 72],
): ComponentDef => ({
  type,
  category,
  name,
  icon,
  shape,
  defaultLabel: name,
  width: size[0],
  height: size[1],
  minWidth: shape === 'text' ? 40 : 60,
  minHeight: shape === 'text' ? 24 : 40,
  accent,
  fill,
});

const SLATE = ['#475569', '#f8fafc'] as const;
const BLUE = ['#1d4ed8', '#eff6ff'] as const;
const GREEN = ['#15803d', '#f0fdf4'] as const;
const AMBER = ['#b45309', '#fffbeb'] as const;
const VIOLET = ['#6d28d9', '#f5f3ff'] as const;
const ROSE = ['#be123c', '#fff1f2'] as const;

export const COMPONENTS: ComponentDef[] = [
  // General
  node('service', 'General', 'Service', 'Cog', ...SLATE, 'rect'),
  node('rounded', 'General', 'Rounded box', null, ...SLATE, 'rounded'),
  node('rectangle', 'General', 'Rectangle', null, ...SLATE, 'rect', [140, 80]),
  node('ellipse', 'General', 'Ellipse', null, ...SLATE, 'ellipse', [140, 80]),
  node('text', 'General', 'Text', null, '#0f172a', 'transparent', 'text', [160, 36]),
  node('sticky', 'General', 'Sticky note', null, '#854d0e', '#fef08a', 'sticky', [160, 140]),
  node('boundary', 'General', 'Boundary', null, '#64748b', 'transparent', 'boundary', [360, 240]),
  node('icon', 'General', 'Generic icon', 'Shapes', ...SLATE, 'rounded', [110, 90]),
  // Data
  node('sql-db', 'Data', 'SQL database', 'Database', ...BLUE, 'cylinder', [130, 100]),
  node('nosql-db', 'Data', 'NoSQL database', 'Layers', ...BLUE, 'cylinder', [130, 100]),
  node('cache', 'Data', 'Cache', 'MemoryStick', ...ROSE, 'rounded'),
  node('object-storage', 'Data', 'Object storage', 'Archive', ...BLUE, 'rounded'),
  node('warehouse', 'Data', 'Data warehouse', 'Warehouse', ...BLUE, 'cylinder', [140, 100]),
  // Messaging
  node('queue', 'Messaging', 'Queue', 'ListOrdered', ...AMBER, 'queue', [170, 64]),
  node('stream', 'Messaging', 'Event stream', 'Waves', ...AMBER, 'queue', [170, 64]),
  node('pubsub', 'Messaging', 'Pub/Sub broker', 'Megaphone', ...AMBER, 'rounded'),
  // Network
  node('client', 'Network', 'Client', 'Laptop', ...GREEN, 'rounded', [130, 72]),
  node('browser', 'Network', 'Browser', 'Globe', ...GREEN, 'rounded', [130, 72]),
  node('mobile', 'Network', 'Mobile client', 'Smartphone', ...GREEN, 'rounded', [130, 72]),
  node('api-gateway', 'Network', 'API gateway', 'Router', ...GREEN, 'rect'),
  node('load-balancer', 'Network', 'Load balancer', 'Split', ...GREEN, 'rect'),
  node('cdn', 'Network', 'CDN', 'Cloud', ...GREEN, 'rounded'),
  node('external-api', 'Network', 'External API', 'Plug', ...GREEN, 'rounded'),
  // Compute
  node('server', 'Compute', 'Server', 'Server', ...SLATE, 'rect'),
  node('worker', 'Compute', 'Worker', 'Cpu', ...SLATE, 'rect'),
  node('function', 'Compute', 'Function', 'Zap', ...SLATE, 'rounded'),
  node('cluster', 'Compute', 'Container cluster', 'Boxes', ...SLATE, 'rect', [170, 80]),
  // AI
  node('llm', 'AI', 'LLM / model', 'Brain', ...VIOLET, 'rounded'),
  node('embedding', 'AI', 'Embedding model', 'Binary', ...VIOLET, 'rounded'),
  node('vector-db', 'AI', 'Vector database', 'Database', ...VIOLET, 'cylinder', [140, 100]),
  node('agent', 'AI', 'Agent / tool', 'Bot', ...VIOLET, 'rounded'),
];

export const CATEGORIES: ComponentCategory[] = ['General', 'Data', 'Messaging', 'Network', 'Compute', 'AI'];

const BY_TYPE = new Map(COMPONENTS.map((c) => [c.type, c]));

export function getComponent(type: ComponentType): ComponentDef {
  const def = BY_TYPE.get(type);
  if (!def) throw new Error(`Unknown component type: ${type}`);
  return def;
}

export function isComponentType(value: unknown): value is ComponentType {
  return typeof value === 'string' && BY_TYPE.has(value as ComponentType);
}

export const STICKY_COLORS = ['#fef08a', '#bbf7d0', '#bfdbfe', '#fbcfe8', '#fed7aa'];
export const INK_COLORS = ['#0f172a', '#dc2626', '#2563eb', '#16a34a', '#9333ea', '#ea580c'];
export const HIGHLIGHT_COLORS = ['#facc15', '#4ade80', '#60a5fa', '#f472b6'];
