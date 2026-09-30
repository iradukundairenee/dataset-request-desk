from datetime import date

from app.models import Assignment, Quality, Request
from tests.conftest import add_episode, auth_header


def get_episodes(client, user, query=""):
    return client.get(f"/episodes{query}", headers=auth_header(user))


def test_list_is_newest_first_with_total(client, db, operator):
    add_episode(db, "EP-1", day=1)
    add_episode(db, "EP-2", day=3)
    add_episode(db, "EP-3", day=2)

    body = get_episodes(client, operator).json()

    assert [e["episode_id"] for e in body["items"]] == ["EP-2", "EP-3", "EP-1"]
    assert body["total"] == 3


def test_filter_by_task_name_is_normalised(client, db, operator):
    add_episode(db, "EP-1", task_name="pick cup")
    add_episode(db, "EP-2", task_name="fold towel")

    body = get_episodes(client, operator, "?task_name=  Pick   CUP").json()
    assert [e["episode_id"] for e in body["items"]] == ["EP-1"]


def test_filter_by_quality_and_robot(client, db, operator):
    add_episode(db, "EP-1", quality=Quality.good, robot_id="arm-01")
    add_episode(db, "EP-2", quality=Quality.bad, robot_id="arm-01")
    add_episode(db, "EP-3", quality=Quality.good, robot_id="mobile-01")

    body = get_episodes(client, operator, "?quality=good&robot_id=arm-01").json()
    assert [e["episode_id"] for e in body["items"]] == ["EP-1"]


def test_unassigned_only_hides_assigned_episodes_and_shows_request(client, db, operator, client_a):
    free = add_episode(db, "EP-FREE", day=1)
    taken = add_episode(db, "EP-TAKEN", day=2)
    request = Request(client_id=client_a.id, task_name="pick cup", episodes_requested=1, deadline=date(2026, 12, 1))
    db.add(request)
    db.flush()
    db.add(Assignment(request_id=request.id, episode_id=taken.id, assigned_by=operator.id))
    db.commit()

    everything = get_episodes(client, operator).json()["items"]
    assert {e["episode_id"]: e["assigned_request_id"] for e in everything} == {
        "EP-TAKEN": request.id,
        "EP-FREE": None,
    }

    free_only = get_episodes(client, operator, "?unassigned_only=true").json()
    assert [e["id"] for e in free_only["items"]] == [free.id]
    assert free_only["total"] == 1


def test_pagination(client, db, operator):
    for day in range(1, 6):
        add_episode(db, f"EP-{day}", day=day)

    page = get_episodes(client, operator, "?limit=2&offset=2").json()

    assert [e["episode_id"] for e in page["items"]] == ["EP-3", "EP-2"]
    assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)


def test_limit_is_capped(client, operator):
    assert get_episodes(client, operator, "?limit=1000").status_code == 422


def test_clients_cannot_browse_episodes(client, client_a):
    assert get_episodes(client, client_a).status_code == 403
