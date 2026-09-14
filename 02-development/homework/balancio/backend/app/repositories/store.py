from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from app.models.domain import CollectionName

COLLECTIONS: tuple[CollectionName, ...] = (
    "users",
    "groups",
    "categories",
    "expenses",
    "settlements",
    "refunds",
    "comments",
)


class JsonStore:
    """Mock database: the whole app state as one JSON file on disk.

    Business logic never touches this class directly - it only sees the
    per-entity repositories in `app.repositories.bundle`, so this can be
    swapped for a real database later without touching route or service code.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._data: dict[str, list[dict[str, Any]]] = {c: [] for c in COLLECTIONS}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            for collection in COLLECTIONS:
                self._data[collection] = raw.get(collection, [])
        else:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.path.parent, prefix=".balancio-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
            os.replace(tmp_path, self.path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def read(self, collection: CollectionName) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._data[collection]]

    def write(self, collection: CollectionName, items: list[dict[str, Any]]) -> None:
        with self._lock:
            self._data[collection] = items
            self._save()
