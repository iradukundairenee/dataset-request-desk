"""User management rules (admin only; the role check is done by the router)."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.errors import Conflict, NotFound
from app.models import Role, User


def list_users(db):
    return db.scalars(select(User).order_by(User.id)).all()


def create_user(db, email, password, name, role, organisation=None):
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise Conflict("A user with this email already exists")

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        organisation=organisation,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two admins creating the same email at the same moment: the UNIQUE constraint wins.
        db.rollback()
        raise Conflict("A user with this email already exists")
    return user


def update_user(db, acting_admin, user_id, role=None, is_active=None):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")

    # An admin can't lock themselves out. This also guarantees there is always
    # at least one active admin: only admins change users, and never themselves.
    if user.id == acting_admin.id:
        if is_active is False:
            raise Conflict("You cannot deactivate your own account")
        if role is not None and role != Role.admin:
            raise Conflict("You cannot remove your own admin role")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    return user
