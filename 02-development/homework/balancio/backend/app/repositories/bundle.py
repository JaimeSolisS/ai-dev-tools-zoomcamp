from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories.entities import (
    CategoryRepository,
    CommentRepository,
    ExpenseRepository,
    GroupRepository,
    RefundRepository,
    SettlementRepository,
    UserRepository,
)


@dataclass
class Repositories:
    users: UserRepository
    groups: GroupRepository
    categories: CategoryRepository
    expenses: ExpenseRepository
    settlements: SettlementRepository
    refunds: RefundRepository
    comments: CommentRepository


def build_repositories(session: Session) -> Repositories:
    return Repositories(
        users=UserRepository(session),
        groups=GroupRepository(session),
        categories=CategoryRepository(session),
        expenses=ExpenseRepository(session),
        settlements=SettlementRepository(session),
        refunds=RefundRepository(session),
        comments=CommentRepository(session),
    )
