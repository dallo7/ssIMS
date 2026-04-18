import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import evaluate_alerts, insert_alert_acknowledgment, list_alerts_with_ack_state
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.auth import session_user_id_for_write
from utils.navigation import normalize_path

register_page(__name__, path="/monitoring", name="Monitoring", title="Alerts", order=8)

_mon_t, _mon_h = i18n.page_heading("en", "monitoring")

layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="mon-version", data=0),
        html.Div(id="monitoring-page-header", children=page_header(_mon_t, help=_mon_h)),
        dmc.Paper(
            className="cpi-toolbar-paper",
            p="md",
            radius="md",
            withBorder=True,
            children=dmc.Group(
                [
                    dmc.Button("Refresh", id="mon-refresh", variant="light"),
                    dmc.Text(id="mon-summary", size="sm", c="dimmed"),
                ],
                align="center",
                justify="space-between",
                wrap="wrap",
                gap="md",
            ),
        ),
        html.Div(id="mon-list"),
    ],
)


@callback(
    Output("monitoring-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def monitoring_page_header(pathname, loc):
    if normalize_path(pathname) != "/monitoring":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "monitoring")
    return page_header(t, help=h)


@callback(
    Output("mon-list", "children"),
    Output("mon-summary", "children"),
    Input("_pages_location", "pathname"),
    Input("mon-version", "data"),
    Input("mon-refresh", "n_clicks"),
)
def mon_load(pathname, _v, _r):
    if "/monitoring" not in (pathname or ""):
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    with db_session() as s:
        evaluate_alerts(s)
        rows = list_alerts_with_ack_state(s, 200)
    open_a = [r for r in rows if not r["acknowledged"]]
    cards = []
    role = session.get("role", "VIEWER")
    can_ack = role in ("ADMIN", "MANAGER", "STOCK_CLERK")
    for r in rows[:50]:
        color = "red" if r["severity"] == "CRITICAL" else "yellow" if r["severity"] == "WARNING" else "blue"
        cards.append(
            dmc.Card(
                withBorder=True,
                padding="md",
                mb="sm",
                radius="md",
                children=dmc.Group(
                    [
                        dmc.Stack([dmc.Badge(r["severity"], color=color, size="sm"), dmc.Text(r["message"], size="sm")], gap=4),
                        dmc.Button(
                            "Acknowledge",
                            id={"type": "ack-alert", "id": r["id"]},
                            size="xs",
                            variant="light",
                            disabled=r["acknowledged"] or not can_ack,
                        ),
                    ],
                    justify="space-between",
                    align="flex-start",
                ),
            )
        )
    return dmc.Stack(cards, gap="xs"), f"{len(open_a)} open / {len(rows)} recent in view"


@callback(
    Output("mon-version", "data"),
    Input({"type": "ack-alert", "id": dash.ALL}, "n_clicks"),
    State("mon-version", "data"),
    prevent_initial_call=True,
)
def mon_ack(_clicks, ver):
    if session.get("role") == "VIEWER":
        raise PreventUpdate
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    t = ctx.triggered_id
    if not (isinstance(t, dict) and t.get("type") == "ack-alert"):
        raise PreventUpdate
    aid = int(t["id"])
    with db_session() as s:
        uid = session_user_id_for_write(s)
        if uid is None:
            if session.get("user_id"):
                session.clear()
            raise PreventUpdate
        insert_alert_acknowledgment(s, alert_log_id=aid, user_id=uid)
    return (ver or 0) + 1
