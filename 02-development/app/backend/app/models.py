"""API models. Field names are snake_case in Python and camelCase on the wire (see openapi.yaml)."""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

SessionState = Literal["draft", "live", "ended", "archived"]
Role = Literal["owner", "interviewer", "candidate", "observer"]
GuestRole = Literal["interviewer", "candidate", "observer"]
SnapshotReason = Literal["final", "before-clear", "periodic", "before-restore"]

MAX_TEXT = 2000
MAX_PROMPT = 10_000
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Title is required.")
    if len(value) > 120:
        raise ValueError("Title must be at most 120 characters.")
    return value


def _duration(value: int | None) -> int | None:
    if value is not None and not 5 <= value <= 480:
        raise ValueError("Duration must be between 5 and 480 minutes.")
    return value


# ---------------------------------------------------------------------- auth --


class User(CamelModel):
    id: str
    email: str
    display_name: str
    organization_id: str | None = None
    created_at: datetime


class MagicLinkRequestInput(CamelModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address.")
        return value


class MagicLinkRequest(CamelModel):
    sent: Literal[True] = True
    dev_token: str | None = None


class VerifyMagicLinkInput(CamelModel):
    token: str


class LoginInput(CamelModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(CamelModel):
    user: User
    access_token: str


# ------------------------------------------------------------------ sessions --


class InterviewSession(CamelModel):
    id: str
    owner_user_id: str
    title: str
    prompt: str
    state: SessionState
    candidate_editing_enabled: bool
    show_cursors: bool
    duration_minutes: int | None
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GuestLink(CamelModel):
    id: str
    session_id: str
    role_granted: GuestRole
    expires_at: datetime | None
    max_uses: int | None
    uses: int
    revoked_at: datetime | None
    created_at: datetime


class SessionSummary(InterviewSession):
    participant_names: list[str]
    last_modified_at: datetime
    active_guest_link: GuestLink | None


class CreateSessionInput(CamelModel):
    title: str
    prompt: str = Field(default="", max_length=MAX_PROMPT)
    duration_minutes: int | None = None
    scheduled_at: datetime | None = None
    template_session_id: str | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str) -> str:
        return _title(value)

    @field_validator("duration_minutes")
    @classmethod
    def check_duration(cls, value: int | None) -> int | None:
        return _duration(value)


class UpdateSessionInput(CamelModel):
    """Only fields present in the request are applied (see `model_fields_set`)."""

    title: str | None = None
    prompt: str | None = Field(default=None, max_length=MAX_PROMPT)
    duration_minutes: int | None = None
    scheduled_at: datetime | None = None
    candidate_editing_enabled: bool | None = None
    show_cursors: bool | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Title is required.")
        return _title(value)

    @field_validator("duration_minutes")
    @classmethod
    def check_duration(cls, value: int | None) -> int | None:
        return _duration(value)

    @field_validator("prompt", "candidate_editing_enabled", "show_cursors")
    @classmethod
    def not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Value may not be null.")
        return value


# -------------------------------------------------------------- participants --


class Participant(CamelModel):
    id: str
    session_id: str
    user_id: str | None
    display_name: str
    role: Role
    color: str
    joined_at: datetime
    left_at: datetime | None
    removed_at: datetime | None
    last_seen_at: datetime | None


# --------------------------------------------------------------- guest links --


class CreateGuestLinkInput(CamelModel):
    role_granted: GuestRole = "candidate"
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    rotate: bool = False


class CreatedGuestLink(CamelModel):
    link: GuestLink
    token: str


# ---------------------------------------------------------------------- join --


class JoinInfo(CamelModel):
    session_title: str
    session_state: SessionState
    role_granted: GuestRole


class JoinInput(CamelModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter your name.")
        if len(value) > 60:
            raise ValueError("Name must be at most 60 characters.")
        return value


class JoinResult(CamelModel):
    session_id: str
    participant: Participant
    credential: str


# -------------------------------------------------------------------- canvas --


class Permissions(CamelModel):
    can_view: bool
    can_edit: bool
    can_lock_editing: bool
    can_share: bool
    can_remove_participants: bool
    can_start_or_end: bool
    can_clear_canvas: bool
    can_edit_settings: bool


class CanvasDoc(CamelModel):
    schema_version: int = 1
    # Element entries are stored exactly as validated JSON (camelCase keys); see canvas.py.
    elements: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RoomAccess(CamelModel):
    session: InterviewSession
    me: Participant
    participants: list[Participant]
    canvas: CanvasDoc
    cursor: int
    permissions: Permissions


class CanvasSnapshotInfo(CamelModel):
    id: str
    session_id: str
    reason: SnapshotReason
    operation_cursor: int
    element_count: int
    created_at: datetime


class ErrorBody(CamelModel):
    code: str
    message: str
