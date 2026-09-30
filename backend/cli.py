"""Command line tools.

    python -m cli seed-users [path]     (default: /seed/users.json)
"""
import argparse
import json

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Role, User


def load_users(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_users(db, users):
    """Create users that don't exist yet. Existing emails are left untouched.

    Returns (created, skipped) counts.
    """
    created = 0
    skipped = 0
    for u in users:
        email = u["email"].strip().lower()
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            skipped += 1
            continue
        db.add(
            User(
                email=email,
                password_hash=hash_password(u["password"]),
                name=u["name"],
                role=Role(u["role"]),
                organisation=u.get("organisation"),
            )
        )
        # Flush so a duplicate email later in the same file is seen as existing.
        db.flush()
        created += 1
    db.commit()
    return created, skipped


def main():
    parser = argparse.ArgumentParser(prog="cli")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed-users", help="create seed users (idempotent)")
    seed.add_argument("path", nargs="?", default="/seed/users.json")

    args = parser.parse_args()

    if args.command == "seed-users":
        with SessionLocal() as db:
            created, skipped = seed_users(db, load_users(args.path))
        print(json.dumps({"created": created, "skipped_existing": skipped}))


if __name__ == "__main__":
    main()
