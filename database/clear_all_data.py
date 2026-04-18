"""
Remove all row data from CPI application tables (PostgreSQL).

Schema and objects stay; sequences reset. On next app start, `seed_if_empty` repopulates
according to CPI_SEED_MODE (production defaults to minimal: roles, alert rules, config only;
use CPI_BOOTSTRAP_ADMIN_PASSWORD or `python -m database.create_bootstrap_admin` for the first login).

Usage (from project root, same env as the app):
  python -m database.clear_all_data --yes
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect, text

from database import models
from database.engine import dispose_engine, get_engine


def _truncate_all_public_app_tables() -> list[str]:
    engine = get_engine()
    names = [t.name for t in models.Base.metadata.sorted_tables]
    insp = inspect(engine)
    existing = set(insp.get_table_names(schema="public"))
    to_truncate = [n for n in names if n in existing]
    if not to_truncate:
        return []
    # Single statement: CASCADE handles FK order; RESTART IDENTITY resets serials.
    q = text(
        "TRUNCATE TABLE "
        + ", ".join(f"public.{n}" for n in to_truncate)
        + " RESTART IDENTITY CASCADE"
    )
    with engine.begin() as conn:
        conn.execute(q)
    return to_truncate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Truncate all CPI inventory app tables (PostgreSQL).")
    p.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation; without it the script exits without changes.",
    )
    args = p.parse_args(argv)
    if not args.yes:
        print("Refusing to run without --yes (destructive). Example:", file=sys.stderr)
        print("  python -m database.clear_all_data --yes", file=sys.stderr)
        return 2
    try:
        cleared = _truncate_all_public_app_tables()
    finally:
        dispose_engine()
    if not cleared:
        print("No matching application tables found in schema public; nothing truncated.")
        return 0
    print(f"Truncated {len(cleared)} table(s): {', '.join(cleared)}")
    print("Restart the app to re-seed. Set CPI_ENV=production (or CPI_SEED_MODE=minimal) for empty operational data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
