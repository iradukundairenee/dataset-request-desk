"""The database itself enforces the rules that must never be broken,
even if a bug in the service layer lets a bad write through."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Assignment, Episode, Quality, Request, Role, User


def make_user(db, email="ops@example.com", role=Role.operator):
    user = User(email=email, password_hash="x", name="U", role=role)
    db.add(user)
    db.flush()
    return user


def make_episode(db, episode_id="EP-1"):
    episode = Episode(
        episode_id=episode_id,
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        duration_seconds=10,
        quality=Quality.good,
    )
    db.add(episode)
    db.flush()
    return episode


def make_request(db, client):
    request = Request(client_id=client.id, task_name="pick cup", episodes_requested=1, deadline=date(2026, 12, 1))
    db.add(request)
    db.flush()
    return request


def test_episode_can_only_be_assigned_to_one_request(db):
    ops = make_user(db)
    client = make_user(db, "c@example.com", Role.client)
    episode = make_episode(db)
    first, second = make_request(db, client), make_request(db, client)

    db.add(Assignment(request_id=first.id, episode_id=episode.id, assigned_by=ops.id))
    db.flush()
    db.add(Assignment(request_id=second.id, episode_id=episode.id, assigned_by=ops.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_episode_id_is_unique(db):
    make_episode(db, "EP-1")
    with pytest.raises(IntegrityError):
        make_episode(db, "EP-1")


def test_episodes_requested_must_be_positive(db):
    client = make_user(db, "c@example.com", Role.client)
    db.add(Request(client_id=client.id, task_name="t", episodes_requested=0, deadline=date(2026, 12, 1)))
    with pytest.raises(IntegrityError):
        db.flush()


def test_new_request_defaults_to_submitted(db):
    client = make_user(db, "c@example.com", Role.client)
    request = make_request(db, client)
    db.refresh(request)
    assert request.status.value == "submitted"
