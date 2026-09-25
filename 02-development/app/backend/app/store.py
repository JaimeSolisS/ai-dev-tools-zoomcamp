"""In-memory store and domain rules.

All state lives in plain dicts on a `Store` instance (one per app). Methods
enforce the same rules as the frontend's mock backend
(`frontend/src/services/mock/mockBackend.ts`) and raise `ApiError` with the
codes documented in openapi.yaml.

Everything runs on the ASGI event loop, so there is no locking. Room events
(for WebSocket clients) are emitted through an `EventSink`; the store knows
nothing about sockets.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Protocol
from uuid import uuid4

from pydantic import Field

from . import canvas
from .config import Settings
from .errors import ApiError
from .models import (
    CanvasDoc,
    CanvasSnapshotInfo,
    CreateGuestLinkInput,
    CreateSessionInput,
    GuestLink,
    InterviewSession,
    JoinInfo,
    Participant,
    Role,
    RoomAccess,
    SessionSummary,
    SnapshotReason,
    UpdateSessionInput,
    User,
)
from .permissions import compute_permissions
from .security import hash_password, hash_token, new_token, verify_password

PARTICIPANT_COLORS = [
    "#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed",
    "#0891b2", "#dc2626", "#4f46e5", "#65a30d", "#c026d3",
]  # fmt: skip
RECENT_OP_IDS = 500
SNAPSHOT_EVERY_OPS = 200
LAST_SEEN_WRITE_SECONDS = 10


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def utcnow() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ records --
# Internal records extend the public models with secrets that are never serialized.


class UserRecord(User):
    password_hash: str | None = Field(default=None, exclude=True)


class GuestLinkRecord(GuestLink):
    token_hash: str = Field(exclude=True)


class ParticipantRecord(Participant):
    credential_hash: str | None = Field(default=None, exclude=True)


class SnapshotRecord(CanvasSnapshotInfo):
    elements: dict[str, dict[str, Any]] = Field(exclude=True)


@dataclass
class CanvasRecord:
    session_id: str
    elements: dict[str, dict[str, Any]]
    cursor: int
    updated_at: datetime
    recent_op_ids: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_OP_IDS))


@dataclass
class MagicLink:
    email: str
    expires_at: datetime


@dataclass
class AuditEvent:
    id: str
    session_id: str
    actor: str
    action: str
    at: datetime
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationResult:
    """Outcome of a client canvas operation, for the realtime layer."""

    ok: bool
    cursor: int = 0
    duplicate: bool = False
    code: str | None = None
    message: str | None = None


class EventSink(Protocol):
    def publish(self, session_id: str, payload: dict[str, Any], exclude: str | None = None) -> None: ...
    def disconnect_participant(self, session_id: str, participant_id: str) -> None: ...


class NullSink:
    def publish(self, session_id: str, payload: dict[str, Any], exclude: str | None = None) -> None:
        pass

    def disconnect_participant(self, session_id: str, participant_id: str) -> None:
        pass


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)


class Store:
    def __init__(
        self,
        settings: Settings | None = None,
        events: EventSink | None = None,
        clock: Callable[[], datetime] = utcnow,
    ):
        self.settings = settings or Settings()
        self.events: EventSink = events or NullSink()
        self.now = clock
        self.users: dict[str, UserRecord] = {}
        self.access_tokens: dict[str, str] = {}  # token hash -> user id
        self.magic_links: dict[str, MagicLink] = {}  # token hash -> link
        self.sessions: dict[str, InterviewSession] = {}
        self.guest_links: dict[str, GuestLinkRecord] = {}
        self.participants: dict[str, ParticipantRecord] = {}
        self.canvases: dict[str, CanvasRecord] = {}
        self.snapshots: dict[str, SnapshotRecord] = {}
        self.audit_log: list[AuditEvent] = []
        # Hook for new users (the seed module installs "create an example session").
        self.on_user_created: Callable[["Store", UserRecord], None] | None = None

    # ------------------------------------------------------------- helpers --

    def audit(self, session_id: str, actor: str, action: str, **details: Any) -> None:
        self.audit_log.append(AuditEvent(new_id("audit"), session_id, actor, action, self.now(), details))

    def publish(self, session_id: str, payload: dict[str, Any], exclude: str | None = None) -> None:
        self.events.publish(session_id, payload, exclude)

    def _touch(self, session: InterviewSession, **changes: Any) -> InterviewSession:
        updated = session.model_copy(update={**changes, "updated_at": self.now()})
        self.sessions[updated.id] = updated
        return updated

    # --------------------------------------------------------------- users --

    def create_user(self, email: str, display_name: str | None = None, password: str | None = None) -> UserRecord:
        email = email.strip().lower()
        if self.find_user_by_email(email):
            raise ApiError("CONFLICT", "A user with this email already exists.")
        local = email.split("@")[0]
        user = UserRecord(
            id=new_id("u"),
            email=email,
            display_name=display_name or local[:1].upper() + local[1:],
            organization_id=None,
            created_at=self.now(),
            password_hash=hash_password(password) if password else None,
        )
        self.users[user.id] = user
        if self.on_user_created:
            self.on_user_created(self, user)
        return user

    def find_user_by_email(self, email: str) -> UserRecord | None:
        email = email.strip().lower()
        return next((u for u in self.users.values() if u.email == email), None)

    def issue_access_token(self, user: User) -> str:
        token = new_token()
        self.access_tokens[hash_token(token)] = user.id
        return token

    def user_for_access_token(self, token: str) -> UserRecord | None:
        user_id = self.access_tokens.get(hash_token(token))
        return self.users.get(user_id) if user_id else None

    def revoke_access_token(self, token: str) -> None:
        self.access_tokens.pop(hash_token(token), None)

    def request_magic_link(self, email: str) -> str:
        token = new_token()
        expires = self.now() + timedelta(minutes=self.settings.magic_link_ttl_minutes)
        self.magic_links[hash_token(token)] = MagicLink(email=email.strip().lower(), expires_at=expires)
        return token

    def verify_magic_link(self, token: str) -> UserRecord:
        link = self.magic_links.pop(hash_token(token), None)
        if link is None or link.expires_at <= self.now():
            raise ApiError("LINK_INVALID", "This sign-in link is invalid or has expired.")
        return self.find_user_by_email(link.email) or self.create_user(link.email)

    def login(self, email: str, password: str) -> UserRecord:
        user = self.find_user_by_email(email)
        # Same error for unknown email and wrong password.
        if user is None or not user.password_hash or not verify_password(password, user.password_hash):
            raise ApiError("UNAUTHENTICATED", "Invalid email or password.")
        return user

    # ----------------------------------------------------------- principals --

    def get_session(self, session_id: str) -> InterviewSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise ApiError("NOT_FOUND", "Interview not found.")
        return session

    def require_owner(self, user: User, session_id: str) -> InterviewSession:
        """Owner-only access; everyone else gets NOT_FOUND so ids cannot be probed."""
        session = self.get_session(session_id)
        if session.owner_user_id != user.id:
            raise ApiError("NOT_FOUND", "Interview not found.")
        return session

    def resolve_principal(self, session_id: str, user: User | None, guest_credential: str | None) -> ParticipantRecord:
        """Who is calling for this session: a guest credential (preferred) or the signed-in user."""
        session = self.get_session(session_id)
        if guest_credential:
            credential_hash = hash_token(guest_credential)
            participant = next(
                (
                    p
                    for p in self.participants.values()
                    if p.session_id == session_id and p.credential_hash == credential_hash
                ),
                None,
            )
            if participant is not None:
                if participant.removed_at:
                    raise ApiError("PARTICIPANT_REMOVED", "You were removed from this interview.")
                return participant
            # A credential for another session is ignored here, not an error.
        if user is None:
            raise ApiError("UNAUTHENTICATED", "Join this interview through its invitation link.")
        mine = next(
            (
                p
                for p in self.participants.values()
                if p.session_id == session_id and p.user_id == user.id and p.credential_hash is None
            ),
            None,
        )
        if session.owner_user_id == user.id:
            return mine or self.add_participant(session_id, user.id, user.display_name, "owner", None)
        # Interviewers/observers who joined through a link while signed in.
        linked = mine or next(
            (p for p in self.participants.values() if p.session_id == session_id and p.user_id == user.id),
            None,
        )
        if linked is not None and not linked.removed_at:
            return linked
        raise ApiError("NOT_FOUND", "Interview not found.")

    # ------------------------------------------------------------- sessions --

    def list_sessions(self, user: User) -> list[SessionSummary]:
        invited = {p.session_id for p in self.participants.values() if p.user_id == user.id and not p.removed_at}
        summaries = [
            self.summarize(s) for s in self.sessions.values() if s.owner_user_id == user.id or s.id in invited
        ]
        return sorted(summaries, key=lambda s: s.last_modified_at, reverse=True)

    def summarize(self, session: InterviewSession) -> SessionSummary:
        participants = [p for p in self.participants.values() if p.session_id == session.id and not p.removed_at]
        record = self.canvases.get(session.id)
        active = sorted(
            (
                link
                for link in self.guest_links.values()
                if link.session_id == session.id and link.role_granted == "candidate" and self._link_active(link)
            ),
            key=lambda link: link.created_at,
            reverse=True,
        )
        last_modified = max(session.updated_at, record.updated_at) if record else session.updated_at
        return SessionSummary(
            **session.model_dump(),
            participant_names=[p.display_name for p in participants if p.role != "owner"],
            last_modified_at=last_modified,
            active_guest_link=GuestLink(**active[0].model_dump()) if active else None,
        )

    def create_session(self, user: User, data: CreateSessionInput) -> InterviewSession:
        if data.template_session_id:
            self.require_owner(user, data.template_session_id)
        session = self.insert_session(
            user,
            title=data.title,
            prompt=data.prompt,
            duration_minutes=data.duration_minutes,
            scheduled_at=data.scheduled_at,
        )
        if data.template_session_id:
            self._copy_canvas(data.template_session_id, session.id)
        else:
            self.ensure_canvas(session.id)
        self.audit(session.id, user.id, "session.created")
        return session

    def insert_session(self, owner: User, **fields: Any) -> InterviewSession:
        now = self.now()
        session = InterviewSession(
            id=new_id("s"),
            owner_user_id=owner.id,
            title=fields["title"],
            prompt=fields.get("prompt", ""),
            state=fields.get("state", "draft"),
            candidate_editing_enabled=True,
            show_cursors=True,
            duration_minutes=fields.get("duration_minutes"),
            scheduled_at=fields.get("scheduled_at"),
            started_at=fields.get("started_at"),
            ended_at=fields.get("ended_at"),
            created_at=fields.get("created_at", now),
            updated_at=now,
        )
        self.sessions[session.id] = session
        return session

    def update_session(
        self, principal: ParticipantRecord, session_id: str, patch: UpdateSessionInput
    ) -> InterviewSession:
        session = self.get_session(session_id)
        perms = compute_permissions(principal.role, session.state, session.candidate_editing_enabled)
        fields = patch.model_fields_set
        settings_fields = {"title", "prompt", "duration_minutes", "scheduled_at", "show_cursors"}
        if fields & settings_fields and not perms.can_edit_settings:
            raise ApiError("FORBIDDEN", "Only the owner can change interview settings.")
        if "candidate_editing_enabled" in fields and not perms.can_lock_editing:
            raise ApiError("FORBIDDEN", "You cannot change editing permissions.")
        updated = self._touch(session, **{name: getattr(patch, name) for name in fields})
        if "candidate_editing_enabled" in fields:
            self.audit(
                session_id,
                principal.id,
                "permissions.changed",
                candidate_editing_enabled=updated.candidate_editing_enabled,
            )
        self.publish(session_id, {"type": "session_updated", "session": _dump(updated)})
        return updated

    def start_session(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        if session.state != "draft":
            raise ApiError("CONFLICT", "Only draft interviews can be started.")
        updated = self._touch(session, state="live", started_at=self.now())
        self.audit(session_id, user.id, "session.started")
        self.publish(session_id, {"type": "session_updated", "session": _dump(updated)})
        return updated

    def end_session(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        if session.state not in ("draft", "live"):
            raise ApiError("CONFLICT", "This interview is not running.")
        self.save_snapshot(session_id, "final")
        updated = self._touch(session, state="ended", ended_at=self.now())
        self.audit(session_id, user.id, "session.ended")
        self.publish(session_id, {"type": "session_ended", "session": _dump(updated)})
        return updated

    def reopen_session(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        if session.state != "ended":
            raise ApiError("CONFLICT", "Only ended interviews can be reopened.")
        updated = self._touch(session, state="live", ended_at=None)
        self.audit(session_id, user.id, "session.reopened")
        self.publish(session_id, {"type": "session_updated", "session": _dump(updated)})
        return updated

    def archive_session(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        was_live = session.state == "live"
        if was_live:
            self.save_snapshot(session_id, "final")
        updated = self._touch(
            session,
            state="archived",
            ended_at=session.ended_at or (self.now() if was_live else None),
        )
        self.audit(session_id, user.id, "session.archived")
        self.publish(session_id, {"type": "session_ended", "session": _dump(updated)})
        return updated

    def duplicate_session(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        copy = self.insert_session(
            user,
            title=f"{session.title} (copy)"[:120],
            prompt=session.prompt,
            duration_minutes=session.duration_minutes,
        )
        self._copy_canvas(session_id, copy.id)
        self.audit(copy.id, user.id, "session.created", duplicated_from=session_id)
        return copy

    # --------------------------------------------------------- participants --

    def add_participant(
        self, session_id: str, user_id: str | None, display_name: str, role: Role, credential_hash: str | None
    ) -> ParticipantRecord:
        used = sum(1 for p in self.participants.values() if p.session_id == session_id)
        now = self.now()
        participant = ParticipantRecord(
            id=new_id("p"),
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            role=role,
            color=PARTICIPANT_COLORS[0] if role == "owner" else PARTICIPANT_COLORS[used % len(PARTICIPANT_COLORS)],
            joined_at=now,
            left_at=None,
            removed_at=None,
            last_seen_at=now,
            credential_hash=credential_hash,
        )
        self.participants[participant.id] = participant
        return participant

    def list_participants(self, session_id: str) -> list[ParticipantRecord]:
        return sorted(
            (p for p in self.participants.values() if p.session_id == session_id and not p.removed_at),
            key=lambda p: p.joined_at,
        )

    def remove_participant(self, user: User, session_id: str, participant_id: str) -> None:
        self.require_owner(user, session_id)
        participant = self.participants.get(participant_id)
        if participant is None or participant.session_id != session_id:
            raise ApiError("NOT_FOUND", "Participant not found.")
        if participant.role == "owner":
            raise ApiError("VALIDATION", "The owner cannot be removed.")
        now = self.now()
        self.participants[participant_id] = participant.model_copy(update={"removed_at": now, "left_at": now})
        self.audit(session_id, user.id, "participant.removed", participant_id=participant_id)
        self.publish(session_id, {"type": "participant_removed", "participantId": participant_id})
        self.publish(session_id, {"type": "participants_changed"})
        self.events.disconnect_participant(session_id, participant_id)

    def mark_seen(self, participant_id: str, *, left: bool = False) -> None:
        participant = self.participants.get(participant_id)
        if participant is None:
            return
        now = self.now()
        if not left and participant.last_seen_at and (now - participant.last_seen_at).total_seconds() < LAST_SEEN_WRITE_SECONDS:
            return
        self.participants[participant_id] = participant.model_copy(
            update={"last_seen_at": now, "left_at": now if left else None}
        )

    def _active_participant_count(self, session_id: str) -> int:
        cutoff = self.now() - timedelta(seconds=self.settings.active_window_seconds)
        return sum(
            1
            for p in self.participants.values()
            if p.session_id == session_id
            and not p.removed_at
            and not p.left_at
            and p.last_seen_at is not None
            and p.last_seen_at >= cutoff
        )

    # ---------------------------------------------------------- guest links --

    def _link_active(self, link: GuestLinkRecord) -> bool:
        if link.revoked_at:
            return False
        if link.expires_at and link.expires_at <= self.now():
            return False
        return not (link.max_uses is not None and link.uses >= link.max_uses)

    def list_links(self, user: User, session_id: str) -> list[GuestLinkRecord]:
        self.require_owner(user, session_id)
        links = [link for link in self.guest_links.values() if link.session_id == session_id]
        return sorted(links, key=lambda link: link.created_at, reverse=True)

    def create_link(
        self, user: User, session_id: str, data: CreateGuestLinkInput, token: str | None = None
    ) -> tuple[GuestLinkRecord, str]:
        session = self.require_owner(user, session_id)
        if session.state in ("ended", "archived"):
            raise ApiError("SESSION_ENDED", "Reopen the interview before sharing it.")
        if data.rotate:
            for link in list(self.guest_links.values()):
                if link.session_id == session_id and link.role_granted == data.role_granted and not link.revoked_at:
                    self.guest_links[link.id] = link.model_copy(update={"revoked_at": self.now()})
        token = token or new_token()
        link = GuestLinkRecord(
            id=new_id("gl"),
            session_id=session_id,
            role_granted=data.role_granted,
            expires_at=data.expires_at,
            max_uses=data.max_uses,
            uses=0,
            revoked_at=None,
            created_at=self.now(),
            token_hash=hash_token(token),
        )
        self.guest_links[link.id] = link
        self.audit(session_id, user.id, "link.rotated" if data.rotate else "link.created", link_id=link.id)
        return link, token

    def revoke_link(self, user: User, session_id: str, link_id: str) -> None:
        self.require_owner(user, session_id)
        link = self.guest_links.get(link_id)
        if link is None or link.session_id != session_id:
            raise ApiError("NOT_FOUND", "Link not found.")
        if not link.revoked_at:
            self.guest_links[link_id] = link.model_copy(update={"revoked_at": self.now()})
        self.audit(session_id, user.id, "link.revoked", link_id=link_id)

    # ----------------------------------------------------------------- join --

    def _find_link(self, token: str) -> tuple[GuestLinkRecord, InterviewSession]:
        token_hash = hash_token(token)
        link = next((link for link in self.guest_links.values() if link.token_hash == token_hash), None)
        session = self.sessions.get(link.session_id) if link else None
        if link is None or session is None:
            raise ApiError("LINK_INVALID", "This invitation link is not valid.")
        return link, session

    def _assert_joinable(self, link: GuestLinkRecord, session: InterviewSession, *, returning: bool) -> None:
        if session.state == "archived":
            raise ApiError("SESSION_ARCHIVED", "This interview has been archived.")
        if session.state == "ended":
            raise ApiError("SESSION_ENDED", "This interview has already ended.")
        if link.revoked_at:
            raise ApiError("LINK_REVOKED", "This invitation link has been revoked. Ask your interviewer for a new one.")
        if link.expires_at and link.expires_at <= self.now():
            raise ApiError("LINK_EXPIRED", "This invitation link has expired.")
        if not returning and link.max_uses is not None and link.uses >= link.max_uses:
            raise ApiError("LINK_EXHAUSTED", "This invitation link has already been used.")

    def join_info(self, token: str) -> JoinInfo:
        link, session = self._find_link(token)
        self._assert_joinable(link, session, returning=False)
        return JoinInfo(session_title=session.title, session_state=session.state, role_granted=link.role_granted)

    def join(
        self, token: str, display_name: str, user: User | None, guest_credential: str | None
    ) -> tuple[ParticipantRecord, str]:
        """Returns the participant and the guest credential to use for this session."""
        link, session = self._find_link(token)

        # Reconnect with an existing credential for this session.
        if guest_credential:
            credential_hash = hash_token(guest_credential)
            existing = next(
                (
                    p
                    for p in self.participants.values()
                    if p.session_id == session.id and p.credential_hash == credential_hash
                ),
                None,
            )
            if existing is not None:
                if existing.removed_at:
                    raise ApiError("PARTICIPANT_REMOVED", "You were removed from this interview.")
                self._assert_joinable(link, session, returning=True)
                updated = existing.model_copy(
                    update={"display_name": display_name, "left_at": None, "last_seen_at": self.now()}
                )
                self.participants[existing.id] = updated
                self.publish(session.id, {"type": "participants_changed"})
                return updated, guest_credential

        self._assert_joinable(link, session, returning=False)
        if self._active_participant_count(session.id) >= self.settings.max_participants:
            raise ApiError(
                "SESSION_FULL", f"This interview already has {self.settings.max_participants} participants."
            )
        credential = new_token()
        linked_user = user if link.role_granted in ("interviewer", "observer") else None
        participant = self.add_participant(
            session.id,
            linked_user.id if linked_user else None,
            display_name,
            link.role_granted,
            hash_token(credential),
        )
        self.guest_links[link.id] = link.model_copy(update={"uses": link.uses + 1})
        self.audit(session.id, participant.id, "participant.joined", role=participant.role)
        self.publish(session.id, {"type": "participants_changed"})
        return participant, credential

    # --------------------------------------------------------------- canvas --

    def ensure_canvas(self, session_id: str) -> CanvasRecord:
        record = self.canvases.get(session_id)
        if record is None:
            record = CanvasRecord(session_id=session_id, elements={}, cursor=0, updated_at=self.now())
            self.canvases[session_id] = record
        return record

    def _copy_canvas(self, from_session_id: str, to_session_id: str) -> None:
        source = self.canvases.get(from_session_id)
        elements = {k: dict(v) for k, v in source.elements.items()} if source else {}
        self.canvases[to_session_id] = CanvasRecord(
            session_id=to_session_id, elements=elements, cursor=0, updated_at=self.now()
        )

    def open_room(self, principal: ParticipantRecord) -> RoomAccess:
        session = self.get_session(principal.session_id)
        perms = compute_permissions(principal.role, session.state, session.candidate_editing_enabled)
        if not perms.can_view:
            if session.state == "ended":
                raise ApiError("SESSION_ENDED", "This interview has ended.")
            if session.state == "archived":
                raise ApiError("SESSION_ARCHIVED", "This interview has been archived.")
            raise ApiError("FORBIDDEN", "You do not have access to this interview.")
        record = self.ensure_canvas(session.id)
        return RoomAccess(
            session=session,
            me=Participant(**principal.model_dump()),
            participants=[Participant(**p.model_dump()) for p in self.list_participants(session.id)],
            canvas=CanvasDoc(elements=record.elements),
            cursor=record.cursor,
            permissions=perms,
        )

    def save_snapshot(self, session_id: str, reason: SnapshotReason) -> SnapshotRecord:
        record = self.ensure_canvas(session_id)
        snapshot = SnapshotRecord(
            id=new_id("snap"),
            session_id=session_id,
            reason=reason,
            operation_cursor=record.cursor,
            element_count=canvas.live_count(record.elements),
            created_at=self.now(),
            elements=dict(record.elements),
        )
        self.snapshots[snapshot.id] = snapshot
        return snapshot

    def _replace_canvas(self, session_id: str, elements: dict[str, dict[str, Any]]) -> None:
        record = self.ensure_canvas(session_id)
        record.elements = dict(elements)
        record.cursor += 1
        record.recent_op_ids.clear()
        record.updated_at = self.now()

    def _require_open_owner(self, user: User, session_id: str) -> InterviewSession:
        session = self.require_owner(user, session_id)
        if not compute_permissions("owner", session.state, session.candidate_editing_enabled).can_clear_canvas:
            raise ApiError("SESSION_ENDED", "This interview has ended.")
        return session

    def clear_canvas(self, user: User, session_id: str) -> None:
        self._require_open_owner(user, session_id)
        self.save_snapshot(session_id, "before-clear")
        self._replace_canvas(session_id, {})
        self.audit(session_id, user.id, "canvas.cleared")
        self.publish(session_id, {"type": "canvas_reset"})

    def list_snapshots(self, user: User, session_id: str) -> list[SnapshotRecord]:
        self.require_owner(user, session_id)
        snaps = [s for s in self.snapshots.values() if s.session_id == session_id]
        return sorted(snaps, key=lambda s: s.created_at, reverse=True)

    def restore_snapshot(self, user: User, session_id: str, snapshot_id: str) -> None:
        self._require_open_owner(user, session_id)
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None or snapshot.session_id != session_id:
            raise ApiError("NOT_FOUND", "Snapshot not found.")
        self.save_snapshot(session_id, "before-restore")
        self._replace_canvas(session_id, snapshot.elements)
        self.audit(session_id, user.id, "canvas.restored", snapshot_id=snapshot_id)
        self.publish(session_id, {"type": "canvas_reset"})

    def apply_client_operation(
        self, session_id: str, participant_id: str, raw_op: Any, connection_id: str | None = None
    ) -> OperationResult:
        """Authorize, validate, persist and fan out one operation from a WebSocket client."""
        participant = self.participants.get(participant_id)
        if participant is None or participant.session_id != session_id:
            return OperationResult(False, code="FORBIDDEN", message="Unknown participant.")
        if participant.removed_at:
            return OperationResult(False, code="PARTICIPANT_REMOVED", message="You were removed from this interview.")
        session = self.get_session(session_id)
        perms = compute_permissions(participant.role, session.state, session.candidate_editing_enabled)
        if not perms.can_edit:
            if session.state in ("ended", "archived"):
                return OperationResult(False, code="SESSION_ENDED", message="The interview has ended; the canvas is read-only.")
            if participant.role == "candidate" and session.state == "live":
                return OperationResult(False, code="EDIT_LOCKED", message="The interviewer has locked editing.")
            return OperationResult(False, code="FORBIDDEN", message="You cannot edit this canvas.")
        try:
            op = canvas.parse_operation(raw_op)
        except canvas.InvalidOperation as exc:
            return OperationResult(False, code="VALIDATION", message=str(exc))
        if op.actor_id != participant.id:
            return OperationResult(False, code="FORBIDDEN", message="Operation actor does not match the connection.")

        record = self.ensure_canvas(session_id)
        if op.id in record.recent_op_ids:
            return OperationResult(True, cursor=record.cursor, duplicate=True)
        elements = canvas.apply_operation(record.elements, op)
        if len(elements) > canvas.MAX_ELEMENTS:
            return OperationResult(False, code="VALIDATION", message="The canvas has too many elements.")
        record.elements = elements
        record.cursor += 1
        record.recent_op_ids.append(op.id)
        record.updated_at = self.now()
        if record.cursor % SNAPSHOT_EVERY_OPS == 0:
            self.save_snapshot(session_id, "periodic")
        self.publish(
            session_id,
            {"type": "document_update", "op": op.model_dump(mode="json", by_alias=True, exclude_unset=True), "cursor": record.cursor},
            exclude=connection_id,
        )
        return OperationResult(True, cursor=record.cursor)
