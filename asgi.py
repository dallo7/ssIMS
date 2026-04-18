"""
ASGI entry point: FastAPI in front of the Dash/Flask app (WSGI).

Run: uvicorn asgi:application --host 127.0.0.1 --port 8050
Or: python app.py (uses uvicorn with reload by default).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.requests import Request

from app import server as flask_server
from routes.fastapi_db import router as fastapi_db_router
from utils.app_text import primary_app_name


class CPIRequestMiddleware(BaseHTTPMiddleware):
    """Example middleware on the FastAPI stack (runs before the Dash app)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-CPI-Served-By"] = "fastapi+wsgi"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Dispose SQLAlchemy pool on shutdown (clean reconnect after reload)."""
    yield
    from database.engine import dispose_engine

    dispose_engine()


api = FastAPI(
    title=primary_app_name(),
    version="1.0",
    lifespan=lifespan,
)
api.add_middleware(CPIRequestMiddleware)
api.include_router(fastapi_db_router)


@api.get("/api/health")
def health():
    return {"status": "ok", "app": primary_app_name()}


api.mount("/", WSGIMiddleware(flask_server))
application = api
