from tests.conftest import auth_header

NEW_USER = {
    "email": "  New.Client@Example.com ",
    "password": "long-enough-pw",
    "name": "New Client",
    "role": "client",
    "organisation": "Gamma",
}


def test_admin_creates_user_who_can_then_log_in(client, admin):
    response = client.post("/users", json=NEW_USER, headers=auth_header(admin))
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.client@example.com"
    assert body["role"] == "client"
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body

    login = client.post("/auth/login", json={"email": "new.client@example.com", "password": "long-enough-pw"})
    assert login.status_code == 200


def test_duplicate_email_is_409_whatever_the_case(client, admin):
    client.post("/users", json=NEW_USER, headers=auth_header(admin))
    response = client.post(
        "/users", json={**NEW_USER, "email": "NEW.CLIENT@example.com"}, headers=auth_header(admin)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_create_user_validates_input(client, admin):
    headers = auth_header(admin)
    cases = [
        {**NEW_USER, "password": "short"},
        {**NEW_USER, "password": "é" * 40},  # 80 bytes: over bcrypt's 72-byte limit
        {**NEW_USER, "email": "not-an-email"},
        {**NEW_USER, "role": "superuser"},
        {**NEW_USER, "name": "   "},
    ]
    for body in cases:
        response = client.post("/users", json=body, headers=headers)
        assert response.status_code == 422, body
        assert response.json()["error"]["code"] == "validation_error"


def test_list_users_does_not_expose_password_hashes(client, admin, operator):
    response = client.get("/users", headers=auth_header(admin))
    assert response.status_code == 200
    assert [u["email"] for u in response.json()] == ["admin@example.com", "ops@example.com"]
    assert "password_hash" not in response.text


def test_operator_and_client_cannot_create_users(client, operator, client_a):
    for user in (operator, client_a):
        assert client.post("/users", json=NEW_USER, headers=auth_header(user)).status_code == 403


def test_admin_cannot_deactivate_themselves(client, admin):
    response = client.patch(f"/users/{admin.id}", json={"is_active": False}, headers=auth_header(admin))
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "You cannot deactivate your own account"


def test_admin_cannot_remove_their_own_admin_role(client, admin):
    response = client.patch(f"/users/{admin.id}", json={"role": "operator"}, headers=auth_header(admin))
    assert response.status_code == 409
    assert client.get("/auth/me", headers=auth_header(admin)).json()["role"] == "admin"


def test_admin_deactivates_and_reactivates_another_user(client, admin, operator):
    headers = auth_header(admin)
    credentials = {"email": "ops@example.com", "password": "password123"}

    response = client.patch(f"/users/{operator.id}", json={"is_active": False}, headers=headers)
    assert response.json()["is_active"] is False
    assert client.post("/auth/login", json=credentials).status_code == 401

    client.patch(f"/users/{operator.id}", json={"is_active": True}, headers=headers)
    assert client.post("/auth/login", json=credentials).status_code == 200


def test_admin_changes_another_users_role(client, admin, operator):
    response = client.patch(f"/users/{operator.id}", json={"role": "client"}, headers=auth_header(admin))
    assert response.status_code == 200
    assert response.json()["role"] == "client"


def test_update_unknown_user_is_404(client, admin):
    response = client.patch("/users/9999", json={"is_active": False}, headers=auth_header(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
