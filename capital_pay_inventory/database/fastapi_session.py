"""FastAPI dependency: one SQLAlchemy Session per request (for ASGI / other services)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from database.engine import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """Yield a Session; commit on success, rollback on error, always close."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
