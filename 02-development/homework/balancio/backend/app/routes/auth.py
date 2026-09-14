from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response

from app.config import Settings
from app.dependencies import get_app_settings, get_current_user, get_repos
from app.errors import bad_request, conflict, unauthorized
from app.models.domain import Role, Theme, User
from app.repositories.bundle import Repositories
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
    SetupStatus,
)
from app.schemas.users import UserOut
from app.security import create_access_token, hash_password, verify_password
from app.services.identity import new_id

router = APIRouter(prefix="/auth")


@router.get("/setup-status", response_model=SetupStatus)
def setup_status(repos: Repositories = Depends(get_repos)) -> SetupStatus:
    return SetupStatus(admin_exists=repos.users.any_admin())


@router.post("/setup", response_model=AuthResponse, status_code=201)
def setup(
    body: SetupRequest,
    repos: Repositories = Depends(get_repos),
    settings: Settings = Depends(get_app_settings),
) -> AuthResponse:
    if repos.users.any_admin():
        raise conflict("Setup has already been completed.")
    username = body.username.strip().lower()
    if not username:
        raise bad_request("Username is required.")
    if repos.users.get_by_username(username):
        raise bad_request("That username is already taken.")

    now = datetime.now(UTC)
    user = User(
        id=new_id("usr"),
        username=username,
        display_name=body.display_name.strip() or username,
        password_hash=hash_password(body.password),
        role=Role.ADMIN,
        is_active=True,
        must_change_password=False,
        theme=Theme.LIGHT,
        created_at=now,
        updated_at=now,
    )
    repos.users.create(user)
    token = create_access_token(user.id, settings.jwt_secret, settings.jwt_expiration_hours)
    return AuthResponse(user=UserOut.from_domain(user), access_token=token)


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    repos: Repositories = Depends(get_repos),
    settings: Settings = Depends(get_app_settings),
) -> AuthResponse:
    user = repos.users.get_by_username(body.username.strip().lower())
    if not user or not verify_password(body.password, user.password_hash):
        raise unauthorized("Incorrect username or password.")
    if not user.is_active:
        raise unauthorized("This account has been deactivated. Contact your admin.")
    token = create_access_token(user.id, settings.jwt_secret, settings.jwt_expiration_hours)
    return AuthResponse(user=UserOut.from_domain(user), access_token=token)


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
    if not verify_password(body.old_password, current_user.password_hash):
        raise bad_request("Current password is incorrect.")
    updated = current_user.model_copy(
        update={
            "password_hash": hash_password(body.new_password),
            "must_change_password": False,
            "updated_at": datetime.now(UTC),
        }
    )
    repos.users.update(updated)
    return UserOut.from_domain(updated)


@router.post("/logout", status_code=204, response_class=Response)
def logout(current_user: User = Depends(get_current_user)) -> Response:
    # Stateless JWT with no refresh-token system for the MVP: nothing to
    # invalidate server-side.
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_domain(current_user)
