"""SQLAlchemy models. The schema itself is created by Alembic migrations."""
import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(str, enum.Enum):
    client = "client"
    operator = "operator"
    admin = "admin"


class Quality(str, enum.Enum):
    good = "good"
    usable = "usable"
    bad = "bad"


class RequestStatus(str, enum.Enum):
    submitted = "submitted"
    in_progress = "in_progress"
    delivered = "delivered"
    accepted = "accepted"
    rejected = "rejected"


# One Postgres enum type shared by requests.status and the two event columns.
request_status_enum = Enum(RequestStatus, name="request_status")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are lowercased in code; the DB refuses anything else, so the
        # UNIQUE constraint is effectively case-insensitive.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"))
    organisation: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    # NULL when the import was run from the CLI rather than by a logged-in user.
    started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    counts: Mapped[dict | None] = mapped_column(JSONB)
    issues: Mapped[list | None] = mapped_column(JSONB)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint("duration_seconds > 0", name="duration_positive"),
        # Analytics: episodes per day per robot.
        Index("ix_episodes_recorded_at_robot_id", "recorded_at", "robot_id"),
        # Episode list filters (task_name + quality).
        Index("ix_episodes_task_name_quality", "task_name", "quality"),
        # Analytics: top tasks by good episodes in a date range.
        Index("ix_episodes_good_recorded_at", "recorded_at", postgresql_where=text("quality = 'good'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(50), unique=True)
    robot_id: Mapped[str] = mapped_column(String(50))
    task_name: Mapped[str] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    operator_name: Mapped[str | None] = mapped_column(String(200))
    quality: Mapped[Quality] = mapped_column(Enum(Quality, name="episode_quality"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("episodes_requested > 0", name="episodes_requested_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_name: Mapped[str] = mapped_column(String(200))
    episodes_requested: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_enum, server_default=RequestStatus.submitted.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RequestStatusEvent(Base):
    """One row per status change, including creation (from_status NULL -> submitted)."""

    __tablename__ = "request_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    from_status: Mapped[RequestStatus | None] = mapped_column(request_status_enum)
    to_status: Mapped[RequestStatus] = mapped_column(request_status_enum)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    # UNIQUE: an episode can belong to at most one request at a time (enforced by the DB).
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), unique=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
