from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos
from app.errors import bad_request, forbidden, not_found
from app.models.domain import Expense, Group, GroupStatus, Payer, Role, Share, User
from app.repositories.bundle import Repositories
from app.schemas.expenses import ExpenseInput, ExpensePage, ExpenseUpdate
from app.services.balance_calculator import split_equally
from app.services.identity import new_id

router = APIRouter(prefix="/expenses")


def _assert_group_access(group: Group, user: User) -> None:
    if user.role != Role.ADMIN and user.id not in group.member_ids:
        raise forbidden("You are not a member of this group.")


def _get_group_or_404(repos: Repositories, group_id: str) -> Group:
    group = repos.groups.get(group_id)
    if not group:
        raise not_found("Group not found.")
    return group


def _get_expense_or_404(repos: Repositories, expense_id: str) -> Expense:
    expense = repos.expenses.get(expense_id)
    if not expense:
        raise not_found("Expense not found.")
    return expense


def _visible_group_ids(repos: Repositories, user: User) -> set[str]:
    groups = repos.groups.list()
    if user.role == Role.ADMIN:
        return {g.id for g in groups}
    return {g.id for g in groups if user.id in g.member_ids}


def _validate_payers_and_participants(
    amount: Decimal, payers: list[Payer], participant_ids: list[str], group: Group
) -> None:
    if amount <= 0:
        raise bad_request("Expense amount must be greater than zero.")
    if not payers:
        raise bad_request("Select at least one payer.")
    if not participant_ids:
        raise bad_request("Select at least one participant.")
    if sum(p.amount for p in payers) != amount:
        raise bad_request("Payer amounts must equal the total expense amount.")
    if any(p.user_id not in group.member_ids for p in payers):
        raise bad_request("Payers must be members of the group.")
    if any(uid not in group.member_ids for uid in participant_ids):
        raise bad_request("Participants must be members of the group.")


@router.get("", response_model=ExpensePage)
def list_expenses(
    group_id: str | None = None,
    member_id: str | None = None,
    category_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    tag: str | None = None,
    cursor: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> ExpensePage:
    visible_group_ids = _visible_group_ids(repos, current_user)
    items = [e for e in repos.expenses.list() if e.group_id in visible_group_ids]

    if group_id:
        items = [e for e in items if e.group_id == group_id]
    if member_id:
        items = [
            e
            for e in items
            if member_id in e.participant_ids or any(p.user_id == member_id for p in e.payers)
        ]
    if category_id:
        items = [e for e in items if e.category_id == category_id]
    if date_from:
        items = [e for e in items if e.expense_date >= date_from]
    if date_to:
        items = [e for e in items if e.expense_date <= date_to]
    if tag:
        items = [e for e in items if tag in e.tags]
    if search:
        needle = search.lower()
        items = [
            e
            for e in items
            if needle in e.title.lower() or (e.note and needle in e.note.lower())
        ]

    items.sort(key=lambda e: (e.expense_date, e.created_at), reverse=True)
    total = len(items)
    page = items[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None
    return ExpensePage(items=page, next_cursor=next_cursor, total=total)


@router.post("", response_model=Expense, status_code=201)
def create_expense(
    body: ExpenseInput,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Expense:
    group = _get_group_or_404(repos, body.group_id)
    _assert_group_access(group, current_user)
    if group.status == GroupStatus.ARCHIVED:
        raise bad_request("This group is archived and read-only.")
    if not body.title.strip():
        raise bad_request("Title is required.")
    _validate_payers_and_participants(body.amount, body.payers, body.participant_ids, group)

    shares = split_equally(body.amount, body.participant_ids)
    now = datetime.now(UTC)
    expense = Expense(
        id=new_id("exp"),
        group_id=body.group_id,
        title=body.title.strip(),
        amount=body.amount,
        expense_date=body.expense_date,
        category_id=body.category_id,
        note=(body.note or "").strip() or None,
        tags=body.tags,
        created_by=current_user.id,
        payers=body.payers,
        participant_ids=body.participant_ids,
        shares=[Share(user_id=uid, amount=amt) for uid, amt in shares.items()],
        created_at=now,
        updated_at=now,
    )
    return repos.expenses.create(expense)


@router.get("/{expense_id}", response_model=Expense)
def get_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Expense:
    expense = _get_expense_or_404(repos, expense_id)
    group = _get_group_or_404(repos, expense.group_id)
    _assert_group_access(group, current_user)
    return expense


def _expense_has_related_confirmed_settlement_activity(repos: Repositories) -> bool:
    # The MVP settles debts globally rather than per-expense, so there is no
    # direct expense/settlement link. As a conservative, spec-friendly proxy
    # we block balance-changing edits whenever *any* settlement has already
    # been confirmed, since that confirmation locked in a snapshot of the
    # balances.
    return any(s.status in ("confirmed", "reversal_pending") for s in repos.settlements.list())


@router.patch("/{expense_id}", response_model=Expense)
def update_expense(
    expense_id: str,
    body: ExpenseUpdate,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> Expense:
    expense = _get_expense_or_404(repos, expense_id)
    group = _get_group_or_404(repos, expense.group_id)
    _assert_group_access(group, current_user)
    if group.status == GroupStatus.ARCHIVED:
        raise bad_request("This group is archived and read-only.")
    if current_user.role != Role.ADMIN and current_user.id != expense.created_by:
        raise forbidden("Only the person who created this expense (or the admin) can edit it.")

    provided = body.model_fields_set
    next_amount = body.amount if body.amount is not None else expense.amount
    next_payers = body.payers if body.payers is not None else expense.payers
    next_participants = (
        body.participant_ids if body.participant_ids is not None else expense.participant_ids
    )
    changes_balance = (
        next_amount != expense.amount
        or [p.model_dump() for p in next_payers] != [p.model_dump() for p in expense.payers]
        or sorted(next_participants) != sorted(expense.participant_ids)
    )
    if changes_balance and _expense_has_related_confirmed_settlement_activity(repos):
        raise bad_request(
            "This expense can't be edited because confirmed settlement activity "
            "depends on its current balance."
        )
    if provided & {"payers", "participant_ids", "amount"}:
        _validate_payers_and_participants(next_amount, next_payers, next_participants, group)

    updatable_fields = (
        "title",
        "amount",
        "expense_date",
        "category_id",
        "note",
        "tags",
        "payers",
        "participant_ids",
    )
    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    for field in updatable_fields:
        if field in provided:
            updates[field] = getattr(body, field)
    if "title" in updates:
        updates["title"] = updates["title"].strip()
    if "note" in updates:
        updates["note"] = (updates["note"] or "").strip() or None

    expense = expense.model_copy(update=updates)
    shares = split_equally(expense.amount, expense.participant_ids)
    expense = expense.model_copy(
        update={"shares": [Share(user_id=uid, amount=amt) for uid, amt in shares.items()]}
    )
    return repos.expenses.update(expense)


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> None:
    expense = _get_expense_or_404(repos, expense_id)
    group = _get_group_or_404(repos, expense.group_id)
    _assert_group_access(group, current_user)
    if current_user.role != Role.ADMIN and current_user.id != expense.created_by:
        raise forbidden("Only the person who created this expense (or the admin) can delete it.")
    repos.expenses.delete(expense_id)
    related_comments = [
        c
        for c in repos.comments.list()
        if c.transaction_type == "expense" and c.transaction_id == expense_id
    ]
    for comment in related_comments:
        repos.comments.delete(comment.id)


@router.post("/{expense_id}/duplicate", response_model=ExpenseInput)
def duplicate_expense(
    expense_id: str,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> ExpenseInput:
    expense = _get_expense_or_404(repos, expense_id)
    group = _get_group_or_404(repos, expense.group_id)
    _assert_group_access(group, current_user)
    return ExpenseInput(
        group_id=expense.group_id,
        title=expense.title,
        amount=expense.amount,
        expense_date=date.today(),
        category_id=expense.category_id,
        note=expense.note,
        tags=list(expense.tags),
        payers=[],
        participant_ids=list(expense.participant_ids),
    )
