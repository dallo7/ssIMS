import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import insert_alert_acknowledgment, list_alerts_with_ack_state
from database.engine import db_session

register_page(__name__, path="/monitoring", name="Monitoring", title="Alerts", order=8)


def _uid():
    return int(session.get("user_id") or 1)


layout = dmc.Stack(
    [
        dcc.Store(id="mon-version", data=0),
        dmc.Title("Monitoring & alerting", order=3),
        dmc.Button("Refresh", id="mon-refresh", variant="light"),
        dmc.Text(id="mon-summary", size="sm", c="dimmed"),
        html.Div(id="mon-list"),
    ],
    gap="md",
)


@callback(
    Output("mon-list", "children"),
    Output("mon-summary", "children"),
    Input("url", "pathname"),
    Input("mon-version", "data"),
    Input("mon-refresh", "n_clicks"),
)
def mon_load(pathname, _v, _r):
    if "/monitoring" not in (pathname or ""):
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    with db_session() as s:
        rows = list_alerts_with_ack_state(s, 200)
    open_a = [r for r in rows if not r["acknowledged"]]
    cards = []
    for r in rows[:50]:
        color = "red" if r["severity"] == "CRITICAL" else "yellow" if r["severity"] == "WARNING" else "blue"
        cards.append(
            dmc.Card(
                withBorder=True,
                padding="sm",
                mb="xs",
                children=dmc.Group(
                    [
                        dmc.Stack([dmc.Badge(r["severity"], color=color, size="sm"), dmc.Text(r["message"], size="sm")], gap=4),
                        dmc.Button(
                            "Acknowledge",
                            id={"type": "ack-alert", "id": r["id"]},
                            size="xs",
                            variant="light",
                            disabled=r["acknowledged"],
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
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    t = ctx.triggered_id
    if not (isinstance(t, dict) and t.get("type") == "ack-alert"):
        raise PreventUpdate
    aid = int(t["id"])
    with db_session() as s:
        insert_alert_acknowledgment(s, alert_log_id=aid, user_id=_uid())
    return (ver or 0) + 1
