from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.users import UserOut


class SetupRequest(BaseModel):
    username: str
    display_name: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
