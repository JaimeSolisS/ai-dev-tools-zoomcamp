from __future__ import annotations

from typing import Any

from app.models.domain import (
    Category,
    Comment,
    Expense,
    Group,
    Payer,
    Refund,
    RefundConfirmation,
    Settlement,
    Share,
    User,
)
from app.repositories.base import SqlAlchemyRepository
from app.repositories.orm import (
    CategoryORM,
    CommentORM,
    ExpenseORM,
    GroupORM,
    RefundORM,
    SettlementORM,
    UserORM,
)


class UserRepository(SqlAlchemyRepository[User]):
    orm_model = UserORM

    def _to_domain(self, row: UserORM) -> User:
        return User(
            id=row.id,
            username=row.username,
            display_name=row.display_name,
            password_hash=row.password_hash,
            role=row.role,  # type: ignore[arg-type]
            is_active=row.is_active,
            must_change_password=row.must_change_password,
            theme=row.theme,  # type: ignore[arg-type]
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: User) -> dict[str, Any]:
        return entity.model_dump()

    def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.list() if u.username == username), None)

    def any_admin(self) -> bool:
        return any(u.role == "admin" for u in self.list())


class GroupRepository(SqlAlchemyRepository[Group]):
    orm_model = GroupORM

    def _to_domain(self, row: GroupORM) -> Group:
        return Group(
            id=row.id,
            name=row.name,
            description=row.description,
            member_ids=list(row.member_ids),
            status=row.status,  # type: ignore[arg-type]
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: Group) -> dict[str, Any]:
        return entity.model_dump()


class CategoryRepository(SqlAlchemyRepository[Category]):
    orm_model = CategoryORM

    def _to_domain(self, row: CategoryORM) -> Category:
        return Category(id=row.id, name=row.name, group_id=row.group_id, created_at=row.created_at)

    def _to_orm_values(self, entity: Category) -> dict[str, Any]:
        return entity.model_dump()


class ExpenseRepository(SqlAlchemyRepository[Expense]):
    orm_model = ExpenseORM

    def _to_domain(self, row: ExpenseORM) -> Expense:
        return Expense(
            id=row.id,
            group_id=row.group_id,
            title=row.title,
            amount=row.amount,
            expense_date=row.expense_date,
            category_id=row.category_id,
            note=row.note,
            tags=list(row.tags),
            created_by=row.created_by,
            payers=[Payer.model_validate(p) for p in row.payers],
            participant_ids=list(row.participant_ids),
            shares=[Share.model_validate(s) for s in row.shares],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: Expense) -> dict[str, Any]:
        values = entity.model_dump()
        # `Payer`/`Share` amounts are `Decimal`, which the JSON column can't
        # serialize directly - dump those two nested fields JSON-safe while
        # leaving `amount`/`expense_date`/timestamps as native Python values
        # for their own typed (Numeric/Date/DateTime) columns.
        values["payers"] = [p.model_dump(mode="json") for p in entity.payers]
        values["shares"] = [s.model_dump(mode="json") for s in entity.shares]
        return values


class SettlementRepository(SqlAlchemyRepository[Settlement]):
    orm_model = SettlementORM

    def _to_domain(self, row: SettlementORM) -> Settlement:
        return Settlement(
            id=row.id,
            payer_id=row.payer_id,
            recipient_id=row.recipient_id,
            amount=row.amount,
            note=row.note,
            status=row.status,  # type: ignore[arg-type]
            reversal_requested_by=row.reversal_requested_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: Settlement) -> dict[str, Any]:
        return entity.model_dump()


class RefundRepository(SqlAlchemyRepository[Refund]):
    orm_model = RefundORM

    def _to_domain(self, row: RefundORM) -> Refund:
        return Refund(
            id=row.id,
            group_id=row.group_id,
            title=row.title,
            amount=row.amount,
            participant_ids=list(row.participant_ids),
            created_by=row.created_by,
            status=row.status,  # type: ignore[arg-type]
            confirmations=[RefundConfirmation.model_validate(c) for c in row.confirmations],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: Refund) -> dict[str, Any]:
        values = entity.model_dump()
        values["confirmations"] = [c.model_dump(mode="json") for c in entity.confirmations]
        return values


class CommentRepository(SqlAlchemyRepository[Comment]):
    orm_model = CommentORM

    def _to_domain(self, row: CommentORM) -> Comment:
        return Comment(
            id=row.id,
            transaction_type=row.transaction_type,  # type: ignore[arg-type]
            transaction_id=row.transaction_id,
            author_id=row.author_id,
            body=row.body,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_orm_values(self, entity: Comment) -> dict[str, Any]:
        return entity.model_dump()
