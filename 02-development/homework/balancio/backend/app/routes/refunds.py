from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos
from app.errors import bad_request, forbidden, not_found
from app.models.domain import Group, GroupStatus, Refund, RefundConfirmation, RefundStatus, Role, User
from app.repositories.bundle import Repositories
from app.schemas.refunds import CreateRefundRequest
from app.services.identity import new_id

router = APIRouter(prefix="/refunds")


def _get_group_or_404(repos: Repositories, group_id: str) -> Group:
    group = repos.groups.get(group_id)
    if not group:
        raise not_found("Group not found.")
    return group


@router.get("", response_model=list[Refund])
def list_refunds(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[Refund]:
    return sorted(repos.refunds.list(), key=lambda r: r.created_at, reverse=True)


@router.post("", response_model=Refund, status_code=201)
def create_refund(
    body: CreateRefundRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Refund:
    group = _get_group_or_404(repos, body.group_id)
    if current_user.role != Role.ADMIN and current_user.id not in group.member_ids:
        raise forbidden("You are not a member of this group.")
    if group.status == GroupStatus.ARCHIVED:
        raise bad_request("This group is archived and read-only.")
    if not body.title.strip():
        raise bad_request("Title is required.")
    if body.amount <= 0:
        raise bad_request("Refund amount must be greater than zero.")
    if not body.participant_ids:
        raise bad_request("Select at least one participant.")
    if any(uid not in group.member_ids for uid in body.participant_ids):
        raise bad_request("Participants must be members of the group.")

    now = datetime.now(UTC)
    refund = Refund(
        id=new_id("rfd"),
        group_id=body.group_id,
        title=body.title.strip(),
        amount=body.amount,
        participant_ids=body.participant_ids,
        created_by=current_user.id,
        status=RefundStatus.PENDING,
        confirmations=[
            RefundConfirmation(user_id=uid, confirmed=(uid == current_user.id))
            for uid in body.participant_ids
        ],
        created_at=now,
        updated_at=now,
    )
    return repos.refunds.create(refund)


@router.get("/{refund_id}", response_model=Refund)
def get_refund(
    refund_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Refund:
    refund = repos.refunds.get(refund_id)
    if not refund:
        raise not_found("Refund not found.")
    return refund


@router.post("/{refund_id}/confirm", response_model=Refund)
def confirm_refund(
    refund_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Refund:
    refund = repos.refunds.get(refund_id)
    if not refund:
        raise not_found("Refund not found.")
    confirmations = list(refund.confirmations)
    index = next((i for i, c in enumerate(confirmations) if c.user_id == current_user.id), None)
    if index is None:
        raise bad_request("You are not a participant in this refund.")
    if refund.status == RefundStatus.CONFIRMED:
        raise bad_request("This refund is already confirmed.")
    if confirmations[index].confirmed:
        raise bad_request("You have already confirmed this refund.")

    confirmations[index] = RefundConfirmation(user_id=current_user.id, confirmed=True)
    updates: dict[str, Any] = {"confirmations": confirmations, "updated_at": datetime.now(UTC)}
    if all(c.confirmed for c in confirmations):
        updates["status"] = RefundStatus.CONFIRMED
    refund = refund.model_copy(update=updates)
    return repos.refunds.update(refund)
