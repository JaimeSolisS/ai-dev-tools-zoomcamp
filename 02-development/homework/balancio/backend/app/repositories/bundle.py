from __future__ import annotations

from dataclasses import dataclass

from app.repositories.entities import (
    CategoryRepository,
    CommentRepository,
    ExpenseRepository,
    GroupRepository,
    RefundRepository,
    SettlementRepository,
    UserRepository,
)
from app.repositories.store import JsonStore


@dataclass
class Repositories:
    users: UserRepository
    groups: GroupRepository
    categories: CategoryRepository
    expenses: ExpenseRepository
    settlements: SettlementRepository
    refunds: RefundRepository
    comments: CommentRepository


def build_repositories(store: JsonStore) -> Repositories:
    return Repositories(
        users=UserRepository(store),
        groups=GroupRepository(store),
        categories=CategoryRepository(store),
        expenses=ExpenseRepository(store),
        settlements=SettlementRepository(store),
        refunds=RefundRepository(store),
        comments=CommentRepository(store),
    )
