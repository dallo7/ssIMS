"""
Reset application users to a single super-admin (ADMIN role).

Reassigns every foreign key that points at removed users to the keeper account,
deletes other user rows, and clears server-side session rows so everyone must
log in again.

Usage (from project root):

    python -m database.reset_users

Optional:

    python -m database.reset_users --password YourSecurePassword
        (sets the super-admin password; omit to keep the current hash if the user already exists)

    python -m database.reset_users --username admin
        (keeper account name; created if missing, password default admin)
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import delete, select, update

from database import models
from database.engine import db_session, init_database
from utils.auth import hash_password


def _ensure_super_admin(
    session,
    username: str,
    password_plain: str | None,
    *,
    update_password: bool,
) -> models.User:
    role = session.scalar(select(models.Role).where(models.Role.name == "ADMIN"))
    if not role:
        raise RuntimeError("ADMIN role is missing; run the app once or seed roles first.")

    u = session.scalar(select(models.User).where(models.User.username == username))
    if u:
        u.role_id = role.id
        u.is_active = True
        u.full_name = u.full_name or "Super Administrator"
        if update_password:
            pw = password_plain or os.environ.get("CPI_BOOTSTRAP_PASSWORD") or "admin"
            u.password_hash = hash_password(pw)
        session.flush()
        return u

    pw = password_plain or os.environ.get("CPI_BOOTSTRAP_PASSWORD") or "admin"
    u = models.User(
        username=username,
        password_hash=hash_password(pw),
        full_name="Super Administrator",
        role_id=role.id,
        is_active=True,
    )
    session.add(u)
    session.flush()
    return u


def reset_to_single_super_admin(
    *,
    username: str = "admin",
    password_plain: str | None = None,
    update_password: bool = False,
) -> tuple[int, int]:
    """
    Keep exactly one super-admin user; remove all others.

    Returns (keeper_user_id, deleted_user_count).
    """
    init_database()

    with db_session() as session:
        keeper = _ensure_super_admin(
            session,
            username,
            password_plain,
            update_password=update_password,
        )

        all_ids = list(session.scalars(select(models.User.id)).all())
        from_ids = [i for i in all_ids if i != keeper.id]
        if not from_ids:
            session.execute(delete(models.UserSession))
            return keeper.id, 0

        # Reassign FKs that reference users we are about to delete
        session.execute(
            update(models.InventoryItem)
            .where(models.InventoryItem.created_by.in_(from_ids))
            .values(created_by=keeper.id)
        )
        session.execute(
            update(models.StockTransaction)
            .where(models.StockTransaction.performed_by.in_(from_ids))
            .values(performed_by=keeper.id)
        )
        session.execute(
            update(models.StockTransaction)
            .where(models.StockTransaction.approved_by.in_(from_ids))
            .values(approved_by=keeper.id)
        )
        session.execute(
            update(models.PurchaseOrder)
            .where(models.PurchaseOrder.created_by.in_(from_ids))
            .values(created_by=keeper.id)
        )
        session.execute(
            update(models.PurchaseOrder)
            .where(models.PurchaseOrder.approved_by.in_(from_ids))
            .values(approved_by=keeper.id)
        )
        session.execute(
            update(models.AuditSession)
            .where(models.AuditSession.created_by.in_(from_ids))
            .values(created_by=keeper.id)
        )
        session.execute(
            update(models.AuditSession)
            .where(models.AuditSession.reviewed_by.in_(from_ids))
            .values(reviewed_by=keeper.id)
        )
        session.execute(
            update(models.AlertAcknowledgment)
            .where(models.AlertAcknowledgment.user_id.in_(from_ids))
            .values(user_id=keeper.id)
        )
        session.execute(
            update(models.ActivityLog)
            .where(models.ActivityLog.user_id.in_(from_ids))
            .values(user_id=keeper.id)
        )
        session.execute(
            update(models.InventoryChangeRequest)
            .where(models.InventoryChangeRequest.submitted_by.in_(from_ids))
            .values(submitted_by=keeper.id)
        )
        session.execute(
            update(models.InventoryChangeRequest)
            .where(models.InventoryChangeRequest.reviewed_by.in_(from_ids))
            .values(reviewed_by=keeper.id)
        )

        session.execute(delete(models.UserSession))
        session.execute(delete(models.User).where(models.User.id.in_(from_ids)))

        deleted = len(from_ids)
        return keeper.id, deleted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reset DB users to a single super-admin.")
    p.add_argument("--username", default="admin", help="Super-admin login name (default: admin)")
    p.add_argument(
        "--password",
        default=None,
        help="If set, assigns this password to the super-admin (existing or new). If omitted for an existing user, the current password is kept.",
    )
    args = p.parse_args(argv)

    try:
        keeper_id, n = reset_to_single_super_admin(
            username=args.username,
            password_plain=args.password,
            update_password=args.password is not None,
        )
    except Exception as e:
        print(f"reset_users: failed: {e}", file=sys.stderr)
        return 1

    print(f"reset_users: keeper user id={keeper_id!r}, removed {n} other user(s).")
    print("reset_users: all sessions cleared — log in again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
