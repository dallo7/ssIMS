"""
Create the first admin user on an empty database (production bootstrap).

Requires roles + reference seed (run the app once with CPI_SEED_MODE=minimal, or this
module will call ensure_minimal_reference for you).

Usage:
  python -m database.create_bootstrap_admin --username admin --password 'YourSecurePassword'

Do not commit passwords to git; pass via env in CI if needed:
  set CPI_BOOTSTRAP_CLI_PASSWORD=... && python -m database.create_bootstrap_admin --username admin
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

from database import models
from database.engine import db_session, dispose_engine, init_database
from database.seed import ensure_minimal_reference
from utils.auth import hash_password


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Create first admin user (empty users table only).")
    p.add_argument("--username", default="admin", help="Login username (default: admin)")
    p.add_argument(
        "--password",
        default="",
        help="Plain password (prefer env CPI_BOOTSTRAP_CLI_PASSWORD in automation)",
    )
    args = p.parse_args(argv)
    pw = (args.password or os.environ.get("CPI_BOOTSTRAP_CLI_PASSWORD") or "").strip()
    if not pw:
        print("Provide --password or set CPI_BOOTSTRAP_CLI_PASSWORD.", file=sys.stderr)
        return 2
    if len(pw) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 2
    username = (args.username or "").strip() or "admin"

    init_database()
    try:
        with db_session() as s:
            if s.scalar(select(models.User).limit(1)):
                print("Refusing: users already exist. Use Administration → Users.", file=sys.stderr)
                return 1
            ensure_minimal_reference(s)
            admin_role = s.scalar(select(models.Role).where(models.Role.name == "ADMIN"))
            if not admin_role:
                print("Missing ADMIN role after ensure_minimal_reference.", file=sys.stderr)
                return 1
            if s.scalar(select(models.User).where(models.User.username == username)):
                print(f"Username {username!r} already exists.", file=sys.stderr)
                return 1
            s.add(
                models.User(
                    username=username,
                    password_hash=hash_password(pw),
                    full_name="Administrator",
                    role_id=admin_role.id,
                )
            )
    finally:
        dispose_engine()
    print(f"Created user {username!r}. Log in and change the password under Administration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
