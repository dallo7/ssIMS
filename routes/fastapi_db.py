"""FastAPI routes that share the same SQLAlchemy engine/pool as Dash (via `get_db`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.fastapi_session import get_db
from database.pg_url import pg_connection_summary

router = APIRouter(tags=["database"])


@router.get("/api/db/health")
def db_health(db: Session = Depends(get_db)):
    """Verify DB connectivity (uses pooled connection from `get_db`)."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable", "pg": pg_connection_summary()}
