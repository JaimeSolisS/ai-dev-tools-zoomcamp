/**
 * The single integration point between the UI and a backend.
 *
 * Components never call fetch/WebSocket directly: they receive a
 * `BackendService` from `ServiceProvider` and call it. Swapping the mock for a
 * real HTTP/WebSocket client only requires another implementation of this
 * interface. The comments name the HTTP endpoint each method maps to (spec §12).
 */
import type { CanvasOperation } from '../canvas/types';
import type {
  CanvasSnapshotInfo,
  ClientMessage,
  ConnectionStatus,
  CreatedGuestLink,
  CreateGuestLinkInput,
  CreateSessionInput,
  GuestLink,
  InterviewSession,
  JoinInfo,
  JoinResult,
  MagicLinkRequest,
  Participant,
  RoomAccess,
  ServerMessage,
  SessionSummary,
  UpdateSessionInput,
  User,
} from './types';

export interface AuthService {
  /** GET /v1/auth/me — null when not signed in. */
  getCurrentUser(): Promise<User | null>;
  /** POST /v1/auth/magic-link */
  requestMagicLink(email: string): Promise<MagicLinkRequest>;
  /** POST /v1/auth/magic-link/verify */
  verifyMagicLink(token: string): Promise<User>;
  /** POST /v1/auth/logout */
  signOut(): Promise<void>;
}

export interface SessionService {
  /** GET /v1/sessions */
  list(): Promise<SessionSummary[]>;
  /** POST /v1/sessions */
  create(input: CreateSessionInput): Promise<InterviewSession>;
  /** GET /v1/sessions/{id} */
  get(id: string): Promise<InterviewSession>;
  /** PATCH /v1/sessions/{id} */
  update(id: string, patch: UpdateSessionInput): Promise<InterviewSession>;
  /** POST /v1/sessions/{id}/start */
  start(id: string): Promise<InterviewSession>;
  /** POST /v1/sessions/{id}/end — saves a final snapshot. */
  end(id: string): Promise<InterviewSession>;
  /** POST /v1/sessions/{id}/reopen */
  reopen(id: string): Promise<InterviewSession>;
  /** POST /v1/sessions/{id}/archive */
  archive(id: string): Promise<InterviewSession>;
  /** POST /v1/sessions/{id}/duplicate — copies title, prompt and canvas into a new draft. */
  duplicate(id: string): Promise<InterviewSession>;

  /** GET /v1/sessions/{id}/participants */
  listParticipants(id: string): Promise<Participant[]>;
  /** DELETE /v1/sessions/{id}/participants/{participantId} */
  removeParticipant(id: string, participantId: string): Promise<void>;

  /** GET /v1/sessions/{id}/guest-links */
  listGuestLinks(id: string): Promise<GuestLink[]>;
  /** POST /v1/sessions/{id}/guest-links */
  createGuestLink(id: string, input?: CreateGuestLinkInput): Promise<CreatedGuestLink>;
  /** DELETE /v1/sessions/{id}/guest-links/{linkId} */
  revokeGuestLink(id: string, linkId: string): Promise<void>;

  /** POST /v1/sessions/{id}/canvas/clear — keeps a recoverable snapshot. */
  clearCanvas(id: string): Promise<void>;
  /** GET /v1/sessions/{id}/canvas/snapshots */
  listSnapshots(id: string): Promise<CanvasSnapshotInfo[]>;
  /** POST /v1/sessions/{id}/canvas/snapshots/{snapshotId}/restore */
  restoreSnapshot(id: string, snapshotId: string): Promise<void>;
}

export interface JoinService {
  /** GET /v1/join/{token} — lobby information; throws for invalid links. */
  getInfo(token: string): Promise<JoinInfo>;
  /** POST /v1/join/{token} — creates the guest participation. */
  join(token: string, displayName: string): Promise<JoinResult>;
}

export interface CanvasService {
  /** GET /v1/sessions/{id}/canvas — snapshot, identity and permissions for the room. */
  openRoom(sessionId: string): Promise<RoomAccess>;
}

export interface RealtimeConnection {
  readonly status: ConnectionStatus;
  send(message: ClientMessage): void;
  onMessage(listener: (message: ServerMessage) => void): () => void;
  onStatus(listener: (status: ConnectionStatus) => void): () => void;
  close(): void;
}

export interface RealtimeService {
  /** WS /v1/sessions/{id}/ws */
  connect(sessionId: string): RealtimeConnection;
}

export interface BackendService {
  readonly kind: 'mock' | 'http';
  auth: AuthService;
  sessions: SessionService;
  join: JoinService;
  canvas: CanvasService;
  realtime: RealtimeService;
}

export type { CanvasOperation };
