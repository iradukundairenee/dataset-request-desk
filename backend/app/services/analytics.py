"""Analytics for a date range. Every number is computed by Postgres; Python only
passes the range in and shapes the rows into JSON.

The range is inclusive of both dates, in UTC: [from 00:00, to + 1 day 00:00).
"""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import text

from app.errors import Invalid
from app.models import RequestStatus

MAX_RANGE_DAYS = 366

EPISODES_PER_DAY_PER_ROBOT = text("""
    SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           robot_id,
           count(*) AS episodes
    FROM episodes
    WHERE recorded_at >= :start AND recorded_at < :end
    GROUP BY day, robot_id
    ORDER BY day, robot_id
""")

REQUESTS_BY_STATUS = text("""
    SELECT status, count(*) AS requests
    FROM requests
    WHERE created_at >= :start AND created_at < :end
    GROUP BY status
""")

# Per request: the first time it was submitted and the FIRST time it was delivered
# (a rework cycle doesn't reset the clock). Counted for requests whose first
# delivery falls in the range.
MEDIAN_SUBMITTED_TO_DELIVERED = text("""
    WITH first_events AS (
        SELECT request_id,
               min(created_at) FILTER (WHERE to_status = 'submitted') AS submitted_at,
               min(created_at) FILTER (WHERE to_status = 'delivered') AS delivered_at
        FROM request_status_events
        GROUP BY request_id
    )
    SELECT percentile_cont(0.5) WITHIN GROUP (
               ORDER BY extract(epoch FROM delivered_at - submitted_at)
           ) AS median_seconds,
           count(*) AS delivered_requests
    FROM first_events
    WHERE delivered_at >= :start AND delivered_at < :end
      AND submitted_at IS NOT NULL
""")

TOP_TASKS_BY_GOOD_EPISODES = text("""
    SELECT task_name, count(*) AS good_episodes
    FROM episodes
    WHERE quality = 'good' AND recorded_at >= :start AND recorded_at < :end
    GROUP BY task_name
    ORDER BY good_episodes DESC, task_name
    LIMIT 5
""")


def get_analytics(db, date_from, date_to):
    if date_from > date_to:
        raise Invalid("'from' must be on or before 'to'")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise Invalid(f"Date range can be at most {MAX_RANGE_DAYS} days")

    params = {
        "start": datetime.combine(date_from, time.min, tzinfo=timezone.utc),
        "end": datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc),
    }

    per_day = db.execute(EPISODES_PER_DAY_PER_ROBOT, params).all()

    # Every status is listed, with 0 when there are none, so the shape is stable.
    by_status = {status.value: 0 for status in RequestStatus}
    for status, count in db.execute(REQUESTS_BY_STATUS, params).all():
        by_status[status] = count

    median_seconds, delivered_requests = db.execute(MEDIAN_SUBMITTED_TO_DELIVERED, params).one()

    top_tasks = db.execute(TOP_TASKS_BY_GOOD_EPISODES, params).all()

    return {
        "from": date_from,
        "to": date_to,
        "episodes_per_day_per_robot": [
            {"day": day, "robot_id": robot_id, "episodes": episodes} for day, robot_id, episodes in per_day
        ],
        "requests_by_status": by_status,
        "submitted_to_delivered": {
            "median_seconds": median_seconds,
            "median_hours": round(median_seconds / 3600, 2) if median_seconds is not None else None,
            "delivered_requests": delivered_requests,
        },
        "top_tasks_by_good_episodes": [
            {"task_name": task_name, "good_episodes": count} for task_name, count in top_tasks
        ],
    }
