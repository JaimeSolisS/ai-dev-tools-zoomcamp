import { getComponent } from '../../canvas/catalog';
import { newId } from '../../canvas/model';
import type { CanvasElement, ComponentType, ConnectorElement, ShapeElement } from '../../canvas/types';
import type { InterviewSession, User } from '../types';
import type { MockDatabase } from './db';

/** Give a brand-new interviewer one finished example so the dashboard is not empty. */
export function seedExampleSession(db: MockDatabase, owner: User, now: string): InterviewSession {
  const startedAt = new Date(new Date(now).getTime() - 42 * 60_000).toISOString();
  const session: InterviewSession = {
    id: newId('s'),
    ownerUserId: owner.id,
    title: 'Example: Design a URL shortener',
    prompt:
      'Design a service like bit.ly.\n\n• 100M new URLs per month, 10:1 read/write ratio\n• Short links should redirect in < 50 ms (p95)\n• Collect click analytics\n\nStart with the API, then the data model, then scale it.',
    state: 'ended',
    candidateEditingEnabled: true,
    showCursors: true,
    durationMinutes: 45,
    scheduledAt: null,
    startedAt,
    endedAt: now,
    createdAt: startedAt,
    updatedAt: now,
  };
  db.sessions.put(session.id, session);

  const actor = 'seed';
  const version = { clock: 1, actor };
  const base = { version, createdBy: actor, createdAt: now, updatedBy: actor, groupId: null };
  let z = 0;
  const shape = (type: ComponentType, x: number, y: number, label?: string): ShapeElement => {
    const def = getComponent(type);
    return { ...base, id: newId('el'), z: ++z, kind: 'shape', componentType: type, x, y, w: def.width, h: def.height, label: label ?? def.defaultLabel };
  };
  const link = (a: ShapeElement, b: ShapeElement, label = ''): ConnectorElement => ({
    ...base,
    id: newId('el'),
    z: ++z,
    kind: 'connector',
    from: { elementId: a.id, anchor: 'auto', x: a.x, y: a.y },
    to: { elementId: b.id, anchor: 'auto', x: b.x, y: b.y },
    routing: 'straight',
    arrowStart: false,
    arrowEnd: true,
    label,
    dashed: false,
    color: '#334155',
    width: 2,
  });

  const boundary = shape('boundary', 250, -30, 'Region us-east-1');
  boundary.w = 640;
  boundary.h = 420;
  boundary.z = -10;
  const client = shape('browser', 0, 120, 'Browser');
  const lb = shape('load-balancer', 290, 120);
  const api = shape('server', 520, 120, 'API servers');
  const cache = shape('cache', 740, 20, 'Redis cache');
  const db1 = shape('sql-db', 750, 200, 'URL store');
  const queue = shape('queue', 480, 290, 'Click events');
  const worker = shape('worker', 280, 290, 'Analytics worker');
  const note = shape('sticky', 0, 300, 'Base62 IDs from a counter service; 7 chars ≈ 3.5T URLs');

  const elements: CanvasElement[] = [
    boundary, client, lb, api, cache, db1, queue, worker, note,
    link(client, lb, 'HTTPS'),
    link(lb, api),
    link(api, cache, 'read'),
    link(api, db1, 'read/write'),
    { ...link(api, queue, 'events'), dashed: true },
    link(queue, worker),
  ];
  db.canvases.put(session.id, {
    sessionId: session.id,
    doc: { schemaVersion: 1, elements: Object.fromEntries(elements.map((e) => [e.id, e])) },
    cursor: 0,
    recentOpIds: [],
    updatedAt: now,
  });
  return session;
}
