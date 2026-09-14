from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import forbidden, unauthorized
from app.models.domain import Role, User
from app.repositories.bundle import Repositories, build_repositories
from app.security import decode_access_token


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_repos(session: Session = Depends(get_session)) -> Repositories:
    return build_repositories(session)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_current_user(
    authorization: str | None = Header(default=None),
    repos: Repositories = Depends(get_repos),
    settings: Settings = Depends(get_app_settings),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("You need to log in to do that.")
    token = authorization.split(" ", 1)[1]
    user_id = decode_access_token(token, settings.jwt_secret)
    if not user_id:
        raise unauthorized("Your session is no longer valid. Please log in again.")
    user = repos.users.get(user_id)
    if not user:
        raise unauthorized("Your session is no longer valid. Please log in again.")
    if not user.is_active:
        raise unauthorized("This account has been deactivated. Contact your admin.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise forbidden("Only the admin can do that.")
    return user
