from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.models.domain import CollectionName
from app.repositories.store import JsonStore


class Repository[T: BaseModel](Protocol):
    """Interface every entity repository conforms to.

    Business logic depends only on this shape, never on `JsonStore` -
    a future `SqlAlchemyExpenseRepository` etc. can implement the same
    methods without any route or service code changing.
    """

    def list(self) -> list[T]: ...
    def get(self, entity_id: str) -> T | None: ...
    def create(self, entity: T) -> T: ...
    def update(self, entity: T) -> T: ...
    def delete(self, entity_id: str) -> None: ...


class JsonRepository[T: BaseModel]:
    """Generic JSON-file-backed implementation of `Repository[T]`."""

    def __init__(self, store: JsonStore, collection: CollectionName, model: type[T]) -> None:
        self._store = store
        self._collection = collection
        self._model = model

    def list(self) -> list[T]:
        return [self._model.model_validate(item) for item in self._store.read(self._collection)]

    def get(self, entity_id: str) -> T | None:
        for entity in self.list():
            if entity.id == entity_id:  # type: ignore[attr-defined]
                return entity
        return None

    def create(self, entity: T) -> T:
        items = self._store.read(self._collection)
        items.append(entity.model_dump(mode="json"))
        self._store.write(self._collection, items)
        return entity

    def update(self, entity: T) -> T:
        items = self._store.read(self._collection)
        entity_id = entity.id  # type: ignore[attr-defined]
        for index, item in enumerate(items):
            if item["id"] == entity_id:
                items[index] = entity.model_dump(mode="json")
                self._store.write(self._collection, items)
                return entity
        raise KeyError(entity_id)

    def delete(self, entity_id: str) -> None:
        items = [item for item in self._store.read(self._collection) if item["id"] != entity_id]
        self._store.write(self._collection, items)
