/**
 * Data contract between the frontend and the backend.
 *
 * Every shape the UI receives from or sends to a backend is defined here.
 * These types are the source for the future OpenAPI specification.
 */
import type { CanvasDoc, CanvasOperation } from '../canvas/types';

export type SessionState = 'draft' | 'live' | 'ended' | 'archived';
export type Role = 'owner' | 'interviewer' | 'candidate' | 'observer';
/** Roles that can be granted through a shareable link. */
export type GuestRole = Exclude<Role, 'owner'>;

export interface User {
  id: string;
  email: string;
  displayName: string;
  organizationId: string | null;
  createdAt: string;
}

export interface InterviewSession {
  id: string;
  ownerUserId: string;
  title: string;
  prompt: string;
  state: SessionState;
  candidateEditingEnabled: boolean;
  showCursors: boolean;
  durationMinutes: number | null;
  scheduledAt: string | null;
  startedAt: string | null;
  endedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SessionSummary extends InterviewSession {
  participantNames: string[];
  lastModifiedAt: string;
  /** Currently active (non-revoked, non-expired) link, without its token. */
  activeGuestLink: GuestLink | null;
}

export interface CreateSessionInput {
  title: string;
  prompt?: string;
  durationMinutes?: number | null;
  scheduledAt?: string | null;
  /** Copy the canvas of an existing session (template). */
  templateSessionId?: string | null;
}

export type UpdateSessionInput = Partial<
  Pick<InterviewSession, 'title' | 'prompt' | 'durationMinutes' | 'scheduledAt' | 'candidateEditingEnabled' | 'showCursors'>
>;

export interface GuestLink {
  id: string;
  sessionId: string;
  roleGranted: GuestRole;
  expiresAt: string | null;
  maxUses: number | null;
  uses: number;
  revokedAt: string | null;
  createdAt: string;
}

export interface CreateGuestLinkInput {
  roleGranted?: GuestRole;
  expiresAt?: string | null;
  maxUses?: number | null;
  /** Revoke all other active links of the same role (link rotation). */
  rotate?: boolean;
}

/** The bearer token is returned only once, at creation time. */
export interface CreatedGuestLink {
  link: GuestLink;
  token: string;
}

export interface Participant {
  id: string;
  sessionId: string;
  userId: string | null;
  displayName: string;
  role: Role;
  color: string;
  joinedAt: string;
  leftAt: string | null;
  removedAt: string | null;
  lastSeenAt: string | null;
}

/** Public information shown in the lobby before joining. */
export interface JoinInfo {
  sessionTitle: string;
  sessionState: SessionState;
  roleGranted: GuestRole;
}

export interface JoinResult {
  sessionId: string;
  participant: Participant;
}

export interface Permissions {
  canView: boolean;
  canEdit: boolean;
  canLockEditing: boolean;
  canShare: boolean;
  canRemoveParticipants: boolean;
  canStartOrEnd: boolean;
  canClearCanvas: boolean;
  canEditSettings: boolean;
}

/** Everything needed to render the interview room (GET /v1/sessions/{id}/canvas). */
export interface RoomAccess {
  session: InterviewSession;
  me: Participant;
  participants: Participant[];
  canvas: CanvasDoc;
  /** Sequence number of the last operation included in `canvas`. */
  cursor: number;
  permissions: Permissions;
}

export interface CanvasSnapshotInfo {
  id: string;
  sessionId: string;
  reason: 'final' | 'before-clear' | 'periodic' | 'before-restore';
  operationCursor: number;
  elementCount: number;
  createdAt: string;
}

export interface MagicLinkRequest {
  sent: true;
  /** Only returned by development backends so the flow can be completed without email. */
  devToken?: string;
}

// ---------------------------------------------------------------------------
// Real-time protocol
// ---------------------------------------------------------------------------

export const PROTOCOL_VERSION = 1;

export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'offline' | 'closed';

export interface PresencePoint {
  x: number;
  y: number;
}

export interface Presence {
  participantId: string;
  displayName: string;
  color: string;
  role: Role;
  cursor: PresencePoint | null;
  selection: string[];
  /** Client timestamp (ms) — used to expire stale presence. */
  ts: number;
}

export type ClientMessage =
  | { type: 'document_update'; op: CanvasOperation }
  | { type: 'presence_update'; presence: Presence }
  | { type: 'ping' };

export type ErrorCode =
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION'
  | 'LINK_INVALID'
  | 'LINK_REVOKED'
  | 'LINK_EXPIRED'
  | 'LINK_EXHAUSTED'
  | 'SESSION_ENDED'
  | 'SESSION_ARCHIVED'
  | 'SESSION_FULL'
  | 'EDIT_LOCKED'
  | 'PARTICIPANT_REMOVED'
  | 'CONFLICT';

export type ServerMessage =
  | { type: 'room_joined'; participantId: string; cursor: number }
  | { type: 'document_update'; op: CanvasOperation; cursor: number }
  | { type: 'document_ack'; opId: string; cursor: number }
  | { type: 'presence_update'; presence: Presence }
  | { type: 'presence_leave'; participantId: string }
  | { type: 'participants_changed' }
  | { type: 'session_updated'; session: InterviewSession }
  | { type: 'session_ended'; session: InterviewSession }
  | { type: 'participant_removed'; participantId: string }
  | { type: 'canvas_reset' }
  | { type: 'error'; code: ErrorCode; message: string; opId?: string }
  | { type: 'pong' };

export type Envelope<T> = T & { v: typeof PROTOCOL_VERSION; sessionId: string; id: string };
