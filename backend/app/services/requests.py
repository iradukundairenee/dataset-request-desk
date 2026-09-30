"""Dataset requests: create, read, and the status machine."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.errors import Conflict, Forbidden, Invalid, NotFound
from app.models import Assignment, Request, RequestStatus, RequestStatusEvent, Role
from app.services.normalise import normalise_task_name

S = RequestStatus

# Valid moves: current status -> statuses it may move to.
ALLOWED_TRANSITIONS = {
    S.submitted: {S.in_progress},
    S.in_progress: {S.delivered},
    S.delivered: {S.accepted, S.rejected},
    S.rejected: {S.in_progress},  # rework
    S.accepted: set(),  # final
}

# Who may move a request INTO each status. Each target belongs to exactly one side:
# operators run the workflow, the owning client reviews the delivery.
ROLES_FOR_TARGET = {
    S.in_progress: {Role.operator, Role.admin},
    S.delivered: {Role.operator, Role.admin},
    S.accepted: {Role.client},
    S.rejected: {Role.client},
}


def create_request(db, client, task_name, episodes_requested, deadline, notes=None):
    if client.role != Role.client:
        raise Forbidden("Only clients can create requests")
    if deadline < datetime.now(timezone.utc).date():
        raise Invalid("Deadline cannot be in the past")

    request = Request(
        client_id=client.id,
        task_name=normalise_task_name(task_name),
        episodes_requested=episodes_requested,
        deadline=deadline,
        notes=notes,
        status=S.submitted,
    )
    db.add(request)
    db.flush()  # get request.id for the event row
    db.add(RequestStatusEvent(request_id=request.id, from_status=None, to_status=S.submitted, actor_id=client.id))
    db.commit()  # request and its creation event are saved together, or not at all
    request.assigned_count = 0
    return request


def _assigned_count(db, request_id):
    return db.scalar(select(func.count()).select_from(Assignment).where(Assignment.request_id == request_id))


def list_requests(db, user, status=None):
    """Clients see only their own requests; operators and admins see all."""
    query = (
        select(Request, func.count(Assignment.id))
        .outerjoin(Assignment, Assignment.request_id == Request.id)
        .group_by(Request.id)
        .order_by(Request.created_at.desc(), Request.id.desc())
    )
    if user.role == Role.client:
        query = query.where(Request.client_id == user.id)
    if status is not None:
        query = query.where(Request.status == status)

    requests = []
    for request, assigned_count in db.execute(query).all():
        request.assigned_count = assigned_count
        requests.append(request)
    return requests


def _get_visible(db, user, request_id, lock=False):
    """Load a request the user is allowed to see. Another client's request is
    reported as not found (404), so clients can't probe which ids exist."""
    query = select(Request).where(Request.id == request_id)
    if lock:
        query = query.with_for_update()
    request = db.scalar(query)
    if request is None or (user.role == Role.client and request.client_id != user.id):
        raise NotFound("Request not found")
    return request


def get_request(db, user, request_id):
    request = _get_visible(db, user, request_id)
    request.assigned_count = _assigned_count(db, request.id)
    request.events = db.scalars(
        select(RequestStatusEvent)
        .where(RequestStatusEvent.request_id == request.id)
        .order_by(RequestStatusEvent.id)
    ).all()
    return request


def transition(db, user, request_id, to_status):
    # Lock the row until commit: a concurrent transition or unassign on the same
    # request waits, so the "enough episodes assigned" check can't be raced.
    request = _get_visible(db, user, request_id, lock=True)
    from_status = request.status

    # 1. Role: who may move a request into this status at all?
    if to_status not in ROLES_FOR_TARGET:
        raise Conflict(f"A request can never be moved back to {to_status.value}")
    if user.role not in ROLES_FOR_TARGET[to_status]:
        raise Forbidden(f"Your role cannot move a request to {to_status.value}")

    # 2. Is this a valid move from the current status?
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise Conflict(f"Cannot move a request from {from_status.value} to {to_status.value}")

    # 3. Delivery needs enough episodes.
    if to_status == S.delivered:
        assigned = _assigned_count(db, request.id)
        if assigned < request.episodes_requested:
            raise Conflict(
                f"Cannot deliver: {assigned} of {request.episodes_requested} requested episodes assigned"
            )

    request.status = to_status
    db.add(RequestStatusEvent(request_id=request.id, from_status=from_status, to_status=to_status, actor_id=user.id))
    db.commit()  # status change and its event are saved together; releases the lock
    return get_request(db, user, request.id)
