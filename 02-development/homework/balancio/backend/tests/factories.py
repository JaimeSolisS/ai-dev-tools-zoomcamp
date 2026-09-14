"""Small helpers for building domain objects in tests without boilerplate."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models.domain import (
    Expense,
    Payer,
    Refund,
    RefundConfirmation,
    Settlement,
    Share,
)

NOW = datetime(2026, 1, 1, tzinfo=None)


def make_expense(
    *,
    id: str = "exp_1",
    group_id: str = "grp_1",
    amount: str = "100.00",
    payers: dict[str, str],
    participant_ids: list[str],
    created_by: str | None = None,
) -> Expense:
    from app.services.balance_calculator import split_equally

    shares = split_equally(Decimal(amount), participant_ids)
    return Expense(
        id=id,
        group_id=group_id,
        title="Test expense",
        amount=Decimal(amount),
        expense_date=date(2026, 1, 1),
        category_id=None,
        tags=[],
        created_by=created_by or next(iter(payers)),
        payers=[Payer(user_id=uid, amount=Decimal(amt)) for uid, amt in payers.items()],
        participant_ids=participant_ids,
        shares=[Share(user_id=uid, amount=amt) for uid, amt in shares.items()],
        created_at=NOW,
        updated_at=NOW,
    )


def make_settlement(
    *,
    id: str = "stl_1",
    payer_id: str,
    recipient_id: str,
    amount: str,
    status: str = "pending",
) -> Settlement:
    return Settlement(
        id=id,
        payer_id=payer_id,
        recipient_id=recipient_id,
        amount=Decimal(amount),
        status=status,  # type: ignore[arg-type]
        created_at=NOW,
        updated_at=NOW,
    )


def make_refund(
    *,
    id: str = "rfd_1",
    group_id: str = "grp_1",
    created_by: str,
    amount: str,
    participant_ids: list[str],
    status: str = "pending",
) -> Refund:
    return Refund(
        id=id,
        group_id=group_id,
        title="Test refund",
        amount=Decimal(amount),
        participant_ids=participant_ids,
        created_by=created_by,
        status=status,  # type: ignore[arg-type]
        confirmations=[RefundConfirmation(user_id=uid, confirmed=False) for uid in participant_ids],
        created_at=NOW,
        updated_at=NOW,
    )
