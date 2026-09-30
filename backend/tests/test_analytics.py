"""Analytics on small hand-made data, where every expected number is known."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models import Episode, Quality, Request, RequestStatus, RequestStatusEvent
from app.services.analytics import get_analytics as run_analytics
from tests.conftest import auth_header

S = RequestStatus
UTC = timezone.utc
PLUS_2 = timezone(timedelta(hours=2))  # Kigali


def episode(db, episode_id, recorded_at, robot_id="arm-01", task_name="pick cup", quality=Quality.good):
    db.add(
        Episode(
            episode_id=episode_id,
            robot_id=robot_id,
            task_name=task_name,
            recorded_at=recorded_at,
            duration_seconds=30,
            quality=quality,
        )
    )
    db.commit()


def request_with_history(db, owner, history, created_at=None):
    """history: list of (to_status, datetime). The request ends in the last status."""
    request = Request(
        client_id=owner.id,
        task_name="pick cup",
        episodes_requested=1,
        deadline=date(2026, 12, 1),
        status=history[-1][0],
        created_at=created_at or history[0][1],
    )
    db.add(request)
    db.flush()
    previous = None
    for to_status, at in history:
        db.add(
            RequestStatusEvent(
                request_id=request.id, from_status=previous, to_status=to_status, actor_id=owner.id, created_at=at
            )
        )
        previous = to_status
    db.commit()
    return request


def delivered_after(db, owner, submitted_at, hours):
    return request_with_history(
        db,
        owner,
        [
            (S.submitted, submitted_at),
            (S.in_progress, submitted_at + timedelta(minutes=1)),
            (S.delivered, submitted_at + timedelta(hours=hours)),
        ],
    )


def get_analytics(client, user, date_from, date_to):
    return client.get(f"/analytics?from={date_from}&to={date_to}", headers=auth_header(user))


# --- episodes per day per robot -----------------------------------------------


def test_episodes_per_day_per_robot_with_inclusive_utc_range(client, db, operator):
    episode(db, "EP-1", datetime(2026, 8, 1, 10, 0, tzinfo=UTC))
    episode(db, "EP-2", datetime(2026, 8, 1, 23, 30, tzinfo=UTC))
    # 01:00 in Kigali on 2 Aug is 23:00 UTC on 1 Aug: counted on 1 Aug.
    episode(db, "EP-3", datetime(2026, 8, 2, 1, 0, tzinfo=PLUS_2), robot_id="arm-02", quality=Quality.usable)
    episode(db, "EP-4", datetime(2026, 8, 2, 0, 0, tzinfo=UTC))  # first second of 'to' day: included
    episode(db, "EP-OUT-1", datetime(2026, 7, 31, 23, 59, tzinfo=UTC))  # before 'from'
    episode(db, "EP-OUT-2", datetime(2026, 8, 3, 0, 0, tzinfo=UTC))  # after 'to'

    body = get_analytics(client, operator, "2026-08-01", "2026-08-02").json()

    assert body["episodes_per_day_per_robot"] == [
        {"day": "2026-08-01", "robot_id": "arm-01", "episodes": 2},
        {"day": "2026-08-01", "robot_id": "arm-02", "episodes": 1},
        {"day": "2026-08-02", "robot_id": "arm-01", "episodes": 1},
    ]


# --- requests by status -------------------------------------------------------


def test_requests_by_status_counts_requests_created_in_range(client, db, operator, client_a):
    in_range = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    request_with_history(db, client_a, [(S.submitted, in_range)])
    request_with_history(db, client_a, [(S.submitted, in_range)])
    delivered_after(db, client_a, in_range, hours=5)
    request_with_history(db, client_a, [(S.submitted, datetime(2026, 7, 1, tzinfo=UTC))])  # created before range

    body = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()

    assert body["requests_by_status"] == {
        "submitted": 2,
        "in_progress": 0,
        "delivered": 1,
        "accepted": 0,
        "rejected": 0,
    }


# --- median submitted -> delivered --------------------------------------------


def test_median_with_odd_number_of_requests(client, db, operator, client_a):
    start = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    for hours in (2, 4, 10):
        delivered_after(db, client_a, start, hours)

    median = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()["submitted_to_delivered"]

    assert median == {"median_seconds": 4 * 3600, "median_hours": 4.0, "delivered_requests": 3}


def test_median_with_even_number_is_the_average_of_the_middle_two(client, db, operator, client_a):
    start = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    for hours in (2, 4, 6, 10):
        delivered_after(db, client_a, start, hours)

    median = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()["submitted_to_delivered"]

    assert median["median_hours"] == 5.0


def test_median_uses_first_delivery_when_request_was_reworked(client, db, operator, client_a):
    t0 = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    request_with_history(
        db,
        client_a,
        [
            (S.submitted, t0),
            (S.in_progress, t0 + timedelta(minutes=1)),
            (S.delivered, t0 + timedelta(hours=1)),  # first delivery: this one counts
            (S.rejected, t0 + timedelta(hours=2)),
            (S.in_progress, t0 + timedelta(hours=3)),
            (S.delivered, t0 + timedelta(hours=20)),
        ],
    )

    median = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()["submitted_to_delivered"]

    assert median == {"median_seconds": 3600, "median_hours": 1.0, "delivered_requests": 1}


def test_median_ignores_undelivered_and_out_of_range_deliveries(client, db, operator, client_a):
    delivered_after(db, client_a, datetime(2026, 8, 1, tzinfo=UTC), hours=3)  # counts
    delivered_after(db, client_a, datetime(2026, 6, 1, tzinfo=UTC), hours=3)  # delivered in June
    request_with_history(db, client_a, [(S.submitted, datetime(2026, 8, 2, tzinfo=UTC))])  # never delivered

    median = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()["submitted_to_delivered"]

    assert median["delivered_requests"] == 1


# --- top tasks ----------------------------------------------------------------


def test_top_five_tasks_counts_only_good_episodes_and_breaks_ties_by_name(client, db, operator):
    day = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    good_counts = {"wipe table": 4, "pick cup": 3, "fold towel": 2, "open drawer": 2, "pour water": 1, "stack blocks": 1}
    n = 0
    for task, count in good_counts.items():
        for _ in range(count):
            n += 1
            episode(db, f"EP-{n}", day, task_name=task)
    # Not good, or outside the range: must not count.
    for i, quality in enumerate([Quality.usable, Quality.bad, Quality.usable, Quality.bad, Quality.usable]):
        episode(db, f"EP-NG-{i}", day, task_name="place cup on shelf", quality=quality)
    episode(db, "EP-OLD", datetime(2026, 1, 1, tzinfo=UTC), task_name="place cup on shelf")

    body = get_analytics(client, operator, "2026-08-01", "2026-08-31").json()

    assert body["top_tasks_by_good_episodes"] == [
        {"task_name": "wipe table", "good_episodes": 4},
        {"task_name": "pick cup", "good_episodes": 3},
        {"task_name": "fold towel", "good_episodes": 2},
        {"task_name": "open drawer", "good_episodes": 2},
        {"task_name": "pour water", "good_episodes": 1},  # beats "stack blocks" alphabetically
    ]


# --- empty range, validation, access ------------------------------------------


def test_empty_range_returns_zeros_and_nulls(client, operator):
    body = get_analytics(client, operator, "2026-08-01", "2026-08-01").json()

    assert body["episodes_per_day_per_robot"] == []
    assert set(body["requests_by_status"].values()) == {0}
    assert body["submitted_to_delivered"] == {"median_seconds": None, "median_hours": None, "delivered_requests": 0}
    assert body["top_tasks_by_good_episodes"] == []


@pytest.mark.parametrize(
    "query",
    [
        "from=2026-08-10&to=2026-08-01",  # from after to
        "from=2025-01-01&to=2026-01-02",  # 367 days
        "from=2026-08-01",  # missing to
        "from=yesterday&to=2026-08-01",  # not a date
    ],
)
def test_invalid_ranges_are_422(client, operator, query):
    response = client.get(f"/analytics?{query}", headers=auth_header(operator))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_full_366_day_range_is_allowed(client, operator):
    assert get_analytics(client, operator, "2025-10-01", "2026-10-01").status_code == 200


def test_clients_cannot_see_analytics(client, client_a):
    assert get_analytics(client, client_a, "2026-08-01", "2026-08-31").status_code == 403


def test_days_are_utc_days_whatever_the_database_timezone(db):
    """date_trunc on a timestamptz uses the session's timezone. The query converts
    to UTC first, so a Kigali-configured database gives the same days."""
    episode(db, "EP-1", datetime(2026, 8, 1, 23, 30, tzinfo=UTC))  # 01:30 on 2 Aug in Kigali
    db.execute(text("SET TIME ZONE 'Africa/Kigali'"))

    body = run_analytics(db, date(2026, 8, 1), date(2026, 8, 2))

    assert body["episodes_per_day_per_robot"] == [{"day": date(2026, 8, 1), "robot_id": "arm-01", "episodes": 1}]
