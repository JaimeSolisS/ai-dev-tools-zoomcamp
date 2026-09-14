from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.domain import Expense, Payer


class ExpenseInput(BaseModel):
    group_id: str
    title: str
    amount: Decimal
    expense_date: date
    category_id: str | None = None
    note: str | None = None
    tags: list[str] = []
    payers: list[Payer]
    participant_ids: list[str]


class ExpenseUpdate(BaseModel):
    title: str | None = None
    amount: Decimal | None = None
    expense_date: date | None = None
    category_id: str | None = None
    note: str | None = None
    tags: list[str] | None = None
    payers: list[Payer] | None = None
    participant_ids: list[str] | None = None


class ExpensePage(BaseModel):
    items: list[Expense]
    next_cursor: int | None
    total: int
