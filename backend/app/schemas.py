"""Request and response bodies (pydantic)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import MAX_PASSWORD_BYTES
from app.models import Role


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: Role
    organisation: str | None
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=200)
    role: Role
    organisation: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value):
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class UserUpdate(BaseModel):
    """Admin changes to a user. Omitted fields are left as they are."""

    role: Role | None = None
    is_active: bool | None = None
