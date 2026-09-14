from __future__ import annotations

from pydantic import BaseModel


class AdminOverview(BaseModel):
    users_count: int
    active_users_count: int
    groups_count: int
    active_groups_count: int
    pending_settlements_count: int
    pending_refunds_count: int
    expenses_count: int
