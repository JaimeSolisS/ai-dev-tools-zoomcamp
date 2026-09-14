from __future__ import annotations

from pydantic import BaseModel


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    member_ids: list[str] = []


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class AddMemberRequest(BaseModel):
    user_id: str
