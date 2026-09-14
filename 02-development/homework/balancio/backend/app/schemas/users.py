from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.domain import Role, Theme, User


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    is_active: bool
    must_change_password: bool
    theme: Theme
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> UserOut:
        return cls.model_validate(user.model_dump(exclude={"password_hash"}))


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    temporary_password: str = Field(min_length=8)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    theme: Theme | None = None


class ResetPasswordRequest(BaseModel):
    new_temporary_password: str = Field(min_length=8)
