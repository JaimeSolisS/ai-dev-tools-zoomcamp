from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos
from app.errors import bad_request, forbidden, not_found
from app.models.domain import Role, Settlement, SettlementStatus, User
from app.repositories.bundle import Repositories
from app.schemas.settlements import CreateSettlementRequest, UpdateSettlementRequest
from app.services.identity import new_id

router = APIRouter(prefix="/settlements")


def _get_settlement_or_404(repos: Repositories, settlement_id: str) -> Settlement:
    settlement = repos.settlements.get(settlement_id)
    if not settlement:
        raise not_found("Settlement not found.")
    return settlement


@router.get("", response_model=list[Settlement])
def list_settlements(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[Settlement]:
    return sorted(repos.settlements.list(), key=lambda s: s.created_at, reverse=True)


@router.post("", response_model=Settlement, status_code=201)
def create_settlement(
    body: CreateSettlementRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    if body.payer_id == body.recipient_id:
        raise bad_request("Payer and recipient must be different people.")
    if body.amount <= 0:
        raise bad_request("Settlement amount must be greater than zero.")
    now = datetime.now(UTC)
    settlement = Settlement(
        id=new_id("stl"),
        payer_id=body.payer_id,
        recipient_id=body.recipient_id,
        amount=body.amount,
        note=body.note,
        status=SettlementStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    return repos.settlements.create(settlement)


@router.patch("/{settlement_id}", response_model=Settlement)
def update_settlement(
    settlement_id: str,
    body: UpdateSettlementRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if current_user.role != Role.ADMIN and current_user.id != settlement.payer_id:
        raise forbidden("Only the payer can edit this settlement.")
    if settlement.status != SettlementStatus.PENDING:
        raise bad_request("Only pending settlements can be edited.")
    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if body.amount is not None:
        if body.amount <= 0:
            raise bad_request("Settlement amount must be greater than zero.")
        updates["amount"] = body.amount
    if body.note is not None:
        updates["note"] = body.note
    settlement = settlement.model_copy(update=updates)
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/confirm", response_model=Settlement)
def confirm_settlement(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if current_user.role != Role.ADMIN and current_user.id != settlement.recipient_id:
        raise forbidden("Only the recipient can confirm this settlement.")
    if settlement.status != SettlementStatus.PENDING:
        raise bad_request("This settlement is no longer pending.")
    settlement = settlement.model_copy(
        update={"status": SettlementStatus.CONFIRMED, "updated_at": datetime.now(UTC)}
    )
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/reject", response_model=Settlement)
def reject_settlement(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if current_user.role != Role.ADMIN and current_user.id != settlement.recipient_id:
        raise forbidden("Only the recipient can reject this settlement.")
    if settlement.status != SettlementStatus.PENDING:
        raise bad_request("This settlement is no longer pending.")
    settlement = settlement.model_copy(
        update={"status": SettlementStatus.REJECTED, "updated_at": datetime.now(UTC)}
    )
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/cancel", response_model=Settlement)
def cancel_settlement(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if current_user.role != Role.ADMIN and current_user.id != settlement.payer_id:
        raise forbidden("Only the payer can cancel this settlement.")
    if settlement.status != SettlementStatus.PENDING:
        raise bad_request("This settlement is no longer pending.")
    settlement = settlement.model_copy(
        update={"status": SettlementStatus.CANCELLED, "updated_at": datetime.now(UTC)}
    )
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/request-reversal", response_model=Settlement)
def request_reversal(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    is_participant = current_user.id in (settlement.payer_id, settlement.recipient_id)
    if current_user.role != Role.ADMIN and not is_participant:
        raise forbidden("Only a participant in this settlement can request a reversal.")
    if settlement.status != SettlementStatus.CONFIRMED:
        raise bad_request("Only confirmed settlements can be reversed.")
    settlement = settlement.model_copy(
        update={
            "status": SettlementStatus.REVERSAL_PENDING,
            "reversal_requested_by": current_user.id,
            "updated_at": datetime.now(UTC),
        }
    )
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/confirm-reversal", response_model=Settlement)
def confirm_reversal(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if settlement.status != SettlementStatus.REVERSAL_PENDING:
        raise bad_request("This settlement has no pending reversal.")
    is_participant = current_user.id in (settlement.payer_id, settlement.recipient_id)
    if current_user.role != Role.ADMIN and not is_participant:
        raise forbidden("Only a participant can confirm this reversal.")
    if settlement.reversal_requested_by == current_user.id:
        raise bad_request("Waiting for the other participant to confirm the reversal.")
    settlement = settlement.model_copy(
        update={"status": SettlementStatus.REVERSED, "updated_at": datetime.now(UTC)}
    )
    return repos.settlements.update(settlement)


@router.post("/{settlement_id}/reject-reversal", response_model=Settlement)
def reject_reversal(
    settlement_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Settlement:
    settlement = _get_settlement_or_404(repos, settlement_id)
    if settlement.status != SettlementStatus.REVERSAL_PENDING:
        raise bad_request("This settlement has no pending reversal.")
    is_participant = current_user.id in (settlement.payer_id, settlement.recipient_id)
    if current_user.role != Role.ADMIN and not is_participant:
        raise forbidden("Only a participant can reject this reversal.")
    settlement = settlement.model_copy(
        update={
            "status": SettlementStatus.CONFIRMED,
            "reversal_requested_by": None,
            "updated_at": datetime.now(UTC),
        }
    )
    return repos.settlements.update(settlement)
