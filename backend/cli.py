"""Command line tools.

    python -m cli seed-users [path]     (default: /seed/users.json)
    python -m cli import <path.csv>     import episodes; prints the report as JSON
"""
import argparse
import json
import os
import sys

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Role, User
from app.services.importer import ImportFileError, import_file


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

    import_cmd = commands.add_parser("import", help="import episodes from a CSV file (safe to re-run)")
    import_cmd.add_argument("path")

    args = parser.parse_args()

    if args.command == "seed-users":
        with SessionLocal() as db:
            created, skipped = seed_users(db, load_users(args.path))
        print(json.dumps({"created": created, "skipped_existing": skipped}))

    if args.command == "import":
        with SessionLocal() as db:
            try:
                report = import_file(db, args.path, filename=os.path.basename(args.path))
            except ImportFileError as error:
                print(f"Import failed: {error.message}", file=sys.stderr)
                sys.exit(1)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
