"""Session-backed auth helpers (Flask session)."""
from __future__ import annotations

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

import bcrypt
from flask import session
from sqlalchemy import select

from database.engine import db_session
from database import models

P = ParamSpec("P")
R = TypeVar("R")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def login_user(user_id: int, username: str, role: str, full_name: str) -> None:
    session["user_id"] = user_id
    session["username"] = username
    session["role"] = role
    session["full_name"] = full_name
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return {
        "id": uid,
        "username": session.get("username"),
        "role": session.get("role"),
        "full_name": session.get("full_name"),
    }


def role_at_least(role: str) -> bool:
    order = ("VIEWER", "STOCK_CLERK", "MANAGER", "ADMIN")
    u = current_user()
    if not u:
        return False
    try:
        return order.index(u["role"]) >= order.index(role)
    except ValueError:
        return False


def require_roles(*roles: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapped(*args: P.args, **kwargs: P.kwargs):
            u = current_user()
            if not u or u["role"] not in roles:
                from dash.exceptions import PreventUpdate

                raise PreventUpdate
            return fn(*args, **kwargs)

        return wrapped

    return deco


def load_user_record(user_id: int) -> models.User | None:
    with db_session() as s:
        return s.get(models.User, user_id)


def get_role_name(user_id: int) -> str | None:
    with db_session() as s:
        u = s.get(models.User, user_id)
        if not u:
            return None
        r = s.get(models.Role, u.role_id)
        return r.name if r else None
