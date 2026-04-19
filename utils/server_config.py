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

# Static, content-addressed assets that are safe to cache aggressively.
# Dash component-suite URLs include both a package version and a file mtime
# query string, so a stale browser cache is impossible — when the package or
# file changes, the URL changes too. Caching these for a year (with `immutable`)
# is the single biggest perf win for Dash apps: without it every internal
# navigation re-downloads the full ~1 MB JS bundle, which is exactly what was
# making "open a page" feel slow before this change.
_LONG_CACHE_VALUE: str = "public, max-age=31536000, immutable"

# Project /assets/ files (favicon, custom.css, brand SVG/PNG, tutorials).
# We don't fingerprint these, so use a much shorter window so a deploy can ship
# a CSS or icon change without users having to hard-refresh.
_SHORT_CACHE_VALUE: str = "public, max-age=86400"


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
    """Two-track cache policy.

    * **Dynamic SPA shell + callbacks** (`/`, `/_dash-layout`,
      `/_dash-dependencies`, `/_dash-update-component`, custom Flask routes):
      stamped `no-store` so the browser can't bfcache a logged-in screen.
      This is the defence against the "Back button after logout shows the old
      page" bug.
    * **Static, versioned bundles** (`/_dash-component-suites/*`,
      `/assets/*`, `/_favicon.ico`): allowed to cache for a long time. Dash
      component URLs already carry a `?v=` and `?m=` query string, so a stale
      browser cache is impossible — and caching them is what makes internal
      navigation feel instant instead of re-downloading 1 MB of JS each time.
    """
    from flask import request

    @flask_server.after_request
    def _stamp_cache_headers(resp):  # pragma: no cover — wired into Flask
        path = request.path or ""
        # Dash's versioned component bundles: cache forever (immutable URLs).
        if path.startswith("/_dash-component-suites/"):
            resp.headers["Cache-Control"] = _LONG_CACHE_VALUE
            resp.headers.pop("Pragma", None)
            resp.headers.pop("Expires", None)
            return resp
        # Project static files — short cache so a deploy can ship a CSS/icon
        # change without forcing every user to hard-refresh.
        if path.startswith("/assets/") or path == "/_favicon.ico":
            resp.headers["Cache-Control"] = _SHORT_CACHE_VALUE
            resp.headers.pop("Pragma", None)
            resp.headers.pop("Expires", None)
            return resp
        # Everything else (SPA shell, callbacks, public Flask pages): no-store.
        for k, v in _NO_STORE_HEADERS.items():
            resp.headers[k] = v
        return resp


def _install_session_redirect(flask_server) -> None:
    """Redirect unauthenticated HTML page-loads to /welcome *before* Dash boots.

    Unauthenticated visitors land on the marketing landing page first, where
    they can choose to sign in. This catches direct navigations and Back-button
    restorations that previously let the browser repaint a stale logged-in
    view. AJAX/JSON callbacks are left alone — Dash's own auth-guard callback
    handles those — to preserve the SPA's client-side behaviour.
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
        return redirect("/welcome")


def _install_gzip_compression(flask_server) -> None:
    """Gzip text-y responses on the way out.

    Cuts JS/CSS/JSON payloads by ~70%. Critical for the Dash component-suite
    bundles (AgGrid, Plotly, Mantine) which are large but very compressible.
    Behaviour:

    * Honour the client's `Accept-Encoding: gzip`. Skip otherwise.
    * Only compress text/* and application/{json,javascript,xml,...} types.
    * Skip already-compressed responses, byte-range responses, and anything
      below 512 bytes (where gzip overhead beats the savings).
    * Sets `Vary: Accept-Encoding` so caches/CDNs differentiate properly.

    This stays in pure stdlib (gzip module) so we don't pull in another dep.
    Nginx-level compression (in production) is fine to keep on top of this —
    Nginx will simply pass our pre-compressed body through unchanged.
    """
    import gzip
    from io import BytesIO

    from flask import request

    _COMPRESSIBLE_PREFIXES: tuple[str, ...] = (
        "text/",
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
        "application/wasm",
        "image/svg+xml",
    )
    _MIN_BYTES = 512

    @flask_server.after_request
    def _gzip(resp):  # pragma: no cover — wired into Flask
        try:
            accept = request.headers.get("Accept-Encoding", "")
            if "gzip" not in accept.lower():
                return resp
            if resp.status_code < 200 or resp.status_code >= 300:
                return resp
            if "Content-Encoding" in resp.headers:
                return resp
            ctype = (resp.content_type or "").split(";")[0].strip().lower()
            if not any(ctype.startswith(p) for p in _COMPRESSIBLE_PREFIXES):
                return resp
            # Materialise Flask's send_from_directory file-iterator response
            # into bytes so we can re-emit it compressed. We do this *before*
            # `get_data()` because Werkzeug refuses to read the body of a
            # direct_passthrough response otherwise. The content-type filter
            # above keeps us out of binary payloads (favicon.ico, png).
            if resp.direct_passthrough:
                try:
                    materialised = b"".join(
                        chunk if isinstance(chunk, bytes) else bytes(chunk)
                        for chunk in resp.response
                    )
                except Exception:
                    return resp
                resp.response = [materialised]
                resp.direct_passthrough = False
            data = resp.get_data()
            if len(data) < _MIN_BYTES:
                return resp
            buf = BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as gz:
                gz.write(data)
            compressed = buf.getvalue()
            if len(compressed) >= len(data):
                # Compression didn't help (already-compressed payload, etc.).
                return resp
            resp.set_data(compressed)
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Content-Length"] = str(len(compressed))
            vary = resp.headers.get("Vary")
            if not vary:
                resp.headers["Vary"] = "Accept-Encoding"
            elif "accept-encoding" not in vary.lower():
                resp.headers["Vary"] = vary + ", Accept-Encoding"
        except Exception:  # pragma: no cover — never let compression break a response
            return resp
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
    """Session hardening, ProxyFix, security headers and bfcache defence."""
    validate_production_secret(flask_server.secret_key)
    # Engine dispose is useful in both dev and prod (avoids stale pooled
    # connections when workers recycle) and cheap otherwise.
    _install_graceful_shutdown()
    # Cache + auth gate run in dev too — they are the core defence against
    # session-leak / back-button-after-logout bugs and add no real cost.
    _install_no_cache_headers(flask_server)
    _install_session_redirect(flask_server)
    # Compression runs in dev too so we exercise the same code path locally
    # that ships to production. Negligible CPU cost vs. the 60-70% bandwidth
    # win on JS/CSS/JSON.
    _install_gzip_compression(flask_server)
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
