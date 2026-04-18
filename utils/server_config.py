"""Production-oriented Flask server settings (sessions, reverse proxy, headers)."""
from __future__ import annotations

import atexit
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


# Baseline headers applied to every response in production. Values chosen to be
# compatible with Dash's client-side rendering (no strict CSP on inline scripts).
_DEFAULT_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}


def _hsts_header_value() -> str | None:
    """Only emit HSTS when the operator confirmed the site is HTTPS-only."""
    if os.environ.get("CPI_SESSION_COOKIE_SECURE", "").lower() not in ("1", "true", "yes"):
        return None
    raw = (os.environ.get("CPI_HSTS_MAX_AGE") or "31536000").strip()
    try:
        age = int(raw)
    except ValueError:
        age = 31_536_000
    age = max(0, min(age, 63_072_000))
    extras = ""
    if os.environ.get("CPI_HSTS_INCLUDE_SUBDOMAINS", "").lower() in ("1", "true", "yes"):
        extras += "; includeSubDomains"
    if os.environ.get("CPI_HSTS_PRELOAD", "").lower() in ("1", "true", "yes"):
        extras += "; preload"
    return f"max-age={age}{extras}"


def _install_security_headers(flask_server) -> None:
    hsts = _hsts_header_value()

    @flask_server.after_request
    def _add_headers(resp):  # pragma: no cover — wired into Flask
        for k, v in _DEFAULT_SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if hsts is not None:
            resp.headers.setdefault("Strict-Transport-Security", hsts)
        return resp


def _install_graceful_shutdown() -> None:
    """Dispose the SQLAlchemy pool on clean process exit (WSGI parity w/ ASGI lifespan)."""

    def _dispose() -> None:  # pragma: no cover — process-exit hook
        try:
            from database.engine import dispose_engine

            dispose_engine()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "dispose_engine() raised during shutdown.", exc_info=True
            )

    atexit.register(_dispose)


def apply_flask_server_settings(flask_server) -> None:
    """Session hardening, ProxyFix, and security headers — all no-ops in dev."""
    validate_production_secret(flask_server.secret_key)
    # Engine dispose is useful in both dev and prod (avoids stale pooled
    # connections when workers recycle) and cheap otherwise.
    _install_graceful_shutdown()
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
    _install_security_headers(flask_server)
