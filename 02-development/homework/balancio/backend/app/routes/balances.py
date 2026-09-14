from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos
from app.models.domain import PairBalance, User
from app.repositories.bundle import Repositories
from app.schemas.balances import BalanceView, GlobalBalances
from app.services.balance_calculator import compute_global_net, net_to_strings, simplify

router = APIRouter(prefix="/balances")


def _global_balances(repos: Repositories) -> GlobalBalances:
    expenses = repos.expenses.list()
    refunds = repos.refunds.list()
    settlements = repos.settlements.list()

    confirmed_net = compute_global_net(
        expenses, refunds, settlements, include_pending_settlements=False
    )
    current_net = compute_global_net(
        expenses, refunds, settlements, include_pending_settlements=True
    )
    return GlobalBalances(
        current=BalanceView(net=net_to_strings(current_net), pairs=simplify(current_net)),
        confirmed=BalanceView(net=net_to_strings(confirmed_net), pairs=simplify(confirmed_net)),
    )


@router.get("/me", response_model=GlobalBalances)
def my_balances(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> GlobalBalances:
    return _global_balances(repos)


@router.get("/global", response_model=GlobalBalances)
def global_balances(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> GlobalBalances:
    return _global_balances(repos)


settlement_suggestions_router = APIRouter()


@settlement_suggestions_router.get("/settlement-suggestions", response_model=list[PairBalance])
def settlement_suggestions(
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[PairBalance]:
    net = compute_global_net(
        repos.expenses.list(),
        repos.refunds.list(),
        repos.settlements.list(),
        include_pending_settlements=True,
    )
    return simplify(net)
