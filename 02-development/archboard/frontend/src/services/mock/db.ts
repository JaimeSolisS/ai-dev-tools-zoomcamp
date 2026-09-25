import type { CanvasDoc } from '../../canvas/types';
import type { CanvasSnapshotInfo, GuestLink, InterviewSession, Participant, User } from '../types';
import { readJson, writeJson, type KeyValueStorage } from './storage';

export interface StoredGuestLink extends GuestLink {
  tokenHash: string;
}

export interface StoredParticipant extends Participant {
  credentialHash: string | null;
}

export interface StoredCanvas {
  sessionId: string;
  doc: CanvasDoc;
  cursor: number;
  /** Recently applied operation ids, for duplicate detection. */
  recentOpIds: string[];
  updatedAt: string;
}

export interface StoredSnapshot extends CanvasSnapshotInfo {
  doc: CanvasDoc;
}

export interface AuditEvent {
  id: string;
  sessionId: string;
  actor: string;
  action: string;
  at: string;
  details?: Record<string, unknown>;
}

interface MagicLink {
  email: string;
  expiresAt: string;
}

const PREFIX = 'archboard:db:v1:';

/** A tiny key-value "table". Rows are re-read on every access so tabs see each other's writes. */
class Table<T> {
  constructor(
    private storage: KeyValueStorage,
    private key: string,
  ) {}
  all(): Record<string, T> {
    return readJson<Record<string, T>>(this.storage, PREFIX + this.key, {});
  }
  values(): T[] {
    return Object.values(this.all());
  }
  get(id: string): T | undefined {
    return this.all()[id];
  }
  put(id: string, row: T): T {
    const rows = this.all();
    rows[id] = row;
    writeJson(this.storage, PREFIX + this.key, rows);
    return row;
  }
  delete(id: string): void {
    const rows = this.all();
    delete rows[id];
    writeJson(this.storage, PREFIX + this.key, rows);
  }
}

export class MockDatabase {
  readonly users: Table<User>;
  readonly sessions: Table<InterviewSession>;
  readonly guestLinks: Table<StoredGuestLink>;
  readonly participants: Table<StoredParticipant>;
  readonly canvases: Table<StoredCanvas>;
  readonly snapshots: Table<StoredSnapshot>;
  readonly magicLinks: Table<MagicLink>;
  /** Hash of an interviewer auth token -> user id. */
  readonly authTokens: Table<string>;

  constructor(private storage: KeyValueStorage) {
    this.users = new Table(storage, 'users');
    this.sessions = new Table(storage, 'sessions');
    this.guestLinks = new Table(storage, 'guestLinks');
    this.participants = new Table(storage, 'participants');
    this.canvases = new Table(storage, 'canvases');
    this.snapshots = new Table(storage, 'snapshots');
    this.magicLinks = new Table(storage, 'magicLinks');
    this.authTokens = new Table(storage, 'authTokens');
  }

  audit(event: AuditEvent): void {
    const key = PREFIX + 'audit';
    const events = readJson<AuditEvent[]>(this.storage, key, []);
    events.push(event);
    writeJson(this.storage, key, events.slice(-1000));
  }

  auditLog(): AuditEvent[] {
    return readJson<AuditEvent[]>(this.storage, PREFIX + 'audit', []);
  }
}
