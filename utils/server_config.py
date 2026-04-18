"""Production-oriented Flask server settings (sessions, reverse proxy, headers)."""
from __future__ import annotations

import atexit
import os

_DEV_SECRET = "dev-cpi-inventory-change-me"

# Routes that must remain reachable without a session. Everything else is gated.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/login", "/welcome", "/logout"})

# Path prefixes that bypass the auth/cache hooks entirely (static assets,
# Dash internal endpoints, and our public REST API blueprint).
_OPEN_PREFIXES: tuple[str, ...] = (
    "/assets/",
    "/_dash",
    "/_reload",
    "/_favicon",
    "/api/",
)

# Cache-Control bundle that defeats both the regular HTTP cache and the
# back-forward cache (bfcache) for protected, dynamic Dash responses.
_NO_STORE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


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


def _path_is_open(path: str) -> bool:
    """True if the request path is a public/static endpoint and should bypass auth."""
    if not path:
        return False
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _OPEN_PREFIXES)


def _install_no_cache_headers(flask_server) -> None:
    """Stamp protected dynamic responses with no-store so the browser can't bfcache them.

    Static assets keep their normal caching behaviour. We only override dynamic
    responses (Dash pages, _dash-update-component callbacks, and any custom routes
    other than /assets/*). This is the single most important defence against the
    'Back button shows the logged-out user's previous page' class of bug.
    """
    from flask import request

    @flask_server.after_request
    def _stamp_no_store(resp):  # pragma: no cover — wired into Flask
        path = request.path or ""
        if path.startswith("/assets/"):
            return resp
        for k, v in _NO_STORE_HEADERS.items():
            resp.headers[k] = v
        return resp


def _install_session_redirect(flask_server) -> None:
    """Redirect unauthenticated HTML page-loads to /login *before* Dash boots.

    This catches direct navigations and Back-button restorations that previously
    let the browser repaint a stale logged-in view. AJAX/JSON callbacks are left
    alone — Dash's own auth-guard callback handles those — to preserve the SPA's
    client-side behaviour.
    """
    from flask import redirect, request, session

    @flask_server.before_request
    def _gate(_=None):  # pragma: no cover — wired into Flask
        path = request.path or ""
        if _path_is_open(path):
            return None
        # Only intercept top-level HTML navigations; let Dash's AJAX endpoints
        # respond normally (they'll surface the missing session via the in-app
        # auth_guard callback and still be cache-prevented by the no-store hook).
        if request.method != "GET":
            return None
        accept = request.headers.get("Accept", "")
        if "text/html" not in accept:
            return None
        if session.get("user_id"):
            return None
        return redirect("/login")


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
    """Session hardening, ProxyFix, security headers and bfcache defence."""
    validate_production_secret(flask_server.secret_key)
    # Engine dispose is useful in both dev and prod (avoids stale pooled
    # connections when workers recycle) and cheap otherwise.
    _install_graceful_shutdown()
    # Cache + auth gate run in dev too — they are the core defence against
    # session-leak / back-button-after-logout bugs and add no real cost.
    _install_no_cache_headers(flask_server)
    _install_session_redirect(flask_server)
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
