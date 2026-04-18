"""
Stock inventory web app (Plotly Dash + Flask). Run: python app.py
Optional: CPI_USE_UVICORN=1 python app.py  or  uvicorn asgi:application --host 127.0.0.1 --port 8050
"""
from __future__ import annotations

import os

import dash

from utils.logging_config import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

# Mantine / DMC ≥0.14 needs React 18 (useId). Dash 2.x defaults to React 16 unless set here.
dash._dash_renderer._set_react_version("18.2.0")

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, page_container
from dash.exceptions import PreventUpdate
from flask import session
from dash_iconify import DashIconify

from components.layout import sidebar
from components.theme import merge_theme
from database.dal import list_alerts_with_ack_state
from database.engine import db_session, init_database
from database.seed import seed_if_empty
from utils.auth import current_user, prune_invalid_session
from utils import i18n
from utils.app_text import primary_app_name
from utils.server_config import apply_flask_server_settings, is_production_env
from utils.navigation import can_access_path, normalize_path
from routes.api_v1 import bp as cpi_api_v1_bp
from routes.public import bp as cpi_public_bp

# Initialize schema before ORM use.
log.info("Boot: initializing database schema.")
init_database()
seed_if_empty()
log.info("Boot: database ready (env=%s).", os.environ.get("CPI_ENV", "development") or "development")

_default_alert_eval = "0" if is_production_env() else "1"
if os.environ.get("CPI_ALERT_EVAL_ON_START", _default_alert_eval).strip().lower() in ("1", "true", "yes"):
    try:
        from database.dal import evaluate_alerts as _evaluate_alerts_on_boot

        with db_session() as _s:
            _evaluate_alerts_on_boot(_s)
    except Exception:
        # Boot must not fail on a transient DAL error; surface in logs instead.
        log.warning("Initial alert evaluation failed; continuing boot.", exc_info=True)

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    suppress_callback_exceptions=True,
    title=primary_app_name(),
    update_title=None,
)
app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/x-icon" href="/assets/favicon.ico"/>
        <link rel="icon" type="image/png" sizes="256x256" href="/assets/capitalpay-logo.png"/>
        {%favicon%}
        {%css%}
    </head>
    <body>
        <!--[if IE]><script>
        alert("Dash v2.7+ does not support Internet Explorer. Please use a newer browser.");
        </script><![endif]-->
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""
server = app.server
server.secret_key = os.environ.get("CPI_SECRET_KEY", "dev-cpi-inventory-change-me")
server.register_blueprint(cpi_api_v1_bp, url_prefix="/api/v1")
# Public, Dash-free pages. The Flask URL matcher prefers these static rules
# over Dash's catch-all for /<path:path>, so /welcome and /login skip the
# entire SPA bundle (Mantine + AgGrid + dash-renderer) and paint instantly.
server.register_blueprint(cpi_public_bp)
apply_flask_server_settings(server)


# Server-side logout. A real HTTP route (not a Dash callback) so the browser
# performs a full navigation, the response sets Clear-Site-Data + drops the
# session cookie, and the back button can no longer reveal the prior view.
@server.route("/logout", methods=["GET", "POST"])
def server_logout():
    from flask import make_response, redirect as flask_redirect, session as flask_session

    flask_session.clear()
    # Land on the public landing page after logout so the user sees the
    # marketing copy first and can choose to sign in again from there.
    resp = make_response(flask_redirect("/welcome", code=302))
    cookie_name = server.config.get("SESSION_COOKIE_NAME", "session")
    # Best-effort cookie deletion — covers both the Flask default cookie name
    # and any alternative configured via SESSION_COOKIE_NAME.
    resp.delete_cookie(cookie_name, path="/")
    resp.delete_cookie("session", path="/")
    # Tell the browser to discard cached page bodies and any client storage
    # tied to this origin. We deliberately leave 'cookies' off the list here:
    # Flask has already deleted the session cookie, and clearing all cookies
    # would also drop the user's saved language / theme preferences.
    resp.headers["Clear-Site-Data"] = '"cache", "storage"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

_poll_raw = (os.environ.get("CPI_ALERT_POLL_MS") or "").strip()
try:
    _alert_poll_ms = int(_poll_raw) if _poll_raw else (120_000 if is_production_env() else 60_000)
except ValueError:
    _alert_poll_ms = 120_000 if is_production_env() else 60_000
_alert_poll_ms = max(30_000, min(_alert_poll_ms, 600_000))

app.layout = html.Div(
    [
        dcc.Store(id="theme-store", storage_type="local", data={"scheme": "light"}),
        dcc.Store(id="locale-store", storage_type="local", data={"lang": "en"}),
        dcc.Store(id="cpi-inventory-refresh", data=0),
        dcc.Store(id="alert-badge-store", data=0),
        dcc.Interval(id="alert-interval", interval=_alert_poll_ms, n_intervals=0),
        html.Div(id="guard-redirect"),
        html.Div(id="logout-redirect"),
        html.Div(id="rbac-redirect-container"),
        dmc.MantineProvider(
            id="mantine-root",
            theme=merge_theme("light", direction="ltr"),
            forceColorScheme="light",
            children=[
                html.Div(
                    id="lang-float-wrap",
                    className="cpi-lang-float-wrap",
                    children=[
                        dmc.Select(
                            id="app-lang-float",
                            data=i18n.LANG_SELECT_DATA,
                            value="en",
                            size="xs",
                            w=176,
                            radius="md",
                            clearable=False,
                        ),
                    ],
                ),
                dmc.Grid(
                    id="root-grid",
                    gutter=0,
                    children=[
                        dmc.GridCol(
                            id="sidebar-col",
                            span={"base": 12, "sm": 3, "md": 2},
                            # Hidden in initial HTML so the first paint of /login
                            # and /welcome never shows the authenticated chrome.
                            # `layout_responsive` reveals this column on protected
                            # paths once the auth callback confirms a session.
                            style={"padding": 0, "display": "none"},
                            children=html.Div(id="sidebar-inner"),
                        ),
                        dmc.GridCol(
                            id="main-col",
                            span={"base": 12, "sm": 9, "md": 10},
                            style={
                                "padding": 0,
                                "minWidth": 0,
                                "background": "var(--mantine-color-body)",
                            },
                            children=dmc.Stack(
                                gap=0,
                                align="stretch",
                                style={
                                    "minHeight": "100vh",
                                    "width": "100%",
                                    "display": "flex",
                                    "flexDirection": "column",
                                },
                                children=[
                                    dmc.Paper(
                                        id="header-row",
                                        className="cpi-header-bar",
                                        shadow="xs",
                                        px={"base": "sm", "sm": "md"},
                                        py="sm",
                                        radius=0,
                                        withBorder=False,
                                        # Hidden in initial HTML — the
                                        # `header_visibility` callback reveals
                                        # this on protected paths only. This
                                        # eliminates the brief flash of the
                                        # logged-in header on /login and /welcome.
                                        style={
                                            "borderBottom": "1px solid var(--cpi-chrome-border, var(--mantine-color-gray-3))",
                                            "flexShrink": 0,
                                            "display": "none",
                                        },
                                        children=dmc.Group(
                                            [
                                                dmc.Stack(
                                                    [
                                                        dmc.Title(
                                                            id="header-app-title",
                                                            children=primary_app_name(),
                                                            order=4,
                                                            fw=600,
                                                        ),
                                                        dmc.Text(
                                                            id="header-workspace",
                                                            children="",
                                                            size="xs",
                                                            c="dimmed",
                                                        ),
                                                    ],
                                                    gap=2,
                                                    style={"flex": 1, "minWidth": 0},
                                                ),
                                                dmc.Group(
                                                    [
                                                        dmc.Select(
                                                            id="header-lang",
                                                            data=i18n.LANG_SELECT_DATA,
                                                            value="en",
                                                            size="xs",
                                                            w=168,
                                                            radius="md",
                                                            clearable=False,
                                                        ),
                                                        dmc.ActionIcon(
                                                            DashIconify(
                                                                icon="tabler:sun",
                                                                width=20,
                                                            ),
                                                            id="btn-theme-toggle",
                                                            variant="subtle",
                                                            color="gray",
                                                            size="md",
                                                        ),
                                                        dmc.Tooltip(
                                                            label="User guide",
                                                            position="bottom",
                                                            withArrow=True,
                                                            children=html.A(
                                                                dmc.ActionIcon(
                                                                    DashIconify(
                                                                        icon="tabler:help-circle",
                                                                        width=20,
                                                                    ),
                                                                    variant="subtle",
                                                                    color="gray",
                                                                    size="md",
                                                                ),
                                                                id="header-user-guide-link",
                                                                href="/assets/tutorials/index.html",
                                                                target="_blank",
                                                                rel="noopener noreferrer",
                                                                style={
                                                                    "display": "inline-flex",
                                                                    "textDecoration": "none",
                                                                },
                                                            ),
                                                        ),
                                                        dmc.Button(
                                                            "Log out",
                                                            id="btn-logout",
                                                            variant="subtle",
                                                            color="gray",
                                                            size="xs",
                                                        ),
                                                    ],
                                                    gap="xs",
                                                ),
                                            ],
                                            justify="space-between",
                                            align="center",
                                        ),
                                    ),
                                    dmc.Box(
                                        className="cpi-main-page-shell",
                                        p={"base": "sm", "sm": "md"},
                                        style={
                                            "flex": "1 1 auto",
                                            "minWidth": 0,
                                            "minHeight": 0,
                                            "overflow": "auto",
                                            "width": "100%",
                                        },
                                        children=page_container,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ]
)


@callback(
    Output("guard-redirect", "children"),
    Input("_pages_location", "pathname"),
)
def auth_guard(pathname: str | None):
    p = normalize_path(pathname)
    # /welcome is always public (marketing landing). /login is public for
    # unauthenticated visitors; an already-logged-in user that lands on /login
    # (e.g. via Back button after their session restored) is forwarded to the
    # dashboard so the chrome doesn't briefly disappear/reappear.
    if p == "/welcome":
        return dash.no_update
    if p == "/login":
        if session.get("user_id"):
            prune_invalid_session()
            if session.get("user_id"):
                return dcc.Location(pathname="/", id="auth-loc", refresh=True)
        return dash.no_update
    if not session.get("user_id"):
        return dcc.Location(pathname="/welcome", id="auth-loc", refresh=True)
    prune_invalid_session()
    if not session.get("user_id"):
        return dcc.Location(pathname="/welcome", id="auth-loc", refresh=True)
    return dash.no_update


@callback(
    Output("rbac-redirect-container", "children"),
    Input("_pages_location", "pathname"),
)
def rbac_guard(pathname: str | None):
    pathname = pathname or ""
    if "/login" in pathname or not session.get("user_id"):
        return []
    u = current_user()
    if not u:
        return []
    p = normalize_path(pathname)
    if not can_access_path(u.get("role"), p):
        return [dcc.Location(pathname="/", id="rbac-loc", refresh=True)]
    return []


@callback(
    Output("header-app-title", "children"),
    Output("header-workspace", "children"),
    Output("btn-logout", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def header_i18n(_pathname, loc):
    lang = i18n.normalize_lang(loc)
    u = current_user()
    if not u:
        return dash.no_update, "", dash.no_update
    return (
        primary_app_name(),
        i18n.workspace_label(u.get("role"), lang),
        i18n.t(lang, "logout"),
    )


@callback(
    Output("mantine-root", "theme"),
    Output("mantine-root", "forceColorScheme"),
    Input("theme-store", "data"),
    Input("locale-store", "data"),
)
def apply_theme(theme_data: dict | None, locale_data: dict | None):
    scheme = (theme_data or {}).get("scheme", "light")
    lang = i18n.normalize_lang(locale_data)
    direction = i18n.text_direction(lang)
    return merge_theme(scheme, direction=direction), scheme


@callback(
    Output("sidebar-col", "style"),
    Output("main-col", "span"),
    Input("_pages_location", "pathname"),
)
def layout_responsive(pathname: str | None):
    pathname = pathname or ""
    # Sidebar is hidden by default in the initial HTML; reveal it only once
    # we know the user is authenticated AND on a chrome-bearing page.
    if "/login" in pathname or "/welcome" in pathname or not session.get("user_id"):
        return {"display": "none"}, {"base": 12, "sm": 12, "md": 12}
    return {"display": "block", "padding": 0}, {"base": 12, "sm": 9, "md": 10}


@callback(
    Output("sidebar-inner", "children"),
    Input("_pages_location", "pathname"),
    Input("alert-badge-store", "data"),
    Input("locale-store", "data"),
)
def chrome_sidebar(pathname: str | None, alert_n: int | None, loc: dict | None):
    pathname = pathname or ""
    u = current_user()
    if "/login" in pathname or "/welcome" in pathname or not u:
        return []
    ac = int(alert_n or 0)
    lang = i18n.normalize_lang(loc)
    return sidebar(u, ac, current_path=pathname, lang=lang)


@callback(
    Output("header-row", "style"),
    Input("_pages_location", "pathname"),
    Input("theme-store", "data"),
)
def header_visibility(pathname: str | None, _theme):
    pathname = pathname or ""
    base = {
        "borderBottom": "1px solid var(--cpi-chrome-border, var(--mantine-color-gray-3))",
        "flexShrink": 0,
    }
    # Public pages keep the chrome hidden, matching the initial-HTML default.
    # Anything else only reveals the header once we know the user is logged in;
    # the auth_guard callback will redirect non-authenticated requests away.
    if "/login" in pathname or "/welcome" in pathname:
        return {**base, "display": "none"}
    if not session.get("user_id"):
        return {**base, "display": "none"}
    return {**base, "display": "block"}


@callback(
    Output("header-user-guide-link", "href"),
    Input("_pages_location", "pathname"),
)
def user_guide_href(_pathname):
    role = (session.get("role") or "").upper()
    base = "/assets/tutorials/"
    if role == "ADMIN":
        return base + "admin-guide.html"
    if role == "MANAGER":
        return base + "manager-guide.html"
    if role == "STOCK_CLERK":
        return base + "stock-clerk-guide.html"
    return base + "index.html"


@callback(
    Output("btn-theme-toggle", "children"),
    Input("theme-store", "data"),
)
def theme_icon(data: dict | None):
    scheme = (data or {}).get("scheme", "light")
    icon = "tabler:moon" if scheme == "light" else "tabler:sun"
    return DashIconify(icon=icon, width=22)


@callback(
    Output("theme-store", "data"),
    Input("btn-theme-toggle", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def toggle_theme(_n, data):
    cur = (data or {}).get("scheme", "light")
    nxt = "dark" if cur == "light" else "light"
    return {"scheme": nxt}


@callback(
    Output("logout-redirect", "children"),
    Input("btn-logout", "n_clicks"),
    prevent_initial_call=True,
)
def logout_cb(_n):
    """Hand off to the /logout Flask route so the server can clear the cookie,
    emit Clear-Site-Data, and the browser performs a real navigation that
    cannot be served from bfcache. We also clear the session here as a belt
    in case the route handler is short-circuited by middleware."""
    session.clear()
    return dcc.Location(href="/logout", id="lo-loc", refresh=True)


@callback(
    Output("locale-store", "data"),
    Output("app-lang-float", "value"),
    Output("header-lang", "value"),
    Input("locale-store", "data"),
    Input("app-lang-float", "value"),
    Input("header-lang", "value"),
)
def sync_locale(loc_data, v_float, v_head):
    """Single callback avoids locale-store ↔ select value dependency cycle."""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    tid = ctx.triggered_id
    if tid is None or (ctx.triggered and ctx.triggered[0].get("prop_id") == "."):
        lang = i18n.normalize_lang(loc_data)
        return dash.no_update, lang, lang
    if tid == "locale-store":
        lang = i18n.normalize_lang(loc_data)
        return dash.no_update, lang, lang
    if tid == "app-lang-float":
        lang = i18n.normalize_lang({"lang": v_float})
        return {"lang": lang}, dash.no_update, lang
    if tid == "header-lang":
        lang = i18n.normalize_lang({"lang": v_head})
        return {"lang": lang}, lang, dash.no_update
    raise PreventUpdate


@callback(
    Output("lang-float-wrap", "style"),
    Input("_pages_location", "pathname"),
)
def lang_float_visibility(pathname: str | None):
    pathname = pathname or ""
    if "/login" in pathname or "/welcome" in pathname:
        # Nudge down from the very top so the floating language selector does
        # not overlap the login card's Sign In button on short viewports.
        return {
            "position": "fixed",
            "top": "56px",
            "right": "16px",
            "zIndex": 500,
            "width": "188px",
        }
    return {"display": "none"}


@callback(
    Output("alert-badge-store", "data"),
    Input("alert-interval", "n_intervals"),
    Input("_pages_location", "pathname"),
)
def refresh_alerts(_n, pathname: str | None):
    if not session.get("user_id"):
        raise PreventUpdate
    try:
        with db_session() as s:
            # Full evaluate_alerts() scans all SKUs; do not run that on every 60s poll (see
            # CPI_ALERT_EVAL_ON_START, monitoring page load, and optional CPI_ALERT_EVAL_INTERVAL_TICKS).
            _def_ticks = "30" if is_production_env() else "15"
            _ticks = int(os.environ.get("CPI_ALERT_EVAL_INTERVAL_TICKS", _def_ticks) or _def_ticks)
            if _ticks > 0 and _n and int(_n) % _ticks == 0:
                try:
                    from database.dal import evaluate_alerts as _eval

                    _eval(s)
                except Exception:
                    log.warning(
                        "Periodic alert evaluation failed at tick %s.",
                        _n,
                        exc_info=True,
                    )
            rows = list_alerts_with_ack_state(s, limit=100)
            open_alerts = sum(1 for r in rows if not r["acknowledged"])
        return open_alerts
    except Exception:
        log.warning("Alert badge refresh failed; reporting 0.", exc_info=True)
        return 0


if __name__ == "__main__":
    # Flask dev server is the default for Dash (callbacks + Pages).
    # Production: use gunicorn/waitress + wsgi:application (see README).
    _host = os.environ.get("CPI_HOST", "127.0.0.1").strip() or "127.0.0.1"
    _port = int(os.environ.get("CPI_PORT", "8050") or "8050")
    _prod = os.environ.get("CPI_ENV", "").strip().lower() in ("production", "prod", "live")
    _debug = (not _prod) and os.environ.get("CPI_DEBUG", "true").strip().lower() in ("1", "true", "yes")

    if os.environ.get("CPI_USE_UVICORN", "").lower() in ("1", "true", "yes"):
        import uvicorn

        uvicorn.run(
            "asgi:application",
            host=_host,
            port=_port,
            reload=_debug and _host in ("127.0.0.1", "localhost"),
        )
    else:
        # use_reloader=False avoids double-import side effects with Dash pages + DB init.
        app.run(
            debug=_debug,
            host=_host,
            port=_port,
            use_reloader=False,
            threaded=True,
        )
