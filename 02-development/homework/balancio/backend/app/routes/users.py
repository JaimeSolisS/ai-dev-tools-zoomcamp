from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos, require_admin
from app.errors import bad_request, forbidden, not_found
from app.models.domain import Role, Theme, User
from app.repositories.bundle import Repositories
from app.schemas.users import CreateUserRequest, ResetPasswordRequest, UpdateUserRequest, UserOut
from app.security import hash_password
from app.services.balance_calculator import compute_global_net
from app.services.identity import new_id

router = APIRouter(prefix="/users")


@router.get("", response_model=list[UserOut])
def list_users(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[UserOut]:
    return [UserOut.from_domain(u) for u in repos.users.list()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: CreateUserRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
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
        password_hash=hash_password(body.temporary_password),
        role=Role.USER,
        is_active=True,
        must_change_password=True,
        theme=Theme.LIGHT,
        created_at=now,
        updated_at=now,
    )
    repos.users.create(user)
    return UserOut.from_domain(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    return UserOut.from_domain(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    if current_user.role != Role.ADMIN and current_user.id != user_id:
        raise forbidden("You can only edit your own profile.")

    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if body.display_name is not None:
        if not body.display_name.strip():
            raise bad_request("Display name can't be empty.")
        updates["display_name"] = body.display_name.strip()
    if body.theme is not None:
        updates["theme"] = body.theme
    user = user.model_copy(update=updates)
    repos.users.update(user)
    return UserOut.from_domain(user)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> None:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    user = user.model_copy(
        update={
            "password_hash": hash_password(body.new_temporary_password),
            "must_change_password": True,
            "updated_at": datetime.now(UTC),
        }
    )
    repos.users.update(user)


@router.post("/{user_id}/force-password-change", status_code=204)
def force_password_change(
    user_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> None:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    user = user.model_copy(update={"must_change_password": True, "updated_at": datetime.now(UTC)})
    repos.users.update(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    net = compute_global_net(
        repos.expenses.list(),
        repos.refunds.list(),
        repos.settlements.list(),
        include_pending_settlements=True,
    )
    if net.get(user_id, 0) != 0:
        raise bad_request("You can't deactivate this user until their global balance is zero.")
    user = user.model_copy(update={"is_active": False, "updated_at": datetime.now(UTC)})
    repos.users.update(user)
    return UserOut.from_domain(user)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> UserOut:
    user = repos.users.get(user_id)
    if not user:
        raise not_found("User not found.")
    user = user.model_copy(update={"is_active": True, "updated_at": datetime.now(UTC)})
    repos.users.update(user)
    return UserOut.from_domain(user)
