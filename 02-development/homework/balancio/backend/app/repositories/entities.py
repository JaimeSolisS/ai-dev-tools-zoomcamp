from __future__ import annotations

from app.models.domain import Category, Comment, Expense, Group, Refund, Settlement, User
from app.repositories.base import JsonRepository
from app.repositories.store import JsonStore


class UserRepository(JsonRepository[User]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "users", User)

    def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.list() if u.username == username), None)

    def any_admin(self) -> bool:
        return any(u.role == "admin" for u in self.list())


class GroupRepository(JsonRepository[Group]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "groups", Group)


class CategoryRepository(JsonRepository[Category]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "categories", Category)


class ExpenseRepository(JsonRepository[Expense]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "expenses", Expense)


class SettlementRepository(JsonRepository[Settlement]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "settlements", Settlement)


class RefundRepository(JsonRepository[Refund]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "refunds", Refund)


class CommentRepository(JsonRepository[Comment]):
    def __init__(self, store: JsonStore) -> None:
        super().__init__(store, "comments", Comment)
