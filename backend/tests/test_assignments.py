import threading
import time
from datetime import date

import pytest
from sqlalchemy import func, select

from app.errors import Conflict
from app.models import Assignment, Quality, Request, RequestStatus, RequestStatusEvent
from app.services import assignments
from tests.conftest import TestSession, add_episode, auth_header

S = RequestStatus


def make_request(db, owner, status=S.in_progress, episodes_requested=2):
    request = Request(
        client_id=owner.id, task_name="pick cup", episodes_requested=episodes_requested,
        deadline=date(2026, 12, 1), status=status,
    )
    db.add(request)
    db.commit()
    return request


def assign(client, user, request_id, episode_ids):
    return client.post(
        f"/requests/{request_id}/assignments", json={"episode_ids": episode_ids}, headers=auth_header(user)
    )


def unassign(client, user, request_id, episode_id):
    return client.delete(f"/requests/{request_id}/assignments/{episode_id}", headers=auth_header(user))


def assignment_count(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Assignment))


# --- assigning ----------------------------------------------------------------


@pytest.mark.parametrize("status", [S.submitted, S.in_progress, S.rejected])
def test_operator_assigns_good_and_usable_episodes(client, db, client_a, operator, status):
    request = make_request(db, client_a, status)
    good = add_episode(db, "EP-1", Quality.good)
    usable = add_episode(db, "EP-2", Quality.usable)

    response = assign(client, operator, request.id, [good.id, usable.id])

    assert response.status_code == 200
    assert [e["episode_id"] for e in response.json()] == ["EP-1", "EP-2"]
    assert all(e["assigned_request_id"] == request.id for e in response.json())


def test_admin_can_assign(client, db, client_a, admin):
    request = make_request(db, client_a)
    episode = add_episode(db, "EP-1")
    assert assign(client, admin, request.id, [episode.id]).status_code == 200


def test_bad_quality_episode_cannot_be_assigned(client, db, client_a, operator):
    request = make_request(db, client_a)
    bad = add_episode(db, "EP-BAD", Quality.bad)

    response = assign(client, operator, request.id, [bad.id])

    assert response.status_code == 409
    assert "EP-BAD" in response.json()["error"]["message"]
    assert assignment_count(db) == 0


def test_episode_already_on_another_request_is_409(client, db, client_a, client_b, operator):
    first = make_request(db, client_a)
    second = make_request(db, client_b)
    episode = add_episode(db, "EP-1")
    assign(client, operator, first.id, [episode.id])

    response = assign(client, operator, second.id, [episode.id])

    assert response.status_code == 409
    assert response.json()["error"]["message"] == f"Already assigned: EP-1 (request {first.id})"


def test_assigning_is_all_or_nothing(client, db, client_a, operator):
    request = make_request(db, client_a)
    good = add_episode(db, "EP-GOOD", Quality.good)
    bad = add_episode(db, "EP-BAD", Quality.bad)

    assert assign(client, operator, request.id, [good.id, bad.id]).status_code == 409
    assert assignment_count(db) == 0  # the good one was not assigned either


def test_unknown_episode_is_404(client, db, client_a, operator):
    request = make_request(db, client_a)
    assert assign(client, operator, request.id, [9999]).status_code == 404


def test_unknown_request_is_404(client, db, operator):
    episode = add_episode(db, "EP-1")
    assert assign(client, operator, 9999, [episode.id]).status_code == 404


def test_repeated_ids_in_one_call_are_assigned_once(client, db, client_a, operator):
    request = make_request(db, client_a)
    episode = add_episode(db, "EP-1")
    assert assign(client, operator, request.id, [episode.id, episode.id]).status_code == 200
    assert assignment_count(db) == 1


@pytest.mark.parametrize("status", [S.delivered, S.accepted])
def test_no_assign_or_unassign_while_delivered_or_accepted(client, db, client_a, operator, status):
    request = make_request(db, client_a, S.in_progress)
    episode = add_episode(db, "EP-1")
    assign(client, operator, request.id, [episode.id])
    request.status = status
    db.commit()
    other = add_episode(db, "EP-2")

    assign_response = assign(client, operator, request.id, [other.id])
    unassign_response = unassign(client, operator, request.id, episode.id)

    assert assign_response.status_code == 409
    assert assign_response.json()["error"]["message"] == f"Episodes cannot be changed while the request is {status.value}"
    assert unassign_response.status_code == 409
    assert assignment_count(db) == 1


def test_clients_cannot_assign_or_unassign(client, db, client_a, operator):
    request = make_request(db, client_a)
    episode = add_episode(db, "EP-1")
    assert assign(client, client_a, request.id, [episode.id]).status_code == 403
    assign(client, operator, request.id, [episode.id])
    assert unassign(client, client_a, request.id, episode.id).status_code == 403


def test_empty_episode_list_is_422(client, db, client_a, operator):
    request = make_request(db, client_a)
    assert assign(client, operator, request.id, []).status_code == 422


# --- unassigning and viewing --------------------------------------------------


def test_unassign_frees_the_episode_for_another_request(client, db, client_a, client_b, operator):
    first = make_request(db, client_a)
    second = make_request(db, client_b)
    episode = add_episode(db, "EP-1")
    assign(client, operator, first.id, [episode.id])

    assert unassign(client, operator, first.id, episode.id).status_code == 204
    assert assign(client, operator, second.id, [episode.id]).status_code == 200


def test_unassign_episode_not_on_this_request_is_404(client, db, client_a, operator):
    request = make_request(db, client_a)
    episode = add_episode(db, "EP-1")
    assert unassign(client, operator, request.id, episode.id).status_code == 404


def test_owner_can_see_assigned_episodes_other_client_cannot(client, db, client_a, client_b, operator):
    request = make_request(db, client_a)
    episode = add_episode(db, "EP-1")
    assign(client, operator, request.id, [episode.id])

    own = client.get(f"/requests/{request.id}/assignments", headers=auth_header(client_a))
    other = client.get(f"/requests/{request.id}/assignments", headers=auth_header(client_b))

    assert [e["episode_id"] for e in own.json()] == ["EP-1"]
    assert other.status_code == 404


def test_assign_then_deliver_end_to_end(client, db, client_a, operator):
    request = make_request(db, client_a, episodes_requested=2)
    ids = [add_episode(db, "EP-1").id, add_episode(db, "EP-2").id]

    move = {"to_status": "delivered"}
    url = f"/requests/{request.id}/transition"
    assign(client, operator, request.id, ids[:1])
    assert client.post(url, json=move, headers=auth_header(operator)).status_code == 409  # 1 of 2
    assign(client, operator, request.id, ids[1:])
    assert client.post(url, json=move, headers=auth_header(operator)).status_code == 200  # 2 of 2


# --- concurrency: the request row lock ----------------------------------------


def test_unassign_waits_for_a_delivery_in_progress_then_is_refused(db, client_a, operator):
    """While one transaction holds the request lock to deliver it, an unassign in
    another transaction must wait, then see the request is delivered and refuse.
    Without the lock, the unassign could land after the count check and leave a
    delivered request short of episodes."""
    request = make_request(db, client_a, episodes_requested=1)
    episode = add_episode(db, "EP-1")
    db.add(Assignment(request_id=request.id, episode_id=episode.id, assigned_by=operator.id))
    db.commit()

    # Transaction A: lock the request, as transition() does, and hold the lock.
    delivering = TestSession()
    locked = delivering.scalar(select(Request).where(Request.id == request.id).with_for_update())

    outcome = {}

    def unassign_in_other_transaction():
        session = TestSession()
        try:
            assignments.unassign(session, operator, request.id, episode.id)
            outcome["result"] = "unassigned"
        except Conflict as error:
            outcome["result"] = error.message
        finally:
            session.close()

    thread = threading.Thread(target=unassign_in_other_transaction)
    try:
        thread.start()
        time.sleep(0.5)
        blocked_while_locked = "result" not in outcome

        # Transaction A finishes the delivery and releases the lock.
        locked.status = S.delivered
        delivering.add(
            RequestStatusEvent(request_id=request.id, from_status=S.in_progress, to_status=S.delivered, actor_id=operator.id)
        )
        delivering.commit()
    finally:
        # Always release the lock, even if something above failed; otherwise the
        # table cleanup after this test would wait on it forever.
        delivering.close()
        thread.join(timeout=5)

    assert blocked_while_locked, "unassign should wait while the request is locked"
    assert outcome["result"] == "Episodes cannot be changed while the request is delivered"
    assert assignment_count(db) == 1
