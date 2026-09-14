from __future__ import annotations

from pydantic import BaseModel

from app.models.domain import PairBalance


class BalanceView(BaseModel):
    net: dict[str, str]
    pairs: list[PairBalance]


class GroupBalances(BaseModel):
    group_id: str
    net: dict[str, str]
    pairs: list[PairBalance]


class GlobalBalances(BaseModel):
    current: BalanceView
    confirmed: BalanceView
