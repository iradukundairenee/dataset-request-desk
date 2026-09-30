import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import verify_password
from app.models import Role, User
from cli import load_users, seed_users

SEED_FILE = "/seed/users.json"


def test_seed_file_creates_all_users_with_roles(db):
    created, skipped = seed_users(db, load_users(SEED_FILE))

    assert (created, skipped) == (5, 0)
    admin = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin.role == Role.admin
    assert admin.is_active is True
    client_a = db.scalar(select(User).where(User.email == "client-a@example.com"))
    assert client_a.role == Role.client
    assert client_a.organisation == "Acme Robotics"


def test_seed_is_idempotent(db):
    seed_users(db, load_users(SEED_FILE))
    created, skipped = seed_users(db, load_users(SEED_FILE))

    assert (created, skipped) == (0, 5)
    assert db.scalar(select(func.count()).select_from(User)) == 5


def test_passwords_are_hashed_not_plain_text(db):
    seed_users(db, load_users(SEED_FILE))
    admin = db.scalar(select(User).where(User.email == "admin@example.com"))

    assert admin.password_hash != "admin123"
    assert admin.password_hash.startswith("$2b$")  # bcrypt
    assert verify_password("admin123", admin.password_hash)
    assert not verify_password("wrong", admin.password_hash)


def test_email_is_lowercased_and_treated_case_insensitively(db):
    user = {"email": "  Admin@Example.COM ", "password": "x", "role": "admin", "name": "A"}
    assert seed_users(db, [user]) == (1, 0)
    assert db.scalar(select(User.email)) == "admin@example.com"

    same_email_other_case = {**user, "email": "ADMIN@example.com"}
    assert seed_users(db, [same_email_other_case]) == (0, 1)


def test_database_rejects_non_lowercase_email(db):
    db.add(User(email="Mixed@Example.com", password_hash="x", name="M", role=Role.client))
    with pytest.raises(IntegrityError):
        db.commit()
