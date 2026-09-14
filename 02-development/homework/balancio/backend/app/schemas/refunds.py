from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CreateRefundRequest(BaseModel):
    group_id: str
    title: str
    amount: Decimal
    participant_ids: list[str]
