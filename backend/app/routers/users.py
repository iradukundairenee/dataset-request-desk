from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models import Role, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])

admin_only = require_role(Role.admin)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return user_service.list_users(db)


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return user_service.create_user(
        db,
        email=body.email,
        password=body.password,
        name=body.name,
        role=body.role,
        organisation=body.organisation,
    )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    return user_service.update_user(db, admin, user_id, role=body.role, is_active=body.is_active)
