from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import get_db
from app.models import RequestStatus, Role, User
from app.schemas import RequestCreate, RequestDetail, RequestOut, TransitionIn
from app.services import requests as request_service

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=RequestOut, status_code=201)
def create_request(
    body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(require_role(Role.client))
):
    return request_service.create_request(
        db,
        user,
        task_name=body.task_name,
        episodes_requested=body.episodes_requested,
        deadline=body.deadline,
        notes=body.notes,
    )


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: RequestStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return request_service.list_requests(db, user, status=status)


@router.get("/{request_id}", response_model=RequestDetail)
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return request_service.get_request(db, user, request_id)


@router.post("/{request_id}/transition", response_model=RequestDetail)
def transition(
    request_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return request_service.transition(db, user, request_id, body.to_status)
