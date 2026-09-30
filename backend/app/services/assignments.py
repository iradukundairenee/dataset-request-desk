"""Assigning episodes to requests.

Every change locks the request row (SELECT ... FOR UPDATE), the same lock the
status transition takes. So an unassign can't slip in between the "enough
episodes assigned?" check and the move to delivered.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import Conflict, Forbidden, NotFound
from app.models import Assignment, Episode, Quality, Request, RequestStatus, Role
from app.services.requests import get_visible_request

S = RequestStatus

# Episodes can only change while the request is being worked on.
EDITABLE_STATUSES = {S.submitted, S.in_progress, S.rejected}
ASSIGNABLE_QUALITIES = {Quality.good, Quality.usable}


def _require_staff(user):
    if user.role not in (Role.operator, Role.admin):
        raise Forbidden("Only operators and admins can change assignments")


def _lock_editable_request(db, request_id):
    request = db.scalar(select(Request).where(Request.id == request_id).with_for_update())
    if request is None:
        raise NotFound("Request not found")
    if request.status not in EDITABLE_STATUSES:
        raise Conflict(f"Episodes cannot be changed while the request is {request.status.value}")
    return request


def list_assigned(db, user, request_id):
    """Episodes on a request. The owning client may see them too (it's their delivery)."""
    request = get_visible_request(db, user, request_id)
    episodes = db.scalars(
        select(Episode)
        .join(Assignment, Assignment.episode_id == Episode.id)
        .where(Assignment.request_id == request.id)
        .order_by(Assignment.assigned_at, Assignment.id)
    ).all()
    for episode in episodes:
        episode.assigned_request_id = request.id
    return episodes


def assign(db, user, request_id, episode_ids):
    """Assign several episodes at once. All-or-nothing: if any one is not allowed,
    nothing is assigned and the error names the problem episodes."""
    _require_staff(user)
    request = _lock_editable_request(db, request_id)
    episode_ids = list(dict.fromkeys(episode_ids))  # drop repeats, keep order

    episodes = {e.id: e for e in db.scalars(select(Episode).where(Episode.id.in_(episode_ids)))}
    missing = [i for i in episode_ids if i not in episodes]
    if missing:
        raise NotFound(f"Episodes not found: {missing}")

    bad_quality = [episodes[i].episode_id for i in episode_ids if episodes[i].quality not in ASSIGNABLE_QUALITIES]
    if bad_quality:
        raise Conflict(f"Only good or usable episodes can be assigned: {', '.join(bad_quality)}")

    taken = db.execute(
        select(Episode.episode_id, Assignment.request_id)
        .join(Assignment, Assignment.episode_id == Episode.id)
        .where(Episode.id.in_(episode_ids))
    ).all()
    if taken:
        described = ", ".join(f"{eid} (request {rid})" for eid, rid in taken)
        raise Conflict(f"Already assigned: {described}")

    for episode_id in episode_ids:
        db.add(Assignment(request_id=request.id, episode_id=episode_id, assigned_by=user.id))
    try:
        db.commit()
    except IntegrityError:
        # Another request grabbed one of these episodes after our check above.
        # The UNIQUE(episode_id) constraint is the final guarantee.
        db.rollback()
        raise Conflict("One of these episodes was just assigned to another request; reload and try again")
    return list_assigned(db, user, request.id)


def unassign(db, user, request_id, episode_id):
    _require_staff(user)
    request = _lock_editable_request(db, request_id)
    assignment = db.scalar(
        select(Assignment).where(Assignment.request_id == request.id, Assignment.episode_id == episode_id)
    )
    if assignment is None:
        raise NotFound("Episode is not assigned to this request")
    db.delete(assignment)
    db.commit()
