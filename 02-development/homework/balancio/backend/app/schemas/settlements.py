from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CreateSettlementRequest(BaseModel):
    payer_id: str
    recipient_id: str
    amount: Decimal
    note: str | None = None


class UpdateSettlementRequest(BaseModel):
    amount: Decimal | None = None
    note: str | None = None
