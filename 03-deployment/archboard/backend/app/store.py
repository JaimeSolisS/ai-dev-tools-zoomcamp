"""Domain rules on top of the database.

A `Store` wraps one SQLAlchemy session, which is one unit of work: routes get a
store per request and WebSocket messages get one per message (see `auth.py` and
`routers/realtime.py`). `StoreContext.store()` commits on success and rolls back
on error. Room events are buffered and published only **after** the commit, so
clients never refetch data that isn't saved yet.

Methods enforce the same rules as the frontend's mock backend
(`frontend/src/services/mock/mockBackend.ts`) and raise `ApiError` with the codes
documented in openapi.yaml. They return Pydantic models, never ORM rows.
"""

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

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
from .tables import (
    AccessTokenRow,
    AuditEventRow,
    CanvasDocumentRow,
    CanvasElementRow,
    CanvasOperationRow,
    CanvasSnapshotRow,
    GuestLinkRow,
    MagicLinkRow,
    ParticipantRow,
    SessionRow,
    UserRow,
)

PARTICIPANT_COLORS = [
    "#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed",
    "#0891b2", "#dc2626", "#4f46e5", "#65a30d", "#c026d3",
]  # fmt: skip
SNAPSHOT_EVERY_OPS = 200
LAST_SEEN_WRITE_SECONDS = 10


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def utcnow() -> datetime:
    return datetime.now(UTC)


def newest_first[T](items: Iterable[T], key: Callable[[T], Any]) -> list[T]:
    """Sort descending by key; on ties the most recently inserted item comes first."""
    return list(reversed(sorted(items, key=key)))


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)


def _user(row: UserRow) -> User:
    return User.model_validate(row, from_attributes=True)


def _session(row: SessionRow) -> InterviewSession:
    return InterviewSession.model_validate(row, from_attributes=True)


def _participant(row: ParticipantRow) -> Participant:
    return Participant.model_validate(row, from_attributes=True)


def _link(row: GuestLinkRow) -> GuestLink:
    return GuestLink.model_validate(row, from_attributes=True)


def _snapshot(row: CanvasSnapshotRow) -> CanvasSnapshotInfo:
    return CanvasSnapshotInfo.model_validate(row, from_attributes=True)


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


@dataclass
class StoreContext:
    """Application-wide dependencies of the store. Open a unit of work with `store()`."""

    session_factory: sessionmaker
    settings: Settings = field(default_factory=Settings)
    events: EventSink = field(default_factory=NullSink)
    clock: Callable[[], datetime] = utcnow
    # Called for every newly created user (the seed module installs "create an example session").
    on_user_created: Callable[["Store", User], None] | None = None

    @contextmanager
    def store(self) -> Iterator["Store"]:
        db = self.session_factory()
        store = Store(db, self)
        try:
            yield store
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        store.flush_events()


class Store:
    def __init__(self, db: Session, ctx: StoreContext):
        self.db = db
        self.ctx = ctx
        self.settings = ctx.settings
        self._pending_events: list[tuple[str, str, Any, str | None]] = []

    def now(self) -> datetime:
        return self.ctx.clock()

    # ------------------------------------------------------------- events --

    def publish(self, session_id: str, payload: dict[str, Any], exclude: str | None = None) -> None:
        """Queue a room event; it is sent after the transaction commits."""
        self._pending_events.append(("publish", session_id, payload, exclude))

    def _disconnect(self, session_id: str, participant_id: str) -> None:
        self._pending_events.append(("disconnect", session_id, participant_id, None))

    def flush_events(self) -> None:
        events, self._pending_events = self._pending_events, []
        for kind, session_id, payload, exclude in events:
            if kind == "publish":
                self.ctx.events.publish(session_id, payload, exclude)
            else:
                self.ctx.events.disconnect_participant(session_id, payload)

    def audit(self, session_id: str, actor: str, action: str, **details: Any) -> None:
        self.db.add(
            AuditEventRow(
                id=new_id("audit"), session_id=session_id, actor=actor, action=action, at=self.now(), details=details
            )
        )

    def audit_log(self, session_id: str | None = None) -> list[AuditEventRow]:
        query = select(AuditEventRow).order_by(AuditEventRow.at)
        if session_id:
            query = query.where(AuditEventRow.session_id == session_id)
        return list(self.db.scalars(query))

    # -------------------------------------------------------------- users --

    def create_user(self, email: str, display_name: str | None = None, password: str | None = None) -> User:
        email = email.strip().lower()
        if self._user_row_by_email(email):
            raise ApiError("CONFLICT", "A user with this email already exists.")
        local = email.split("@")[0]
        row = UserRow(
            id=new_id("u"),
            email=email,
            display_name=display_name or local[:1].upper() + local[1:],
            organization_id=None,
            password_hash=hash_password(password) if password else None,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        user = _user(row)
        if self.ctx.on_user_created:
            self.ctx.on_user_created(self, user)
        return user

    def _user_row_by_email(self, email: str) -> UserRow | None:
        return self.db.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))

    def find_user_by_email(self, email: str) -> User | None:
        row = self._user_row_by_email(email)
        return _user(row) if row else None

    def has_users(self) -> bool:
        return self.db.scalar(select(func.count()).select_from(UserRow)) > 0

    def issue_access_token(self, user: User) -> str:
        token = new_token()
        self.db.add(AccessTokenRow(token_hash=hash_token(token), user_id=user.id, created_at=self.now()))
        return token

    def user_for_access_token(self, token: str) -> User | None:
        row = self.db.scalar(
            select(UserRow)
            .join(AccessTokenRow, AccessTokenRow.user_id == UserRow.id)
            .where(AccessTokenRow.token_hash == hash_token(token))
        )
        return _user(row) if row else None

    def revoke_access_token(self, token: str) -> None:
        self.db.execute(delete(AccessTokenRow).where(AccessTokenRow.token_hash == hash_token(token)))

    def request_magic_link(self, email: str) -> str:
        token = new_token()
        expires = self.now() + timedelta(minutes=self.settings.magic_link_ttl_minutes)
        self.db.add(MagicLinkRow(token_hash=hash_token(token), email=email.strip().lower(), expires_at=expires))
        return token

    def verify_magic_link(self, token: str) -> User:
        row = self.db.get(MagicLinkRow, hash_token(token))
        if row is None or row.expires_at <= self.now():
            raise ApiError("LINK_INVALID", "This sign-in link is invalid or has expired.")
        email = row.email
        self.db.delete(row)  # single use
        return self.find_user_by_email(email) or self.create_user(email)

    def login(self, email: str, password: str) -> User:
        row = self._user_row_by_email(email)
        # Same error for unknown email and wrong password.
        if row is None or not row.password_hash or not verify_password(password, row.password_hash):
            raise ApiError("UNAUTHENTICATED", "Invalid email or password.")
        return _user(row)

    # --------------------------------------------------------- principals --

    def _session_row(self, session_id: str) -> SessionRow:
        row = self.db.get(SessionRow, session_id)
        if row is None:
            raise ApiError("NOT_FOUND", "Interview not found.")
        return row

    def get_session(self, session_id: str) -> InterviewSession:
        return _session(self._session_row(session_id))

    def _owned_row(self, user: User, session_id: str) -> SessionRow:
        """Owner-only access; everyone else gets NOT_FOUND so ids cannot be probed."""
        row = self._session_row(session_id)
        if row.owner_user_id != user.id:
            raise ApiError("NOT_FOUND", "Interview not found.")
        return row

    def require_owner(self, user: User, session_id: str) -> InterviewSession:
        return _session(self._owned_row(user, session_id))

    def _participant_by_credential(self, session_id: str, credential: str) -> ParticipantRow | None:
        return self.db.scalar(
            select(ParticipantRow).where(
                ParticipantRow.session_id == session_id, ParticipantRow.credential_hash == hash_token(credential)
            )
        )

    def resolve_principal(self, session_id: str, user: User | None, guest_credential: str | None) -> Participant:
        """Who is calling for this session: a guest credential (preferred) or the signed-in user."""
        session = self._session_row(session_id)
        if guest_credential:
            row = self._participant_by_credential(session_id, guest_credential)
            if row is not None:
                if row.removed_at:
                    raise ApiError("PARTICIPANT_REMOVED", "You were removed from this interview.")
                return _participant(row)
            # A credential for another session is ignored here, not an error.
        if user is None:
            raise ApiError("UNAUTHENTICATED", "Join this interview through its invitation link.")
        rows = list(
            self.db.scalars(
                select(ParticipantRow)
                .where(ParticipantRow.session_id == session_id, ParticipantRow.user_id == user.id)
                .order_by(ParticipantRow.joined_at)
            )
        )
        mine = next((r for r in rows if r.credential_hash is None), None)
        if session.owner_user_id == user.id:
            if mine:
                return _participant(mine)
            return self.add_participant(session_id, user.id, user.display_name, "owner", None)
        # Interviewers/observers who joined through a link while signed in.
        linked = mine or (rows[0] if rows else None)
        if linked is not None and not linked.removed_at:
            return _participant(linked)
        raise ApiError("NOT_FOUND", "Interview not found.")

    # ----------------------------------------------------------- sessions --

    def list_sessions(self, user: User) -> list[SessionSummary]:
        invited = select(ParticipantRow.session_id).where(
            ParticipantRow.user_id == user.id, ParticipantRow.removed_at.is_(None)
        )
        rows = self.db.scalars(
            select(SessionRow)
            .where(or_(SessionRow.owner_user_id == user.id, SessionRow.id.in_(invited)))
            .order_by(SessionRow.created_at)
        )
        return newest_first((self.summarize(r) for r in rows), key=lambda s: s.last_modified_at)

    def summarize(self, row: SessionRow) -> SessionSummary:
        names = self.db.scalars(
            select(ParticipantRow.display_name)
            .where(
                ParticipantRow.session_id == row.id,
                ParticipantRow.removed_at.is_(None),
                ParticipantRow.role != "owner",
            )
            .order_by(ParticipantRow.joined_at)
        )
        doc = self.db.get(CanvasDocumentRow, row.id)
        links = self.db.scalars(
            select(GuestLinkRow)
            .where(GuestLinkRow.session_id == row.id, GuestLinkRow.role_granted == "candidate")
            .order_by(GuestLinkRow.created_at)
        )
        active = newest_first((link for link in links if self._link_active(link)), key=lambda link: link.created_at)
        return SessionSummary(
            **_session(row).model_dump(),
            participant_names=list(names),
            last_modified_at=max(row.updated_at, doc.updated_at) if doc else row.updated_at,
            active_guest_link=_link(active[0]) if active else None,
        )

    def create_session(self, user: User, data: CreateSessionInput) -> InterviewSession:
        if data.template_session_id:
            self._owned_row(user, data.template_session_id)
        session = self.insert_session(
            user,
            title=data.title,
            prompt=data.prompt,
            duration_minutes=data.duration_minutes,
            scheduled_at=data.scheduled_at,
        )
        if data.template_session_id:
            self._copy_canvas(data.template_session_id, session.id)
        self.audit(session.id, user.id, "session.created")
        return session

    def insert_session(self, owner: User, **fields: Any) -> InterviewSession:
        """Create a session row, its (empty) canvas and the owner's participant."""
        now = self.now()
        row = SessionRow(
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
        self.db.add(row)
        self.db.flush()  # the session row must exist before rows that reference it
        self.db.add(CanvasDocumentRow(session_id=row.id, schema_version=1, cursor=0, updated_at=now))
        self.db.flush()
        self.add_participant(row.id, owner.id, owner.display_name, "owner", None)
        return _session(row)

    def _touch(self, row: SessionRow, **changes: Any) -> InterviewSession:
        for name, value in changes.items():
            setattr(row, name, value)
        row.updated_at = self.now()
        self.db.flush()
        return _session(row)

    def update_session(self, principal: Participant, session_id: str, patch: UpdateSessionInput) -> InterviewSession:
        row = self._session_row(session_id)
        perms = compute_permissions(principal.role, row.state, row.candidate_editing_enabled)  # type: ignore[arg-type]
        fields = patch.model_fields_set
        settings_fields = {"title", "prompt", "duration_minutes", "scheduled_at", "show_cursors"}
        if fields & settings_fields and not perms.can_edit_settings:
            raise ApiError("FORBIDDEN", "Only the owner can change interview settings.")
        if "candidate_editing_enabled" in fields and not perms.can_lock_editing:
            raise ApiError("FORBIDDEN", "You cannot change editing permissions.")
        updated = self._touch(row, **{name: getattr(patch, name) for name in fields})
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
        row = self._owned_row(user, session_id)
        if row.state != "draft":
            raise ApiError("CONFLICT", "Only draft interviews can be started.")
        updated = self._touch(row, state="live", started_at=self.now())
        self.audit(session_id, user.id, "session.started")
        self.publish(session_id, {"type": "session_updated", "session": _dump(updated)})
        return updated

    def end_session(self, user: User, session_id: str) -> InterviewSession:
        row = self._owned_row(user, session_id)
        if row.state not in ("draft", "live"):
            raise ApiError("CONFLICT", "This interview is not running.")
        self.save_snapshot(session_id, "final")
        updated = self._touch(row, state="ended", ended_at=self.now())
        self.audit(session_id, user.id, "session.ended")
        self.publish(session_id, {"type": "session_ended", "session": _dump(updated)})
        return updated

    def reopen_session(self, user: User, session_id: str) -> InterviewSession:
        row = self._owned_row(user, session_id)
        if row.state != "ended":
            raise ApiError("CONFLICT", "Only ended interviews can be reopened.")
        updated = self._touch(row, state="live", ended_at=None)
        self.audit(session_id, user.id, "session.reopened")
        self.publish(session_id, {"type": "session_updated", "session": _dump(updated)})
        return updated

    def archive_session(self, user: User, session_id: str) -> InterviewSession:
        row = self._owned_row(user, session_id)
        was_live = row.state == "live"
        if was_live:
            self.save_snapshot(session_id, "final")
        updated = self._touch(row, state="archived", ended_at=row.ended_at or (self.now() if was_live else None))
        self.audit(session_id, user.id, "session.archived")
        self.publish(session_id, {"type": "session_ended", "session": _dump(updated)})
        return updated

    def duplicate_session(self, user: User, session_id: str) -> InterviewSession:
        row = self._owned_row(user, session_id)
        copy = self.insert_session(
            user,
            title=f"{row.title} (copy)"[:120],
            prompt=row.prompt,
            duration_minutes=row.duration_minutes,
        )
        self._copy_canvas(session_id, copy.id)
        self.audit(copy.id, user.id, "session.created", duplicated_from=session_id)
        return copy

    # ------------------------------------------------------- participants --

    def add_participant(
        self, session_id: str, user_id: str | None, display_name: str, role: Role, credential_hash: str | None
    ) -> Participant:
        used = self.db.scalar(
            select(func.count()).select_from(ParticipantRow).where(ParticipantRow.session_id == session_id)
        )
        now = self.now()
        row = ParticipantRow(
            id=new_id("p"),
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            role=role,
            color=PARTICIPANT_COLORS[0] if role == "owner" else PARTICIPANT_COLORS[used % len(PARTICIPANT_COLORS)],
            credential_hash=credential_hash,
            joined_at=now,
            left_at=None,
            removed_at=None,
            last_seen_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return _participant(row)

    def get_participant(self, participant_id: str) -> Participant | None:
        row = self.db.get(ParticipantRow, participant_id)
        return _participant(row) if row else None

    def list_participants(self, session_id: str) -> list[Participant]:
        rows = self.db.scalars(
            select(ParticipantRow)
            .where(ParticipantRow.session_id == session_id, ParticipantRow.removed_at.is_(None))
            .order_by(ParticipantRow.joined_at)
        )
        return [_participant(r) for r in rows]

    def remove_participant(self, user: User, session_id: str, participant_id: str) -> None:
        self._owned_row(user, session_id)
        row = self.db.get(ParticipantRow, participant_id)
        if row is None or row.session_id != session_id:
            raise ApiError("NOT_FOUND", "Participant not found.")
        if row.role == "owner":
            raise ApiError("VALIDATION", "The owner cannot be removed.")
        row.removed_at = row.left_at = self.now()
        self.audit(session_id, user.id, "participant.removed", participant_id=participant_id)
        self.publish(session_id, {"type": "participant_removed", "participantId": participant_id})
        self.publish(session_id, {"type": "participants_changed"})
        self._disconnect(session_id, participant_id)

    def mark_seen(self, participant_id: str, *, left: bool = False) -> None:
        row = self.db.get(ParticipantRow, participant_id)
        if row is None:
            return
        now = self.now()
        if not left and row.last_seen_at and (now - row.last_seen_at).total_seconds() < LAST_SEEN_WRITE_SECONDS:
            return
        row.last_seen_at = now
        row.left_at = now if left else None

    def _active_participant_count(self, session_id: str) -> int:
        cutoff = self.now() - timedelta(seconds=self.settings.active_window_seconds)
        return self.db.scalar(
            select(func.count())
            .select_from(ParticipantRow)
            .where(
                ParticipantRow.session_id == session_id,
                ParticipantRow.removed_at.is_(None),
                ParticipantRow.left_at.is_(None),
                ParticipantRow.last_seen_at >= cutoff,
            )
        )

    # -------------------------------------------------------- guest links --

    def _link_active(self, link: GuestLinkRow) -> bool:
        if link.revoked_at:
            return False
        if link.expires_at and link.expires_at <= self.now():
            return False
        return not (link.max_uses is not None and link.uses >= link.max_uses)

    def list_links(self, user: User, session_id: str) -> list[GuestLink]:
        self._owned_row(user, session_id)
        rows = self.db.scalars(
            select(GuestLinkRow).where(GuestLinkRow.session_id == session_id).order_by(GuestLinkRow.created_at)
        )
        return newest_first((_link(r) for r in rows), key=lambda link: link.created_at)

    def create_link(
        self, user: User, session_id: str, data: CreateGuestLinkInput, token: str | None = None
    ) -> tuple[GuestLink, str]:
        session = self._owned_row(user, session_id)
        if session.state in ("ended", "archived"):
            raise ApiError("SESSION_ENDED", "Reopen the interview before sharing it.")
        if data.rotate:
            self.db.execute(
                update(GuestLinkRow)
                .where(
                    GuestLinkRow.session_id == session_id,
                    GuestLinkRow.role_granted == data.role_granted,
                    GuestLinkRow.revoked_at.is_(None),
                )
                .values(revoked_at=self.now())
                .execution_options(synchronize_session=False)
            )
        token = token or new_token()
        row = GuestLinkRow(
            id=new_id("gl"),
            session_id=session_id,
            token_hash=hash_token(token),
            role_granted=data.role_granted,
            expires_at=data.expires_at,
            max_uses=data.max_uses,
            uses=0,
            revoked_at=None,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        self.audit(session_id, user.id, "link.rotated" if data.rotate else "link.created", link_id=row.id)
        return _link(row), token

    def revoke_link(self, user: User, session_id: str, link_id: str) -> None:
        self._owned_row(user, session_id)
        row = self.db.get(GuestLinkRow, link_id)
        if row is None or row.session_id != session_id:
            raise ApiError("NOT_FOUND", "Link not found.")
        if not row.revoked_at:
            row.revoked_at = self.now()
        self.audit(session_id, user.id, "link.revoked", link_id=link_id)

    # --------------------------------------------------------------- join --

    def _find_link(self, token: str) -> tuple[GuestLinkRow, SessionRow]:
        link = self.db.scalar(select(GuestLinkRow).where(GuestLinkRow.token_hash == hash_token(token)))
        session = self.db.get(SessionRow, link.session_id) if link else None
        if link is None or session is None:
            raise ApiError("LINK_INVALID", "This invitation link is not valid.")
        return link, session

    def _assert_joinable(self, link: GuestLinkRow, session: SessionRow, *, returning: bool) -> None:
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
        return JoinInfo(
            session_title=session.title,
            session_state=session.state,  # type: ignore[arg-type]
            role_granted=link.role_granted,  # type: ignore[arg-type]
        )

    def join(
        self, token: str, display_name: str, user: User | None, guest_credential: str | None
    ) -> tuple[Participant, str]:
        """Returns the participant and the guest credential to use for this session."""
        link, session = self._find_link(token)

        # Reconnect with an existing credential for this session.
        if guest_credential:
            existing = self._participant_by_credential(session.id, guest_credential)
            if existing is not None:
                if existing.removed_at:
                    raise ApiError("PARTICIPANT_REMOVED", "You were removed from this interview.")
                self._assert_joinable(link, session, returning=True)
                existing.display_name = display_name
                existing.left_at = None
                existing.last_seen_at = self.now()
                self.db.flush()
                self.publish(session.id, {"type": "participants_changed"})
                return _participant(existing), guest_credential

        self._assert_joinable(link, session, returning=False)
        if self._active_participant_count(session.id) >= self.settings.max_participants:
            raise ApiError("SESSION_FULL", f"This interview already has {self.settings.max_participants} participants.")
        credential = new_token()
        linked_user = user if link.role_granted in ("interviewer", "observer") else None
        participant = self.add_participant(
            session.id,
            linked_user.id if linked_user else None,
            display_name,
            link.role_granted,  # type: ignore[arg-type]
            hash_token(credential),
        )
        link.uses += 1
        self.audit(session.id, participant.id, "participant.joined", role=participant.role)
        self.publish(session.id, {"type": "participants_changed"})
        return participant, credential

    # ------------------------------------------------------------- canvas --

    def _document(self, session_id: str) -> CanvasDocumentRow:
        doc = self.db.get(CanvasDocumentRow, session_id)
        if doc is None:
            doc = CanvasDocumentRow(session_id=session_id, schema_version=1, cursor=0, updated_at=self.now())
            self.db.add(doc)
            self.db.flush()
        return doc

    def canvas_cursor(self, session_id: str) -> int:
        return self._document(session_id).cursor

    def canvas_elements(self, session_id: str) -> dict[str, dict[str, Any]]:
        rows = self.db.scalars(
            select(CanvasElementRow)
            .where(CanvasElementRow.session_id == session_id)
            .order_by(CanvasElementRow.element_id)
            # Elements are written with bulk UPDATEs; don't trust cached objects.
            .execution_options(populate_existing=True)
        )
        return {row.element_id: row.data for row in rows}

    def put_elements(self, session_id: str, elements: dict[str, dict[str, Any]]) -> None:
        """Insert element entries as-is (used for copies, restores and seeding)."""
        for element_id, entry in elements.items():
            self.db.add(
                CanvasElementRow(
                    session_id=session_id,
                    element_id=element_id,
                    clock=entry["version"]["clock"],
                    actor=entry["version"]["actor"],
                    deleted=canvas.is_tombstone(entry),
                    data=entry,
                )
            )
        self.db.flush()

    def _copy_canvas(self, from_session_id: str, to_session_id: str) -> None:
        self._document(to_session_id)
        self.put_elements(to_session_id, self.canvas_elements(from_session_id))

    def open_room(self, principal: Participant) -> RoomAccess:
        session = self._session_row(principal.session_id)
        perms = compute_permissions(principal.role, session.state, session.candidate_editing_enabled)  # type: ignore[arg-type]
        if not perms.can_view:
            if session.state == "ended":
                raise ApiError("SESSION_ENDED", "This interview has ended.")
            if session.state == "archived":
                raise ApiError("SESSION_ARCHIVED", "This interview has been archived.")
            raise ApiError("FORBIDDEN", "You do not have access to this interview.")
        doc = self._document(session.id)
        return RoomAccess(
            session=_session(session),
            me=principal,
            participants=self.list_participants(session.id),
            canvas=CanvasDoc(schema_version=doc.schema_version, elements=self.canvas_elements(session.id)),
            cursor=doc.cursor,
            permissions=perms,
        )

    def save_snapshot(self, session_id: str, reason: SnapshotReason) -> CanvasSnapshotInfo:
        doc = self._document(session_id)
        elements = self.canvas_elements(session_id)
        row = CanvasSnapshotRow(
            id=new_id("snap"),
            session_id=session_id,
            reason=reason,
            operation_cursor=doc.cursor,
            element_count=canvas.live_count(elements),
            elements=elements,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return _snapshot(row)

    def _replace_canvas(self, session_id: str, elements: dict[str, dict[str, Any]]) -> None:
        doc = self._document(session_id)
        self.db.execute(
            delete(CanvasElementRow)
            .where(CanvasElementRow.session_id == session_id)
            .execution_options(synchronize_session=False)
        )
        self.db.expire_all()
        self.put_elements(session_id, elements)
        doc.cursor += 1
        doc.updated_at = self.now()

    def _require_open_owner(self, user: User, session_id: str) -> None:
        row = self._owned_row(user, session_id)
        if not compute_permissions("owner", row.state, row.candidate_editing_enabled).can_clear_canvas:  # type: ignore[arg-type]
            raise ApiError("SESSION_ENDED", "This interview has ended.")

    def clear_canvas(self, user: User, session_id: str) -> None:
        self._require_open_owner(user, session_id)
        self.save_snapshot(session_id, "before-clear")
        self._replace_canvas(session_id, {})
        self.audit(session_id, user.id, "canvas.cleared")
        self.publish(session_id, {"type": "canvas_reset"})

    def list_snapshots(self, user: User, session_id: str) -> list[CanvasSnapshotInfo]:
        self._owned_row(user, session_id)
        rows = self.db.scalars(
            select(CanvasSnapshotRow)
            .where(CanvasSnapshotRow.session_id == session_id)
            .order_by(CanvasSnapshotRow.created_at)
        )
        return newest_first((_snapshot(r) for r in rows), key=lambda s: s.created_at)

    def restore_snapshot(self, user: User, session_id: str, snapshot_id: str) -> None:
        self._require_open_owner(user, session_id)
        snapshot = self.db.get(CanvasSnapshotRow, snapshot_id)
        if snapshot is None or snapshot.session_id != session_id:
            raise ApiError("NOT_FOUND", "Snapshot not found.")
        elements = dict(snapshot.elements)
        self.save_snapshot(session_id, "before-restore")
        self._replace_canvas(session_id, elements)
        self.audit(session_id, user.id, "canvas.restored", snapshot_id=snapshot_id)
        self.publish(session_id, {"type": "canvas_reset"})

    def _write_entry(self, session_id: str, element_id: str, entry: dict[str, Any]) -> None:
        """Last-writer-wins write of one element, decided atomically by the database."""
        clock, actor = entry["version"]["clock"], entry["version"]["actor"]
        values = {"clock": clock, "actor": actor, "deleted": canvas.is_tombstone(entry), "data": entry}
        newer = or_(
            CanvasElementRow.clock < clock,
            and_(CanvasElementRow.clock == clock, CanvasElementRow.actor < actor),
        )
        result = self.db.execute(
            update(CanvasElementRow)
            .where(CanvasElementRow.session_id == session_id, CanvasElementRow.element_id == element_id, newer)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0 and self.db.get(CanvasElementRow, (session_id, element_id)) is None:
            self.db.add(CanvasElementRow(session_id=session_id, element_id=element_id, **values))
            self.db.flush()

    def apply_client_operation(
        self, session_id: str, participant_id: str, raw_op: Any, connection_id: str | None = None
    ) -> OperationResult:
        """Authorize, validate, persist and fan out one operation from a WebSocket client."""
        participant = self.db.get(ParticipantRow, participant_id)
        if participant is None or participant.session_id != session_id:
            return OperationResult(False, code="FORBIDDEN", message="Unknown participant.")
        if participant.removed_at:
            return OperationResult(False, code="PARTICIPANT_REMOVED", message="You were removed from this interview.")
        session = self._session_row(session_id)
        perms = compute_permissions(participant.role, session.state, session.candidate_editing_enabled)  # type: ignore[arg-type]
        if not perms.can_edit:
            if session.state in ("ended", "archived"):
                return OperationResult(
                    False, code="SESSION_ENDED", message="The interview has ended; the canvas is read-only."
                )
            if participant.role == "candidate" and session.state == "live":
                return OperationResult(False, code="EDIT_LOCKED", message="The interviewer has locked editing.")
            return OperationResult(False, code="FORBIDDEN", message="You cannot edit this canvas.")
        try:
            op = canvas.parse_operation(raw_op)
        except canvas.InvalidOperation as exc:
            return OperationResult(False, code="VALIDATION", message=str(exc))
        if op.actor_id != participant.id:
            return OperationResult(False, code="FORBIDDEN", message="Operation actor does not match the connection.")

        doc = self._document(session_id)
        duplicate = self.db.scalar(
            select(CanvasOperationRow.id).where(
                CanvasOperationRow.session_id == session_id, CanvasOperationRow.client_operation_id == op.id
            )
        )
        if duplicate is not None:
            return OperationResult(True, cursor=doc.cursor, duplicate=True)

        for change in op.changes:
            element_id, entry = canvas.entry_for(change)
            self._write_entry(session_id, element_id, entry)
        count = self.db.scalar(
            select(func.count()).select_from(CanvasElementRow).where(CanvasElementRow.session_id == session_id)
        )
        if count > canvas.MAX_ELEMENTS:
            self.db.rollback()
            return OperationResult(False, code="VALIDATION", message="The canvas has too many elements.")

        # Incrementing in SQL locks the document row, serializing concurrent operations.
        self.db.execute(
            update(CanvasDocumentRow)
            .where(CanvasDocumentRow.session_id == session_id)
            .values(cursor=CanvasDocumentRow.cursor + 1, updated_at=self.now())
            .execution_options(synchronize_session=False)
        )
        self.db.refresh(doc)
        payload = op.model_dump(mode="json", by_alias=True, exclude_unset=True)
        self.db.add(
            CanvasOperationRow(
                session_id=session_id,
                client_operation_id=op.id,
                actor_id=participant.id,
                cursor=doc.cursor,
                payload=payload,
                server_received_at=self.now(),
            )
        )
        try:
            self.db.flush()
        except IntegrityError:
            # The same operation id was committed concurrently: treat it as a duplicate.
            self.db.rollback()
            return OperationResult(True, cursor=self.canvas_cursor(session_id), duplicate=True)
        if doc.cursor % SNAPSHOT_EVERY_OPS == 0:
            self.save_snapshot(session_id, "periodic")
        self.publish(
            session_id, {"type": "document_update", "op": payload, "cursor": doc.cursor}, exclude=connection_id
        )
        return OperationResult(True, cursor=doc.cursor)
