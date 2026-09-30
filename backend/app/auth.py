"""Password hashing, JWT tokens, and the current-user / role dependencies."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

JWT_ALGORITHM = "HS256"

# bcrypt only uses the first 72 bytes of a password (bcrypt 5 raises an error instead).
MAX_PASSWORD_BYTES = 72


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


# Used when the email doesn't exist, so a login attempt takes the same time
# either way and response time doesn't reveal which emails are registered.
DUMMY_PASSWORD_HASH = hash_password("dummy-password")


def create_access_token(user_id):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token):
    """Return the user id from a valid token, or None if the token is invalid or expired."""
    try:
        # algorithms= is a fixed list, so a token claiming "alg: none" is rejected.
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def authenticate(db, email, password):
    """Return the user if email + password are right and the account is active, else None."""
    user = db.query(User).filter(User.email == email.strip().lower()).one_or_none()
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def unauthorized(message):
    return HTTPException(status_code=401, detail=message, headers={"WWW-Authenticate": "Bearer"})


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise unauthorized("Not authenticated")

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise unauthorized("Invalid or expired token")

    # Load the user on every request: a deactivated user's token stops working
    # immediately, and the role always comes from the DB, not from the token.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("Invalid or expired token")

    request.state.user_id = user.id  # picked up by the request log line
    return user


def require_role(*roles):
    """Dependency factory: require_role(Role.operator, Role.admin)."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to do this")
        return user

    return dependency
