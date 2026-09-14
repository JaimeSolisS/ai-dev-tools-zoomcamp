from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos, require_admin
from app.errors import bad_request, forbidden, not_found
from app.models.domain import Group, GroupStatus, Role, User
from app.repositories.bundle import Repositories
from app.schemas.balances import GroupBalances
from app.schemas.groups import AddMemberRequest, CreateGroupRequest, UpdateGroupRequest
from app.services.balance_calculator import compute_group_net, net_to_strings, simplify
from app.services.identity import new_id

router = APIRouter()


def _assert_group_access(group: Group, user: User) -> None:
    if user.role != Role.ADMIN and user.id not in group.member_ids:
        raise forbidden("You are not a member of this group.")


def _get_group_or_404(repos: Repositories, group_id: str) -> Group:
    group = repos.groups.get(group_id)
    if not group:
        raise not_found("Group not found.")
    return group


@router.get("/groups", response_model=list[Group])
def list_groups(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[Group]:
    groups = repos.groups.list()
    if current_user.role == Role.ADMIN:
        return groups
    return [g for g in groups if current_user.id in g.member_ids]


@router.post("/groups", response_model=Group, status_code=201)
def create_group(
    body: CreateGroupRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Group:
    if not body.name.strip():
        raise bad_request("Group name is required.")
    now = datetime.now(UTC)
    group = Group(
        id=new_id("grp"),
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        member_ids=list(dict.fromkeys(body.member_ids)),
        status=GroupStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    return repos.groups.create(group)


@router.get("/groups/{group_id}", response_model=Group)
def get_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    _assert_group_access(group, current_user)
    return group


@router.patch("/groups/{group_id}", response_model=Group)
def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if body.name is not None:
        if not body.name.strip():
            raise bad_request("Group name can't be empty.")
        updates["name"] = body.name.strip()
    if body.description is not None:
        updates["description"] = body.description.strip() or None
    group = group.model_copy(update=updates)
    return repos.groups.update(group)


@router.post("/groups/{group_id}/members", response_model=Group)
def add_member(
    group_id: str,
    body: AddMemberRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    if group.status == GroupStatus.ARCHIVED:
        raise bad_request("Archived groups are read-only.")
    member_ids = group.member_ids
    if body.user_id not in member_ids:
        member_ids = [*member_ids, body.user_id]
    group = group.model_copy(update={"member_ids": member_ids, "updated_at": datetime.now(UTC)})
    return repos.groups.update(group)


@router.delete("/groups/{group_id}/members/{user_id}", response_model=Group)
def remove_member(
    group_id: str,
    user_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    net = compute_group_net(group_id, repos.expenses.list(), repos.refunds.list())
    if net.get(user_id, 0) != 0:
        raise bad_request("You can't remove this member until their balance in this group is zero.")
    group = group.model_copy(
        update={
            "member_ids": [m for m in group.member_ids if m != user_id],
            "updated_at": datetime.now(UTC),
        }
    )
    return repos.groups.update(group)


@router.post("/groups/{group_id}/leave", response_model=Group)
def leave_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    net = compute_group_net(group_id, repos.expenses.list(), repos.refunds.list())
    if net.get(current_user.id, 0) != 0:
        raise bad_request("You can't leave this group until your balance here is zero.")
    group = group.model_copy(
        update={
            "member_ids": [m for m in group.member_ids if m != current_user.id],
            "updated_at": datetime.now(UTC),
        }
    )
    return repos.groups.update(group)


@router.post("/groups/{group_id}/archive", response_model=Group)
def archive_group(
    group_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Group:
    group = _get_group_or_404(repos, group_id)
    net = compute_group_net(group_id, repos.expenses.list(), repos.refunds.list())
    if any(amount != 0 for amount in net.values()):
        raise bad_request("This group can't be archived until all balances are zero.")
    group = group.model_copy(update={"status": GroupStatus.ARCHIVED, "updated_at": datetime.now(UTC)})
    return repos.groups.update(group)


@router.get("/groups/{group_id}/balances", response_model=GroupBalances)
def get_group_balances(
    group_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> GroupBalances:
    group = _get_group_or_404(repos, group_id)
    _assert_group_access(group, current_user)
    net = compute_group_net(group_id, repos.expenses.list(), repos.refunds.list())
    return GroupBalances(group_id=group_id, net=net_to_strings(net), pairs=simplify(net))
