import json

from fastapi import Request
from fastapi.testclient import TestClient


def test_one_json_log_line_per_request(client, log_lines):
    response = client.get("/health")

    requests = [line for line in log_lines if line["event"] == "request"]
    assert len(requests) == 1
    line = requests[0]
    assert line["method"] == "GET"
    assert line["path"] == "/health"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["user_id"] is None
    assert line["request_id"] == response.headers["X-Request-ID"]


def test_log_includes_user_id_when_set_on_request_state(app, client, log_lines):
    # Phase 3's auth dependency will set request.state.user_id; simulate it here.
    @app.get("/_test/whoami")
    def whoami(request: Request):
        request.state.user_id = 42
        return {}

    client.get("/_test/whoami")
    assert log_lines[-1]["user_id"] == 42


def test_query_string_not_logged(client, log_lines):
    client.get("/health?token=secret")
    assert log_lines[-1]["path"] == "/health"
    assert "secret" not in json.dumps(log_lines)


def test_unknown_route_returns_error_json(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_validation_error_returns_error_json(app, client):
    @app.get("/_test/items/{item_id}")
    def get_item(item_id: int):
        return {}

    response = client.get("/_test/items/abc")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "path.item_id" in body["error"]["message"]


def test_unhandled_exception_returns_500_without_leaking(app, log_lines):
    @app.get("/_test/boom")
    def boom():
        raise RuntimeError("database password is hunter2")

    client = TestClient(app)
    response = client.get("/_test/boom")

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "hunter2" not in response.text
    # The traceback goes to the server log, and the request line records the 500.
    assert any(line["event"] == "unhandled_error" for line in log_lines)
    assert log_lines[-1]["status"] == 500
