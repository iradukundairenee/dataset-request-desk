from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.models import Role
from tests.conftest import TEST_PASSWORD, auth_header

INVALID_LOGIN = {"error": {"code": "unauthorized", "message": "Invalid email or password"}}


def login(client, email, password=TEST_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_token(sub, secret=settings.jwt_secret, expires_in=timedelta(hours=1), algorithm="HS256"):
    payload = {"sub": str(sub), "exp": datetime.now(timezone.utc) + expires_in}
    return jwt.encode(payload, secret, algorithm=algorithm)


# --- login ------------------------------------------------------------------


def test_login_returns_token_that_works(client, operator):
    response = login(client, "ops@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "operator"
    assert "password_hash" not in body["user"]

    me = client.get("/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "ops@example.com"


def test_login_email_is_case_insensitive(client, operator):
    assert login(client, "  OPS@Example.com ").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client, operator):
    wrong_password = login(client, "ops@example.com", "wrong-password")
    unknown_email = login(client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == INVALID_LOGIN


def test_deactivated_user_cannot_log_in(client, make_user):
    make_user("gone@example.com", Role.client, is_active=False)
    response = login(client, "gone@example.com")
    assert response.status_code == 401
    assert response.json() == INVALID_LOGIN


def test_password_longer_than_bcrypt_limit_is_rejected_not_500(client, operator):
    assert login(client, "ops@example.com", "x" * 100).status_code == 401


# --- tokens -----------------------------------------------------------------


def test_missing_token_is_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_garbage_token_is_401(client):
    assert client.get("/auth/me", headers=bearer("not-a-jwt")).status_code == 401


def test_expired_token_is_401(client, operator):
    token = make_token(operator.id, expires_in=timedelta(seconds=-1))
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_token_signed_with_another_secret_is_401(client, operator):
    token = make_token(operator.id, secret="someone-elses-secret-0123456789abcdef")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_unsigned_alg_none_token_is_401(client, admin):
    token = make_token(admin.id, secret=None, algorithm="none")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_token_for_user_that_does_not_exist_is_401(client):
    assert client.get("/auth/me", headers=bearer(make_token(9999))).status_code == 401


def test_deactivated_users_existing_token_stops_working(client, admin, operator):
    headers = auth_header(operator)
    assert client.get("/auth/me", headers=headers).status_code == 200

    client.patch(f"/users/{operator.id}", json={"is_active": False}, headers=auth_header(admin))

    assert client.get("/auth/me", headers=headers).status_code == 401


# --- roles ------------------------------------------------------------------


def test_non_admins_get_403_on_admin_endpoints(client, operator, client_a):
    assert client.get("/users", headers=auth_header(operator)).status_code == 403
    response = client.get("/users", headers=auth_header(client_a))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_role_change_applies_to_existing_token_immediately(client, admin, operator):
    headers = auth_header(operator)
    assert client.get("/users", headers=headers).status_code == 403

    client.patch(f"/users/{operator.id}", json={"role": "admin"}, headers=auth_header(admin))

    # Same token, new role: the role is read from the DB, not from the token.
    assert client.get("/users", headers=headers).status_code == 200


# --- logging ----------------------------------------------------------------


def test_log_line_has_user_id_when_authenticated(client, operator, log_lines):
    client.get("/auth/me", headers=auth_header(operator))
    assert log_lines[-1]["user_id"] == operator.id


def test_log_line_has_user_id_on_403_too(client, operator, log_lines):
    client.get("/users", headers=auth_header(operator))
    assert log_lines[-1]["status"] == 403
    assert log_lines[-1]["user_id"] == operator.id
