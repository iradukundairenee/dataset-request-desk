from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models import Role, User
from app.services import analytics as analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/analytics")
def get_analytics(
    # "from" is a Python keyword, so the parameter is named date_from and exposed as ?from=
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator, Role.admin)),
):
    return analytics_service.get_analytics(db, date_from, date_to)
