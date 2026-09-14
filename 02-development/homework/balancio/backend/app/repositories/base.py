from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.repositories.database import Base


class Repository[T: BaseModel](Protocol):
    """Interface every entity repository conforms to.

    Business logic depends only on this shape, never on SQLAlchemy or any
    other storage detail - a future repository backed by a different
    database can implement the same methods without any route or service
    code changing.
    """

    def list(self) -> list[T]: ...
    def get(self, entity_id: str) -> T | None: ...
    def create(self, entity: T) -> T: ...
    def update(self, entity: T) -> T: ...
    def delete(self, entity_id: str) -> None: ...


class SqlAlchemyRepository[T: BaseModel]:
    """Generic SQLAlchemy-backed implementation of `Repository[T]`.

    Subclasses only need to say which ORM model backs them and how to
    convert between the domain (Pydantic) model and the ORM row - the CRUD
    mechanics are shared.
    """

    orm_model: type[Base]

    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_domain(self, row: Any) -> T:
        raise NotImplementedError

    def _to_orm_values(self, entity: T) -> dict[str, Any]:
        raise NotImplementedError

    def list(self) -> list[T]:
        rows = (
            self._session.query(self.orm_model)
            .order_by(self.orm_model.created_at, self.orm_model.id)  # type: ignore[attr-defined]
            .all()
        )
        return [self._to_domain(row) for row in rows]

    def get(self, entity_id: str) -> T | None:
        row = self._session.get(self.orm_model, entity_id)
        return self._to_domain(row) if row is not None else None

    def create(self, entity: T) -> T:
        row = self.orm_model(**self._to_orm_values(entity))
        self._session.add(row)
        self._session.commit()
        return entity

    def update(self, entity: T) -> T:
        entity_id = entity.id  # type: ignore[attr-defined]
        row = self._session.get(self.orm_model, entity_id)
        if row is None:
            raise KeyError(entity_id)
        for field, value in self._to_orm_values(entity).items():
            setattr(row, field, value)
        self._session.commit()
        return entity

    def delete(self, entity_id: str) -> None:
        row = self._session.get(self.orm_model, entity_id)
        if row is not None:
            self._session.delete(row)
            self._session.commit()
