from datetime import date, datetime, timedelta, timezone
from itertools import product

import pytest
from sqlalchemy import select

from app.models import Assignment, Episode, Quality, Request, RequestStatus, RequestStatusEvent
from tests.conftest import auth_header

S = RequestStatus
FUTURE = (date.today() + timedelta(days=30)).isoformat()

VALID_TRANSITIONS = {
    (S.submitted, S.in_progress),
    (S.in_progress, S.delivered),
    (S.delivered, S.accepted),
    (S.delivered, S.rejected),
    (S.rejected, S.in_progress),
}


# --- helpers ------------------------------------------------------------------


def make_request(db, owner, status=S.submitted, episodes_requested=2, assigned=None):
    """Put a request straight into any status. `assigned` defaults to enough
    episodes to deliver, so only the rule under test can fail."""
    request = Request(
        client_id=owner.id,
        task_name="pick cup",
        episodes_requested=episodes_requested,
        deadline=date.today() + timedelta(days=30),
        status=status,
    )
    db.add(request)
    db.flush()
    for i in range(episodes_requested if assigned is None else assigned):
        episode = Episode(
            episode_id=f"EP-{request.id}-{i}",
            robot_id="arm-01",
            task_name="pick cup",
            recorded_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            duration_seconds=10,
            quality=Quality.good,
        )
        db.add(episode)
        db.flush()
        db.add(Assignment(request_id=request.id, episode_id=episode.id, assigned_by=owner.id))
    db.commit()
    return request


def move(client, user, request_id, to_status):
    return client.post(
        f"/requests/{request_id}/transition", json={"to_status": to_status.value}, headers=auth_header(user)
    )


def events_of(db, request_id):
    db.expire_all()
    return db.scalars(
        select(RequestStatusEvent).where(RequestStatusEvent.request_id == request_id).order_by(RequestStatusEvent.id)
    ).all()


# --- create -------------------------------------------------------------------


def test_client_creates_request_with_creation_event(client, db, client_a):
    body = {"task_name": "  Pick   Cup ", "episodes_requested": 5, "deadline": FUTURE, "notes": "arm only"}
    response = client.post("/requests", json=body, headers=auth_header(client_a))

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "submitted"
    assert created["task_name"] == "pick cup"  # normalised like imported episodes
    assert created["client_id"] == client_a.id
    assert created["assigned_count"] == 0

    [event] = events_of(db, created["id"])
    assert (event.from_status, event.to_status, event.actor_id) == (None, S.submitted, client_a.id)


def test_operator_and_admin_cannot_create_requests(client, operator, admin):
    body = {"task_name": "pick cup", "episodes_requested": 5, "deadline": FUTURE}
    for user in (operator, admin):
        assert client.post("/requests", json=body, headers=auth_header(user)).status_code == 403


@pytest.mark.parametrize(
    "change",
    [
        {"episodes_requested": 0},
        {"episodes_requested": -3},
        {"task_name": "   "},
        {"deadline": "not-a-date"},
        {"deadline": (date.today() - timedelta(days=1)).isoformat()},  # past
    ],
)
def test_create_request_rejects_invalid_input(client, client_a, change):
    body = {"task_name": "pick cup", "episodes_requested": 5, "deadline": FUTURE, **change}
    response = client.post("/requests", json=body, headers=auth_header(client_a))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- read ---------------------------------------------------------------------


def test_clients_list_only_their_own_requests(client, db, client_a, client_b, operator):
    own = make_request(db, client_a)
    make_request(db, client_b)

    ids = [r["id"] for r in client.get("/requests", headers=auth_header(client_a)).json()]
    assert ids == [own.id]

    all_ids = client.get("/requests", headers=auth_header(operator)).json()
    assert len(all_ids) == 2


def test_list_filters_by_status_and_shows_assigned_count(client, db, client_a, operator):
    make_request(db, client_a, S.submitted, assigned=0)
    delivered = make_request(db, client_a, S.delivered, episodes_requested=3)

    response = client.get("/requests?status=delivered", headers=auth_header(operator))
    assert [(r["id"], r["assigned_count"]) for r in response.json()] == [(delivered.id, 3)]


def test_client_gets_404_for_another_clients_request(client, db, client_a, client_b):
    other = make_request(db, client_b)
    response = client.get(f"/requests/{other.id}", headers=auth_header(client_a))
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Request not found"


def test_request_detail_includes_history(client, db, client_a, operator):
    request = make_request(db, client_a)
    move(client, operator, request.id, S.in_progress)

    detail = client.get(f"/requests/{request.id}", headers=auth_header(client_a)).json()
    assert [(e["from_status"], e["to_status"]) for e in detail["events"]] == [("submitted", "in_progress")]


def test_unknown_request_is_404(client, operator):
    assert client.get("/requests/9999", headers=auth_header(operator)).status_code == 404
    assert move(client, operator, 9999, S.in_progress).status_code == 404


# --- transitions: every valid move --------------------------------------------


@pytest.mark.parametrize(
    "from_status, to_status, actor",
    [
        (S.submitted, S.in_progress, "operator"),
        (S.submitted, S.in_progress, "admin"),
        (S.in_progress, S.delivered, "operator"),
        (S.in_progress, S.delivered, "admin"),
        (S.delivered, S.accepted, "client_a"),
        (S.delivered, S.rejected, "client_a"),
        (S.rejected, S.in_progress, "operator"),
        (S.rejected, S.in_progress, "admin"),
    ],
)
def test_valid_transition_updates_status_and_records_event(
    client, db, client_a, operator, admin, from_status, to_status, actor
):
    user = {"operator": operator, "admin": admin, "client_a": client_a}[actor]
    request = make_request(db, client_a, from_status)

    response = move(client, user, request.id, to_status)

    assert response.status_code == 200
    assert response.json()["status"] == to_status.value
    last = events_of(db, request.id)[-1]
    assert (last.from_status, last.to_status, last.actor_id) == (from_status, to_status, user.id)


# --- transitions: every invalid move ------------------------------------------


@pytest.mark.parametrize(
    "from_status, to_status",
    [pair for pair in product(S, S) if pair not in VALID_TRANSITIONS],
)
def test_every_invalid_transition_is_409_and_changes_nothing(client, db, client_a, operator, from_status, to_status):
    # Use the role that WOULD be allowed to move into to_status, so only the
    # "is this a valid move" rule can reject it.
    user = client_a if to_status in (S.accepted, S.rejected) else operator
    request = make_request(db, client_a, from_status)

    response = move(client, user, request.id, to_status)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    db.expire_all()
    assert db.get(Request, request.id).status == from_status
    assert events_of(db, request.id) == []


# --- transitions: wrong role --------------------------------------------------


@pytest.mark.parametrize(
    "from_status, to_status, actor",
    [
        (S.submitted, S.in_progress, "client_a"),
        (S.in_progress, S.delivered, "client_a"),
        (S.rejected, S.in_progress, "client_a"),
        (S.delivered, S.accepted, "operator"),
        (S.delivered, S.rejected, "operator"),
        (S.delivered, S.accepted, "admin"),  # admins don't accept on a client's behalf
        (S.delivered, S.rejected, "admin"),
    ],
)
def test_wrong_role_is_403_and_changes_nothing(client, db, client_a, operator, admin, from_status, to_status, actor):
    user = {"operator": operator, "admin": admin, "client_a": client_a}[actor]
    request = make_request(db, client_a, from_status)

    response = move(client, user, request.id, to_status)

    assert response.status_code == 403
    db.expire_all()
    assert db.get(Request, request.id).status == from_status


def test_other_client_gets_404_not_403_when_accepting(client, db, client_a, client_b):
    request = make_request(db, client_a, S.delivered)
    assert move(client, client_b, request.id, S.accepted).status_code == 404


# --- delivery needs enough assigned episodes ----------------------------------


def test_cannot_deliver_with_too_few_episodes_assigned(client, db, client_a, operator):
    request = make_request(db, client_a, S.in_progress, episodes_requested=3, assigned=2)

    response = move(client, operator, request.id, S.delivered)

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Cannot deliver: 2 of 3 requested episodes assigned"


def test_can_deliver_with_exactly_enough_episodes_assigned(client, db, client_a, operator):
    request = make_request(db, client_a, S.in_progress, episodes_requested=3, assigned=3)
    assert move(client, operator, request.id, S.delivered).status_code == 200


# --- full lifecycle -----------------------------------------------------------


def test_full_lifecycle_with_rework_is_recorded_in_order(client, db, client_a, operator):
    body = {"task_name": "pick cup", "episodes_requested": 1, "deadline": FUTURE}
    request_id = client.post("/requests", json=body, headers=auth_header(client_a)).json()["id"]
    assert move(client, operator, request_id, S.in_progress).status_code == 200

    # Phase 6 adds the assign endpoint; for now put one episode on the request directly.
    episode = Episode(
        episode_id="EP-1",
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        duration_seconds=10,
        quality=Quality.good,
    )
    db.add(episode)
    db.flush()
    db.add(Assignment(request_id=request_id, episode_id=episode.id, assigned_by=operator.id))
    db.commit()

    for user, to_status in [
        (operator, S.delivered),
        (client_a, S.rejected),
        (operator, S.in_progress),
        (operator, S.delivered),
        (client_a, S.accepted),
    ]:
        assert move(client, user, request_id, to_status).status_code == 200

    history = [(e.from_status, e.to_status) for e in events_of(db, request_id)]
    assert history == [
        (None, S.submitted),
        (S.submitted, S.in_progress),
        (S.in_progress, S.delivered),
        (S.delivered, S.rejected),
        (S.rejected, S.in_progress),
        (S.in_progress, S.delivered),
        (S.delivered, S.accepted),
    ]


# --- names for the UI ---------------------------------------------------------


def test_requests_carry_client_name_and_history_carries_actor_name(client, db, client_a, operator):
    request = make_request(db, client_a)
    move(client, operator, request.id, S.in_progress)

    listed = client.get("/requests", headers=auth_header(operator)).json()
    assert listed[0]["client_name"] == client_a.name

    detail = client.get(f"/requests/{request.id}", headers=auth_header(operator)).json()
    assert detail["client_name"] == client_a.name
    assert detail["events"][-1]["actor_name"] == operator.name
