"""SQLAlchemy table definitions mirroring `app.models.domain`.

Each entity's own fields are real, typed columns so they stay queryable and
indexable in a real database. Small embedded value objects that never need
independent querying (a `Payer`, a `Share`, a `RefundConfirmation`, or a
plain list of ids/tags) are stored as JSON columns, keeping the schema close
to the domain model without a proliferation of child tables the MVP doesn't
need.

Amount columns use `Numeric(asdecimal=True)`, which SQLAlchemy binds/reads
as Python `Decimal` (via string conversion on SQLite) rather than binary
float, so money never loses cent-level precision.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.database import Base

MONEY = Numeric(12, 2, asdecimal=True)


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class GroupORM(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    member_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class CategoryORM(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    group_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ExpenseORM(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    expense_date: Mapped[date] = mapped_column(Date)
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String)
    payers: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    participant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    shares: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class SettlementORM(Base):
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    payer_id: Mapped[str] = mapped_column(String, index=True)
    recipient_id: Mapped[str] = mapped_column(String, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    reversal_requested_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RefundORM(Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    participant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    confirmations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class CommentORM(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    transaction_type: Mapped[str] = mapped_column(String)
    transaction_id: Mapped[str] = mapped_column(String, index=True)
    author_id: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
