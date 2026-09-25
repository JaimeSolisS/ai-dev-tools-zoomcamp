"""ORM tables. Follows the data model in _docs/spec.md §11.

Only portable column types are used so the same schema works on SQLite and
Postgres. Secrets (passwords, tokens, credentials) are stored only as hashes.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, UTCDateTime

ID = String(64)
HASH = String(64)  # SHA-256 hex digest


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    organization_id: Mapped[str | None] = mapped_column(ID)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AccessTokenRow(Base):
    __tablename__ = "access_tokens"

    token_hash: Mapped[str] = mapped_column(HASH, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MagicLinkRow(Base):
    __tablename__ = "magic_links"

    token_hash: Mapped[str] = mapped_column(HASH, primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SessionRow(Base):
    """An interview session (`InterviewSession` in the API)."""

    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(16))
    candidate_editing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    show_cursors: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class GuestLinkRow(Base):
    __tablename__ = "guest_links"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(HASH, unique=True)
    role_granted: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ParticipantRow(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    color: Mapped[str] = mapped_column(String(16))
    credential_hash: Mapped[str | None] = mapped_column(HASH, unique=True)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class CanvasDocumentRow(Base):
    """One per session. `cursor` counts applied operations."""

    __tablename__ = "canvas_documents"

    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CanvasElementRow(Base):
    """Current state of one canvas element (or its tombstone).

    `clock`/`actor` duplicate the element's version so last-writer-wins can be
    decided inside a single conditional UPDATE, which stays correct under
    concurrent writers on any database.
    """

    __tablename__ = "canvas_elements"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("canvas_documents.session_id", ondelete="CASCADE"), primary_key=True
    )
    element_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    clock: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(200))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class CanvasOperationRow(Base):
    """Operation log; the unique constraint rejects duplicate client operations."""

    __tablename__ = "canvas_operations"
    __table_args__ = (UniqueConstraint("session_id", "client_operation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("canvas_documents.session_id", ondelete="CASCADE"))
    client_operation_id: Mapped[str] = mapped_column(String(200))
    actor_id: Mapped[str] = mapped_column(ID)
    cursor: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    server_received_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CanvasSnapshotRow(Base):
    __tablename__ = "canvas_snapshots"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(32))
    operation_cursor: Mapped[int] = mapped_column(Integer)
    element_count: Mapped[int] = mapped_column(Integer)
    elements: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_session_at", "session_id", "at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    session_id: Mapped[str] = mapped_column(ID)
    actor: Mapped[str] = mapped_column(ID)
    action: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
