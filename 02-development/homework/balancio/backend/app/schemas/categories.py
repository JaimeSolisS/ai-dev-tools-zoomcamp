from __future__ import annotations

from pydantic import BaseModel


class CreateCategoryRequest(BaseModel):
    name: str
    group_id: str | None = None


class UpdateCategoryRequest(BaseModel):
    name: str
