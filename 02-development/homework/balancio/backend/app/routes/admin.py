from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_repos, require_admin
from app.models.domain import User
from app.repositories.bundle import Repositories
from app.schemas.admin import AdminOverview

router = APIRouter(prefix="/admin")


@router.get("/overview", response_model=AdminOverview)
def overview(
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> AdminOverview:
    users = repos.users.list()
    groups = repos.groups.list()
    settlements = repos.settlements.list()
    refunds = repos.refunds.list()
    return AdminOverview(
        users_count=len(users),
        active_users_count=sum(1 for u in users if u.is_active),
        groups_count=len(groups),
        active_groups_count=sum(1 for g in groups if g.status == "active"),
        pending_settlements_count=sum(
            1 for s in settlements if s.status in ("pending", "reversal_pending")
        ),
        pending_refunds_count=sum(1 for r in refunds if r.status == "pending"),
        expenses_count=len(repos.expenses.list()),
    )
