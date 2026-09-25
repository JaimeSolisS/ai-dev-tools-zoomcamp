"""Authentication dependencies.

Interviewers send `Authorization: Bearer <accessToken>`; guests send
`X-Guest-Credential: <credential>` (see openapi.yaml `securitySchemes`).
Routes declare what they need with the annotated types at the bottom.

Dependencies are `async` so that, like the routes, they run on the event loop:
the in-memory store is not thread-safe.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError
from .store import ParticipantRecord, Store, UserRecord


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="userAuth")
guest_scheme = APIKeyHeader(name="X-Guest-Credential", auto_error=False, scheme_name="guestAuth")


async def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]


async def optional_user(
    store: StoreDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserRecord | None:
    """The signed-in user, or None. An invalid token counts as not signed in."""
    if credentials is None:
        return None
    return store.user_for_access_token(credentials.credentials)


async def require_user(user: Annotated[UserRecord | None, Depends(optional_user)]) -> UserRecord:
    if user is None:
        raise ApiError("UNAUTHENTICATED", "Please sign in to continue.")
    return user


async def guest_credential(value: Annotated[str | None, Depends(guest_scheme)]) -> str | None:
    return value or None


@dataclass
class Caller:
    user: UserRecord | None
    guest_credential: str | None


async def get_caller(
    user: Annotated[UserRecord | None, Depends(optional_user)],
    credential: Annotated[str | None, Depends(guest_credential)],
) -> Caller:
    return Caller(user=user, guest_credential=credential)


async def session_principal(
    session_id: str, store: StoreDep, caller: Annotated[Caller, Depends(get_caller)]
) -> ParticipantRecord:
    """The participant making this request (userAuth or guestAuth), for `{session_id}` routes."""
    return store.resolve_principal(session_id, caller.user, caller.guest_credential)


CurrentUser = Annotated[UserRecord, Depends(require_user)]
OptionalUser = Annotated[UserRecord | None, Depends(optional_user)]
CallerDep = Annotated[Caller, Depends(get_caller)]
Principal = Annotated[ParticipantRecord, Depends(session_principal)]
