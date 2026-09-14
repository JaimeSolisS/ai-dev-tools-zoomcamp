from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos
from app.errors import forbidden, not_found
from app.models.domain import Comment, TransactionType, User
from app.repositories.bundle import Repositories
from app.schemas.comments import CreateCommentRequest, UpdateCommentRequest
from app.services.identity import new_id

router = APIRouter()

PathTransactionType = Literal["expense", "settlement", "refund"]


def _transaction_participants(repos: Repositories, transaction_type: str, transaction_id: str) -> set[str]:
    if transaction_type == "expense":
        expense = repos.expenses.get(transaction_id)
        if not expense:
            raise not_found("Expense not found.")
        return {expense.created_by, *expense.participant_ids, *(p.user_id for p in expense.payers)}
    if transaction_type == "settlement":
        settlement = repos.settlements.get(transaction_id)
        if not settlement:
            raise not_found("Settlement not found.")
        return {settlement.payer_id, settlement.recipient_id}
    refund = repos.refunds.get(transaction_id)
    if not refund:
        raise not_found("Refund not found.")
    return {refund.created_by, *refund.participant_ids}


@router.get("/{transaction_type}/{transaction_id}/comments", response_model=list[Comment])
def list_comments(
    transaction_type: PathTransactionType,
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[Comment]:
    _transaction_participants(repos, transaction_type, transaction_id)  # 404s if missing
    comments = [
        c
        for c in repos.comments.list()
        if c.transaction_type == transaction_type and c.transaction_id == transaction_id
    ]
    return sorted(comments, key=lambda c: c.created_at)


@router.post("/{transaction_type}/{transaction_id}/comments", response_model=Comment, status_code=201)
def create_comment(
    transaction_type: PathTransactionType,
    transaction_id: str,
    body: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Comment:
    participants = _transaction_participants(repos, transaction_type, transaction_id)
    if current_user.id not in participants:
        raise forbidden("Only people involved in this transaction can comment.")
    now = datetime.now(UTC)
    comment = Comment(
        id=new_id("cmt"),
        transaction_type=TransactionType(transaction_type),
        transaction_id=transaction_id,
        author_id=current_user.id,
        body=body.body.strip(),
        created_at=now,
        updated_at=now,
    )
    return repos.comments.create(comment)


@router.patch("/comments/{comment_id}", response_model=Comment)
def update_comment(
    comment_id: str,
    body: UpdateCommentRequest,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Comment:
    comment = repos.comments.get(comment_id)
    if not comment:
        raise not_found("Comment not found.")
    if comment.author_id != current_user.id:
        raise forbidden("You can only edit your own comments.")
    comment = comment.model_copy(update={"body": body.body.strip(), "updated_at": datetime.now(UTC)})
    return repos.comments.update(comment)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> None:
    comment = repos.comments.get(comment_id)
    if not comment:
        raise not_found("Comment not found.")
    if comment.author_id != current_user.id:
        raise forbidden("You can only delete your own comments.")
    repos.comments.delete(comment_id)
