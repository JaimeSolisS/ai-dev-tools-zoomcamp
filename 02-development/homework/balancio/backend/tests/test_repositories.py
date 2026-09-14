"""Tests for the SQLAlchemy persistence layer itself: does data survive a
restart, and does money keep exact cent precision through the database
round-trip - independent of any HTTP route.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.models.domain import Expense, Payer, Share, User
from app.repositories.bundle import build_repositories
from app.repositories.database import create_engine_for_url, create_session_factory, init_db


def _make_user(user_id: str = "usr_1") -> User:
    now = datetime.now(UTC)
    return User(
        id=user_id,
        username="ana",
        display_name="Ana",
        password_hash="hash",
        role="user",  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
    )


def _make_expense(amount: Decimal, participant_ids: list[str], expense_id: str = "exp_1") -> Expense:
    now = datetime.now(UTC)
    shares = [Share(user_id=uid, amount=amount / len(participant_ids)) for uid in participant_ids]
    return Expense(
        id=expense_id,
        group_id="grp_1",
        title="Dinner",
        amount=amount,
        expense_date=date(2026, 1, 1),
        created_by=participant_ids[0],
        payers=[Payer(user_id=participant_ids[0], amount=amount)],
        participant_ids=participant_ids,
        shares=shares,
        created_at=now,
        updated_at=now,
    )


class TestCrossSessionPersistence:
    def test_data_survives_a_new_session_against_the_same_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "balancio.db"
        engine = create_engine_for_url(f"sqlite:///{db_path}")
        init_db(engine)
        session_factory = create_session_factory(engine)

        with session_factory() as session:
            build_repositories(session).users.create(_make_user())

        # A brand new engine/session pointed at the same file simulates a
        # backend restart - the row must still be there.
        restarted_engine = create_engine_for_url(f"sqlite:///{db_path}")
        with create_session_factory(restarted_engine)() as session:
            user = build_repositories(session).users.get("usr_1")

        assert user is not None
        assert user.username == "ana"

    def test_update_and_delete_are_visible_in_a_later_session(self, tmp_path: Path) -> None:
        db_path = tmp_path / "balancio.db"
        engine = create_engine_for_url(f"sqlite:///{db_path}")
        init_db(engine)
        session_factory = create_session_factory(engine)

        with session_factory() as session:
            build_repositories(session).users.create(_make_user())

        with session_factory() as session:
            repos = build_repositories(session)
            user = repos.users.get("usr_1")
            assert user is not None
            user.display_name = "Ana Updated"
            repos.users.update(user)

        with session_factory() as session:
            repos = build_repositories(session)
            assert repos.users.get("usr_1").display_name == "Ana Updated"  # type: ignore[union-attr]
            repos.users.delete("usr_1")

        with session_factory() as session:
            assert build_repositories(session).users.get("usr_1") is None


class TestDecimalPrecision:
    def test_amount_that_does_not_split_evenly_round_trips_exactly(self, tmp_path: Path) -> None:
        engine = create_engine_for_url(f"sqlite:///{tmp_path / 'balancio.db'}")
        init_db(engine)
        session_factory = create_session_factory(engine)

        amount = Decimal("100.00")
        shares = {
            "usr_a": Decimal("33.34"),
            "usr_b": Decimal("33.33"),
            "usr_c": Decimal("33.33"),
        }
        expense = _make_expense(amount, list(shares))
        expense.shares = [Share(user_id=uid, amount=amt) for uid, amt in shares.items()]

        with session_factory() as session:
            build_repositories(session).expenses.create(expense)

        with session_factory() as session:
            loaded = build_repositories(session).expenses.get("exp_1")

        assert loaded is not None
        assert loaded.amount == amount
        assert isinstance(loaded.amount, Decimal)
        loaded_shares = {s.user_id: s.amount for s in loaded.shares}
        assert loaded_shares == shares
        assert sum(loaded_shares.values(), Decimal("0")) == amount

    def test_amount_survives_many_round_trips_without_float_drift(self, tmp_path: Path) -> None:
        engine = create_engine_for_url(f"sqlite:///{tmp_path / 'balancio.db'}")
        init_db(engine)
        session_factory = create_session_factory(engine)

        # A value with no exact binary-float representation - if amounts were
        # ever stored as float this would drift after repeated round trips.
        amount = Decimal("19.99")
        expense = _make_expense(amount, ["usr_a"])

        with session_factory() as session:
            build_repositories(session).expenses.create(expense)

        for _ in range(5):
            with session_factory() as session:
                repos = build_repositories(session)
                loaded = repos.expenses.get("exp_1")
                assert loaded is not None
                assert loaded.amount == amount
                repos.expenses.update(loaded)
