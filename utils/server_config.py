"""Production-oriented Flask server settings (sessions, reverse proxy)."""
from __future__ import annotations

import os

_DEV_SECRET = "dev-cpi-inventory-change-me"


def is_production_env() -> bool:
    return os.environ.get("CPI_ENV", "").strip().lower() in ("production", "prod", "live")


def validate_production_secret(secret: str) -> None:
    if not is_production_env():
        return
    s = (secret or "").strip()
    if not s or s == _DEV_SECRET or len(s) < 16:
        raise RuntimeError(
            "CPI_SECRET_KEY must be set to a long random value when CPI_ENV is production "
            '(e.g. python -c "import secrets; print(secrets.token_hex(32))")'
        )


def apply_flask_server_settings(flask_server) -> None:
    """Session hardening in production; optional ProxyFix behind TLS terminator."""
    validate_production_secret(flask_server.secret_key)
    if not is_production_env():
        return
    flask_server.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if os.environ.get("CPI_SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        flask_server.config["SESSION_COOKIE_SECURE"] = True
    if os.environ.get("CPI_BEHIND_PROXY", "").lower() in ("1", "true", "yes"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        flask_server.wsgi_app = ProxyFix(
            flask_server.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_prefix=1,
        )
