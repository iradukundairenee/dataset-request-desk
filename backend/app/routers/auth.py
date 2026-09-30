from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import authenticate, create_access_token, get_current_user
from app.db import get_db
from app.models import User
from app.schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        # Same message for unknown email, wrong password and deactivated account,
        # so the response doesn't reveal which emails exist.
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
