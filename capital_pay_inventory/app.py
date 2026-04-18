"""
Smart-Shop Stock Inventory Management System, powered by CapitalPay (South Sudan).
Run: python app.py
"""
from __future__ import annotations

import os

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, page_container
from dash.exceptions import PreventUpdate
from flask import session
from dash_iconify import DashIconify

from components.layout import sidebar
from components.theme import merge_theme
from database.dal import list_alerts_with_ack_state
from database.engine import db_session
from database.seed import seed_if_empty
from utils.auth import current_user

seed_if_empty()

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    suppress_callback_exceptions=True,
    title="Smart-Shop Stock Inventory",
    update_title=None,
)
app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/png" href="/assets/capitalpay-logo.png"/>
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

app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="theme-store", storage_type="local", data={"scheme": "light"}),
        dcc.Store(id="alert-badge-store", data=0),
        dcc.Interval(id="alert-interval", interval=60_000, n_intervals=0),
        html.Div(id="guard-redirect"),
        html.Div(id="logout-redirect"),
        dmc.MantineProvider(
            id="mantine-root",
            theme=merge_theme("light"),
            forceColorScheme="light",
            children=[
                dmc.Grid(
                    id="root-grid",
                    gutter=0,
                    children=[
                        dmc.GridCol(
                            id="sidebar-col",
                            span={"base": 12, "sm": 3, "md": 2},
                            style={"padding": 0},
                            children=html.Div(id="sidebar-inner"),
                        ),
                        dmc.GridCol(
                            id="main-col",
                            span={"base": 12, "sm": 9, "md": 10},
                            style={"padding": 0, "minHeight": "100vh", "background": "var(--mantine-color-body)"},
                            children=[
                                dmc.Paper(
                                    id="header-row",
                                    shadow="xs",
                                    p="sm",
                                    radius=0,
                                    withBorder=False,
                                    style={"borderBottom": "1px solid var(--mantine-color-gray-3)"},
                                    children=dmc.Group(
                                        [
                                            dmc.Title(
                                                "Smart-Shop Stock Inventory",
                                                order=4,
                                                style={"flex": 1},
                                            ),
                                            dmc.Group(
                                                [
                                                    dmc.ActionIcon(
                                                        DashIconify(
                                                            icon="tabler:sun",
                                                            width=22,
                                                        ),
                                                        id="btn-theme-toggle",
                                                        variant="light",
                                                        color="cpi",
                                                        size="lg",
                                                    ),
                                                    dmc.Button(
                                                        "Logout",
                                                        id="btn-logout",
                                                        variant="subtle",
                                                        color="red",
                                                        size="sm",
                                                    ),
                                                ],
                                                gap="xs",
                                            ),
                                        ],
                                        justify="space-between",
                                        align="center",
                                    ),
                                ),
                                page_container,
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ]
)


@callback(
    Output("guard-redirect", "children"),
    Input("url", "pathname"),
)
def auth_guard(pathname: str | None):
    pathname = (pathname or "/").rstrip("/") or "/"
    if pathname == "/login":
        return dash.no_update
    if not session.get("user_id"):
        return dcc.Location(pathname="/login", id="auth-loc", refresh=True)
    return dash.no_update


@callback(
    Output("mantine-root", "theme"),
    Output("mantine-root", "forceColorScheme"),
    Input("theme-store", "data"),
)
def apply_theme(data: dict | None):
    scheme = (data or {}).get("scheme", "light")
    return merge_theme(scheme), scheme


@callback(
    Output("sidebar-col", "style"),
    Output("main-col", "span"),
    Input("url", "pathname"),
)
def layout_responsive(pathname: str | None):
    pathname = pathname or ""
    if "/login" in pathname:
        return {"display": "none"}, {"base": 12, "sm": 12, "md": 12}
    return {"display": "block", "padding": 0}, {"base": 12, "sm": 9, "md": 10}


@callback(
    Output("sidebar-inner", "children"),
    Input("url", "pathname"),
    Input("alert-badge-store", "data"),
)
def chrome_sidebar(pathname: str | None, alert_n: int | None):
    pathname = pathname or ""
    u = current_user()
    if "/login" in pathname or not u:
        return []
    ac = int(alert_n or 0)
    return sidebar(u, ac)


@callback(
    Output("header-row", "style"),
    Input("url", "pathname"),
    Input("theme-store", "data"),
)
def header_visibility(pathname: str | None, _theme):
    pathname = pathname or ""
    base = {"borderBottom": "1px solid var(--mantine-color-gray-3)"}
    if "/login" in pathname:
        return {**base, "display": "none"}
    return {**base, "display": "block"}


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
    session.clear()
    return dcc.Location(pathname="/login", id="lo-loc", refresh=True)


@callback(
    Output("alert-badge-store", "data"),
    Input("alert-interval", "n_intervals"),
    Input("url", "pathname"),
)
def refresh_alerts(_n, pathname: str | None):
    if not session.get("user_id"):
        raise PreventUpdate
    with db_session() as s:
        try:
            from database.dal import evaluate_alerts as _eval

            _eval(s)
        except Exception:
            pass
        rows = list_alerts_with_ack_state(s, limit=100)
        open_alerts = sum(1 for r in rows if not r["acknowledged"])
    return open_alerts


if __name__ == "__main__":
    app.run(debug=True, port=8050)
