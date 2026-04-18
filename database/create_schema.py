#!/usr/bin/env python3
"""
create_schema.py
Applies the Smart‑Shop Stock Inventory schema to PostgreSQL.

Usage (recommended):
  set CPI_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname?sslmode=require
  python -m database.create_schema

This script intentionally reads connection info from environment variables and does
not embed credentials in source files.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _read_schema_sql() -> str:
    here = Path(__file__).resolve().parent
    # Keep the schema as a plain .sql file (currently `ss.sql` in this project).
    p = here / "ss.sql"
    if not p.exists():
        _die(f"Schema file not found: {p}")
    return p.read_text(encoding="utf-8")


def main() -> None:
    url = (os.environ.get("CPI_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        _die("Set CPI_DATABASE_URL (or DATABASE_URL) to a PostgreSQL SQLAlchemy URL.")

    # Prefer psycopg v3 via SQLAlchemy URL; for direct execution we use psycopg (v3).
    try:
        import psycopg
    except Exception as e:
        _die(f"psycopg is not installed or failed to import: {e}")

    sql = _read_schema_sql()

    # psycopg expects libpq-style DSN. SQLAlchemy URLs are also accepted by psycopg.
    print("Connecting…")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            print("Applying schema…")
            cur.execute(sql)
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()

