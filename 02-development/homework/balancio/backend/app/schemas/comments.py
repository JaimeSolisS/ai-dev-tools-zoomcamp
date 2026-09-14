from __future__ import annotations

from pydantic import BaseModel, Field


class CreateCommentRequest(BaseModel):
    body: str = Field(min_length=1)


class UpdateCommentRequest(BaseModel):
    body: str = Field(min_length=1)
