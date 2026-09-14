from decimal import Decimal

from app.services.balance_calculator import (
    compute_global_net,
    compute_group_net,
    simplify,
    split_equally,
)
from tests.factories import make_expense, make_refund, make_settlement


class TestSplitEqually:
    def test_even_split(self):
        shares = split_equally(Decimal("90.00"), ["a", "b", "c"])
        assert shares == {"a": Decimal("30.00"), "b": Decimal("30.00"), "c": Decimal("30.00")}

    def test_remainder_cents_assigned_deterministically(self):
        # $100 / 3 = 33.333... -> two shares get the extra cent, sorted by id.
        shares = split_equally(Decimal("100.00"), ["c", "a", "b"])
        assert shares == {"a": Decimal("33.34"), "b": Decimal("33.33"), "c": Decimal("33.33")}
        assert sum(shares.values()) == Decimal("100.00")

    def test_remainder_assignment_is_stable_across_calls(self):
        first = split_equally(Decimal("10.00"), ["x", "y", "z"])
        second = split_equally(Decimal("10.00"), ["z", "y", "x"])
        assert first == second

    def test_single_participant_gets_full_amount(self):
        shares = split_equally(Decimal("50.00"), ["solo"])
        assert shares == {"solo": Decimal("50.00")}

    def test_empty_participants_returns_empty(self):
        assert split_equally(Decimal("10.00"), []) == {}


class TestExpenseNetting:
    def test_single_payer_all_participate_nets_to_zero(self):
        expense = make_expense(amount="90.00", payers={"a": "90.00"}, participant_ids=["a", "b", "c"])
        net = compute_group_net("grp_1", [expense], [])
        assert net == {"a": Decimal("60.00"), "b": Decimal("-30.00"), "c": Decimal("-30.00")}
        assert sum(net.values()) == Decimal("0.00")

    def test_multiple_payers(self):
        expense = make_expense(
            amount="100.00",
            payers={"a": "60.00", "b": "40.00"},
            participant_ids=["a", "b"],
        )
        net = compute_group_net("grp_1", [expense], [])
        assert net == {"a": Decimal("10.00"), "b": Decimal("-10.00")}

    def test_payer_not_a_participant(self):
        # Jaime pays $300 for Ana and Carlos while owing none of it himself.
        expense = make_expense(
            amount="300.00",
            payers={"jaime": "300.00"},
            participant_ids=["ana", "carlos"],
            created_by="jaime",
        )
        net = compute_group_net("grp_1", [expense], [])
        assert net["jaime"] == Decimal("300.00")
        assert net["ana"] == Decimal("-150.00")
        assert net["carlos"] == Decimal("-150.00")
        assert sum(net.values()) == Decimal("0.00")

    def test_only_expenses_in_the_requested_group_count(self):
        e1 = make_expense(
            id="e1", group_id="grp_1", amount="10.00", payers={"a": "10.00"}, participant_ids=["a", "b"]
        )
        e2 = make_expense(
            id="e2", group_id="grp_2", amount="999.00", payers={"a": "999.00"}, participant_ids=["a", "b"]
        )
        net = compute_group_net("grp_1", [e1, e2], [])
        assert net["a"] == Decimal("5.00")
        assert net["b"] == Decimal("-5.00")


class TestRefunds:
    def test_pending_refund_does_not_affect_balances(self):
        refund = make_refund(created_by="a", amount="40.00", participant_ids=["a", "b"], status="pending")
        net = compute_group_net("grp_1", [], [refund])
        assert net == {}

    def test_confirmed_refund_affects_balances_like_an_expense(self):
        refund = make_refund(created_by="a", amount="40.00", participant_ids=["a", "b"], status="confirmed")
        net = compute_group_net("grp_1", [], [refund])
        assert net == {"a": Decimal("20.00"), "b": Decimal("-20.00")}


class TestGlobalNetting:
    def test_nets_across_groups(self):
        # Spec example: Home -> you owe Ana $300, Trip -> Ana owes you $150,
        # global -> you owe Ana $150.
        home = make_expense(
            id="home",
            group_id="home",
            amount="600.00",
            payers={"ana": "600.00"},
            participant_ids=["ana", "jaime"],
        )
        trip = make_expense(
            id="trip",
            group_id="trip",
            amount="300.00",
            payers={"jaime": "300.00"},
            participant_ids=["jaime", "ana"],
        )
        net = compute_global_net([home, trip], [], [], include_pending_settlements=False)
        assert net == {"ana": Decimal("150.00"), "jaime": Decimal("-150.00")}

    def test_confirmed_settlement_reduces_debt(self):
        expense = make_expense(amount="100.00", payers={"a": "100.00"}, participant_ids=["a", "b"])
        settlement = make_settlement(payer_id="b", recipient_id="a", amount="50.00", status="confirmed")
        net = compute_global_net([expense], [], [settlement], include_pending_settlements=False)
        assert net == {"a": Decimal("0.00"), "b": Decimal("0.00")}

    def test_pending_settlement_only_affects_current_balance(self):
        expense = make_expense(amount="100.00", payers={"a": "100.00"}, participant_ids=["a", "b"])
        settlement = make_settlement(payer_id="b", recipient_id="a", amount="50.00", status="pending")

        confirmed = compute_global_net([expense], [], [settlement], include_pending_settlements=False)
        current = compute_global_net([expense], [], [settlement], include_pending_settlements=True)

        assert confirmed == {"a": Decimal("50.00"), "b": Decimal("-50.00")}
        assert current == {"a": Decimal("0.00"), "b": Decimal("0.00")}

    def test_rejected_and_cancelled_settlements_have_no_effect(self):
        expense = make_expense(amount="100.00", payers={"a": "100.00"}, participant_ids=["a", "b"])
        rejected = make_settlement(payer_id="b", recipient_id="a", amount="50.00", status="rejected")
        cancelled = make_settlement(
            id="stl_2", payer_id="b", recipient_id="a", amount="50.00", status="cancelled"
        )
        net = compute_global_net([expense], [], [rejected, cancelled], include_pending_settlements=True)
        assert net == {"a": Decimal("50.00"), "b": Decimal("-50.00")}

    def test_reversed_settlement_has_no_effect_but_reversal_pending_still_counts(self):
        expense = make_expense(amount="100.00", payers={"a": "100.00"}, participant_ids=["a", "b"])
        reversed_settlement = make_settlement(
            payer_id="b", recipient_id="a", amount="50.00", status="reversed"
        )
        pending_reversal = make_settlement(
            id="stl_2", payer_id="b", recipient_id="a", amount="50.00", status="reversal_pending"
        )

        net_reversed = compute_global_net(
            [expense], [], [reversed_settlement], include_pending_settlements=False
        )
        net_reversal_pending = compute_global_net(
            [expense], [], [pending_reversal], include_pending_settlements=False
        )

        # A reversed settlement is fully excluded, leaving just the expense
        # net (a and b split $100 evenly, a paid it all).
        assert net_reversed == {"a": Decimal("50.00"), "b": Decimal("-50.00")}
        # A still-pending reversal has not taken effect yet, so the
        # settlement keeps counting as confirmed.
        assert net_reversal_pending == {"a": Decimal("0.00"), "b": Decimal("0.00")}

    def test_overpayment_produces_a_credit(self):
        # a and b split $50 evenly (a paid it, so a is owed $25 from b).
        # b then pays a $70, well past the $25 owed, ending up in credit.
        expense = make_expense(amount="50.00", payers={"a": "50.00"}, participant_ids=["a", "b"])
        settlement = make_settlement(payer_id="b", recipient_id="a", amount="70.00", status="confirmed")
        net = compute_global_net([expense], [], [settlement], include_pending_settlements=False)
        assert net == {"a": Decimal("-45.00"), "b": Decimal("45.00")}


class TestSimplify:
    def test_two_person_debt(self):
        pairs = simplify({"a": Decimal("50.00"), "b": Decimal("-50.00")})
        assert len(pairs) == 1
        assert pairs[0].from_user_id == "b"
        assert pairs[0].to_user_id == "a"
        assert pairs[0].amount == Decimal("50.00")

    def test_settled_balances_produce_no_suggestions(self):
        assert simplify({"a": Decimal("0.00"), "b": Decimal("0.00")}) == []

    def test_chain_is_simplified_to_a_single_transfer(self):
        # Spec example: Ana -> Jaime $20, Jaime -> Carlos $20 simplifies to
        # Ana -> Carlos $20 (Jaime's net position is zero).
        net = {"ana": Decimal("-20.00"), "jaime": Decimal("0.00"), "carlos": Decimal("20.00")}
        pairs = simplify(net)
        assert len(pairs) == 1
        assert pairs[0].from_user_id == "ana"
        assert pairs[0].to_user_id == "carlos"
        assert pairs[0].amount == Decimal("20.00")

    def test_minimizes_number_of_transfers_for_multiple_creditors_and_debtors(self):
        net = {
            "jaime": Decimal("-150.00"),
            "ana": Decimal("130.00"),
            "carlos": Decimal("50.00"),
            "sofia": Decimal("-30.00"),
        }
        pairs = simplify(net)
        assert len(pairs) == 3
        total_from_jaime = sum(p.amount for p in pairs if p.from_user_id == "jaime")
        total_from_sofia = sum(p.amount for p in pairs if p.from_user_id == "sofia")
        assert total_from_jaime == Decimal("150.00")
        assert total_from_sofia == Decimal("30.00")
        assert sum(p.amount for p in pairs if p.to_user_id == "ana") == Decimal("130.00")
        assert sum(p.amount for p in pairs if p.to_user_id == "carlos") == Decimal("50.00")

    def test_ties_are_broken_deterministically_by_user_id(self):
        net = {"b": Decimal("10.00"), "a": Decimal("10.00"), "d": Decimal("-10.00"), "c": Decimal("-10.00")}
        first = simplify(net)
        second = simplify(dict(reversed(list(net.items()))))
        assert first == second
