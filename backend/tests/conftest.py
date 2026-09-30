import json
import logging

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, hash_password
from app.config import settings
from app.db import Base, get_db, make_engine
from app.main import create_app
from app.models import Role, User

test_engine = make_engine(settings.test_database_url)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def migrated_test_db():
    """Build the test schema with the real migrations (down to empty, then up),
    so the tests also prove the migrations work."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_tables():
    """Every test starts with empty tables."""
    yield
    table_names = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def app():
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- users and tokens -------------------------------------------------------

TEST_PASSWORD = "password123"
# Hash once: bcrypt is deliberately slow, and every test creates users.
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def auth_header(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def make_user(db):
    def _make(email, role, is_active=True):
        user = User(
            email=email,
            password_hash=TEST_PASSWORD_HASH,
            name=email.split("@")[0],
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def admin(make_user):
    return make_user("admin@example.com", Role.admin)


@pytest.fixture
def operator(make_user):
    return make_user("ops@example.com", Role.operator)


@pytest.fixture
def client_a(make_user):
    return make_user("client-a@example.com", Role.client)


@pytest.fixture
def client_b(make_user):
    return make_user("client-b@example.com", Role.client)


# --- logs -------------------------------------------------------------------


@pytest.fixture
def log_lines():
    """Capture the JSON lines written by the request logger."""
    lines = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(record.getMessage()))

    handler = ListHandler()
    logger = logging.getLogger("app.request")
    logger.addHandler(handler)
    yield lines
    logger.removeHandler(handler)
