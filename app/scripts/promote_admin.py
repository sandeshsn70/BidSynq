"""Promote an EXISTING registered user to administrator (the only supported way to create admins).

Usage (PowerShell, from the project folder, with DATABASE_URL pointing at your database):
    $env:DATABASE_URL = "postgresql://...external URL..."
    python -m app.scripts.promote_admin someone@example.com

The change is written to the tamper-evident audit log. Nothing else is modified.
"""
import sys

from sqlalchemy import func, select

from app.audit import append_audit
from app.database import SessionLocal
from app.models import User


def main(argv: list[str]) -> int:
    if len(argv) != 2 or "@" not in argv[1]:
        print("Usage: python -m app.scripts.promote_admin user@example.com")
        return 2
    email = argv[1].strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"No user with email {email}. Register the account first.")
            return 1
        if user.role == "admin":
            print(f"{email} is already an administrator.")
            return 0
        old_role = user.role
        user.role = "admin"
        append_audit(db, None, "user.promoted_admin", "user", user.id, {"from": old_role, "to": "admin", "via": "cli"})
        db.commit()
        print(f"{email} is now an administrator (was {old_role}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
