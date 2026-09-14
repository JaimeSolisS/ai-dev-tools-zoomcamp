"""The balance engine.

Positive net = the user is owed money (creditor). Negative net = the user
owes money (debtor). Every calculation happens in integer cents so results
always reconcile to zero, and every ordering decision (remainder-cent
assignment, settlement simplification) is deterministic so repeated runs
produce identical output.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models.domain import Expense, PairBalance, Refund, Settlement

CENT = Decimal("0.01")


def to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def split_equally(total: Decimal, participant_ids: list[str]) -> dict[str, Decimal]:
    """Splits `total` equally among `participant_ids`, assigning remainder
    cents deterministically (sorted by user id) so shares always sum exactly
    to `total`."""
    if not participant_ids:
        return {}
    total_cents = to_cents(total)
    n = len(participant_ids)
    base = total_cents // n
    remainder = total_cents - base * n
    sorted_ids = sorted(participant_ids)
    result: dict[str, Decimal] = {}
    for index, user_id in enumerate(sorted_ids):
        cents = base + (1 if index < remainder else 0)
        result[user_id] = from_cents(cents)
    return result


def _apply_expense(net: dict[str, int], expense: Expense) -> None:
    for payer in expense.payers:
        net[payer.user_id] = net.get(payer.user_id, 0) + to_cents(payer.amount)
    for share in expense.shares:
        net[share.user_id] = net.get(share.user_id, 0) - to_cents(share.amount)


def _apply_confirmed_refund(net: dict[str, int], refund: Refund) -> None:
    net[refund.created_by] = net.get(refund.created_by, 0) + to_cents(refund.amount)
    shares = split_equally(refund.amount, refund.participant_ids)
    for user_id, amount in shares.items():
        net[user_id] = net.get(user_id, 0) - to_cents(amount)


def _apply_settlement(net: dict[str, int], settlement: Settlement) -> None:
    cents = to_cents(settlement.amount)
    net[settlement.payer_id] = net.get(settlement.payer_id, 0) + cents
    net[settlement.recipient_id] = net.get(settlement.recipient_id, 0) - cents


def compute_group_net(
    group_id: str, expenses: list[Expense], refunds: list[Refund]
) -> dict[str, Decimal]:
    net: dict[str, int] = {}
    for expense in expenses:
        if expense.group_id == group_id:
            _apply_expense(net, expense)
    for refund in refunds:
        if refund.group_id == group_id and refund.status == "confirmed":
            _apply_confirmed_refund(net, refund)
    return {user_id: from_cents(cents) for user_id, cents in net.items()}


def compute_global_net(
    expenses: list[Expense],
    refunds: list[Refund],
    settlements: list[Settlement],
    *,
    include_pending_settlements: bool,
) -> dict[str, Decimal]:
    net: dict[str, int] = {}
    for expense in expenses:
        _apply_expense(net, expense)
    for refund in refunds:
        if refund.status == "confirmed":
            _apply_confirmed_refund(net, refund)
    for settlement in settlements:
        effective = settlement.status in ("confirmed", "reversal_pending") or (
            include_pending_settlements and settlement.status == "pending"
        )
        if effective:
            _apply_settlement(net, settlement)
    return {user_id: from_cents(cents) for user_id, cents in net.items()}


def simplify(net: dict[str, Decimal]) -> list[PairBalance]:
    """Greedy debt simplification: matches the largest creditor against the
    largest debtor repeatedly. Ties are broken by user id for determinism."""
    cents_net = {user_id: to_cents(amount) for user_id, amount in net.items()}
    creditors = sorted(
        ((user_id, amount) for user_id, amount in cents_net.items() if amount > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    debtors = sorted(
        ((user_id, -amount) for user_id, amount in cents_net.items() if amount < 0),
        key=lambda pair: (-pair[1], pair[0]),
    )

    creditor_ids = [user_id for user_id, _ in creditors]
    creditor_amounts = [amount for _, amount in creditors]
    debtor_ids = [user_id for user_id, _ in debtors]
    debtor_amounts = [amount for _, amount in debtors]

    results: list[PairBalance] = []
    i = j = 0
    while i < len(creditor_ids) and j < len(debtor_ids):
        amount = min(creditor_amounts[i], debtor_amounts[j])
        if amount > 0:
            results.append(
                PairBalance(
                    from_user_id=debtor_ids[j], to_user_id=creditor_ids[i], amount=from_cents(amount)
                )
            )
        creditor_amounts[i] -= amount
        debtor_amounts[j] -= amount
        if creditor_amounts[i] == 0:
            i += 1
        if debtor_amounts[j] == 0:
            j += 1
    return results


def net_to_strings(net: dict[str, Decimal]) -> dict[str, str]:
    return {user_id: str(amount) for user_id, amount in net.items()}
