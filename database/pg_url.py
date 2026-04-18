"""Build a SQLAlchemy PostgreSQL URL from discrete env vars (no secrets committed to git)."""

from __future__ import annotations

import os
from urllib.parse import quote_plus


def build_sqlalchemy_url_from_pg_env() -> str | None:
    """If `CPI_DATABASE_URL` is not set, build one from `CPI_PG_*` variables.

    Required when using this path:
      CPI_PG_HOST, CPI_PG_USER, CPI_PG_PASSWORD, CPI_PG_DB (or CPI_PG_DATABASE)

    Optional:
      CPI_PG_PORT (default 5432)
      CPI_PG_SSLMODE (default require, typical for RDS)
      CPI_PG_CONNECT_TIMEOUT or CPI_DB_CONNECT_TIMEOUT (seconds, default 15)
    """
    host = (os.environ.get("CPI_PG_HOST") or "").strip()
    user = (os.environ.get("CPI_PG_USER") or "").strip()
    password = (os.environ.get("CPI_PG_PASSWORD") or "").strip()
    db = (os.environ.get("CPI_PG_DB") or os.environ.get("CPI_PG_DATABASE") or "").strip()
    if not (host and user and password and db):
        return None
    try:
        port = int((os.environ.get("CPI_PG_PORT") or "5432").strip())
    except ValueError:
        port = 5432
    sslmode = (os.environ.get("CPI_PG_SSLMODE") or "require").strip()

    u = quote_plus(user, safe="")
    p = quote_plus(password, safe="")
    sm = quote_plus(sslmode, safe="")

    # connect_timeout is applied in `database.engine` via SQLAlchemy `connect_args`.
    return f"postgresql+psycopg://{u}:{p}@{host}:{port}/{db}?sslmode={sm}"


def pg_connection_summary() -> dict[str, str | int | None]:
    """Safe dict for logs / health (no password)."""
    return {
        "host": (os.environ.get("CPI_PG_HOST") or "").strip() or None,
        "port": (os.environ.get("CPI_PG_PORT") or "5432").strip(),
        "database": (os.environ.get("CPI_PG_DB") or os.environ.get("CPI_PG_DATABASE") or "").strip() or None,
        "user": (os.environ.get("CPI_PG_USER") or "").strip() or None,
        "sslmode": (os.environ.get("CPI_PG_SSLMODE") or "require").strip(),
    }
