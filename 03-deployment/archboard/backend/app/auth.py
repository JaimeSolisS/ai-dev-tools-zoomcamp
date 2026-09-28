"""Authentication dependencies.

Interviewers send `Authorization: Bearer <accessToken>`; guests send
`X-Guest-Credential: <credential>` (see openapi.yaml `securitySchemes`).
Routes declare what they need with the annotated types at the bottom.

Every request gets one `Store` (one database transaction). The dependency is
function-scoped so the transaction commits before the response is sent.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError
from .models import Participant, User
from .store import Store, StoreContext

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="userAuth")
guest_scheme = APIKeyHeader(name="X-Guest-Credential", auto_error=False, scheme_name="guestAuth")


def get_store(request: Request) -> Iterator[Store]:
    context: StoreContext = request.app.state.store_context
    with context.store() as store:
        yield store


StoreDep = Annotated[Store, Depends(get_store, scope="function")]


def optional_user(
    store: StoreDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    """The signed-in user, or None. An invalid token counts as not signed in."""
    if credentials is None:
        return None
    return store.user_for_access_token(credentials.credentials)


def require_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise ApiError("UNAUTHENTICATED", "Please sign in to continue.")
    return user


def guest_credential(value: Annotated[str | None, Depends(guest_scheme)]) -> str | None:
    return value or None


@dataclass
class Caller:
    user: User | None
    guest_credential: str | None


def get_caller(
    user: Annotated[User | None, Depends(optional_user)],
    credential: Annotated[str | None, Depends(guest_credential)],
) -> Caller:
    return Caller(user=user, guest_credential=credential)


def session_principal(session_id: str, store: StoreDep, caller: Annotated[Caller, Depends(get_caller)]) -> Participant:
    """The participant making this request (userAuth or guestAuth), for `{session_id}` routes."""
    return store.resolve_principal(session_id, caller.user, caller.guest_credential)


CurrentUser = Annotated[User, Depends(require_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
CallerDep = Annotated[Caller, Depends(get_caller)]
Principal = Annotated[Participant, Depends(session_principal)]
