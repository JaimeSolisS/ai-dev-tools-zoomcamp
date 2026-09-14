from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class GroupStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SettlementStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REVERSAL_PENDING = "reversal_pending"
    REVERSED = "reversed"


class RefundStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class TransactionType(StrEnum):
    EXPENSE = "expense"
    SETTLEMENT = "settlement"
    REFUND = "refund"


class Entity(BaseModel):
    """Base class for anything persisted in the store."""

    model_config = ConfigDict(populate_by_name=True)


class User(Entity):
    id: str
    username: str
    display_name: str
    password_hash: str
    role: Role
    is_active: bool = True
    must_change_password: bool = False
    theme: Theme = Theme.LIGHT
    created_at: datetime
    updated_at: datetime


class Group(Entity):
    id: str
    name: str
    description: str | None = None
    member_ids: list[str] = []
    status: GroupStatus = GroupStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class Category(Entity):
    id: str
    name: str
    group_id: str | None = None
    created_at: datetime


class Payer(BaseModel):
    user_id: str
    amount: Decimal


class Share(BaseModel):
    user_id: str
    amount: Decimal


class Expense(Entity):
    id: str
    group_id: str
    title: str
    amount: Decimal
    expense_date: date
    category_id: str | None = None
    note: str | None = None
    tags: list[str] = []
    created_by: str
    payers: list[Payer]
    participant_ids: list[str]
    shares: list[Share]
    created_at: datetime
    updated_at: datetime


class Settlement(Entity):
    id: str
    payer_id: str
    recipient_id: str
    amount: Decimal
    note: str | None = None
    status: SettlementStatus = SettlementStatus.PENDING
    reversal_requested_by: str | None = None
    created_at: datetime
    updated_at: datetime


class RefundConfirmation(BaseModel):
    user_id: str
    confirmed: bool


class Refund(Entity):
    id: str
    group_id: str
    title: str
    amount: Decimal
    participant_ids: list[str]
    created_by: str
    status: RefundStatus = RefundStatus.PENDING
    confirmations: list[RefundConfirmation]
    created_at: datetime
    updated_at: datetime


class Comment(Entity):
    id: str
    transaction_type: TransactionType
    transaction_id: str
    author_id: str
    body: str
    created_at: datetime
    updated_at: datetime


class PairBalance(BaseModel):
    from_user_id: str
    to_user_id: str
    amount: Decimal


CollectionName = Literal[
    "users",
    "groups",
    "categories",
    "expenses",
    "settlements",
    "refunds",
    "comments",
]
