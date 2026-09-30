"""Request and response bodies (pydantic)."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import MAX_PASSWORD_BYTES
from app.models import RequestStatus, Role


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


class RequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_name: str = Field(min_length=1, max_length=200)
    episodes_requested: int = Field(gt=0, le=1_000_000)
    deadline: date
    notes: str | None = Field(default=None, max_length=2000)


class TransitionIn(BaseModel):
    to_status: RequestStatus


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: RequestStatus | None
    to_status: RequestStatus
    actor_id: int
    created_at: datetime


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    task_name: str
    episodes_requested: int
    deadline: date
    notes: str | None
    status: RequestStatus
    assigned_count: int
    created_at: datetime
    updated_at: datetime


class RequestDetail(RequestOut):
    """One request with its full status history (oldest first)."""

    events: list[StatusEventOut]
