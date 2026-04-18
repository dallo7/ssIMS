import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import list_activity, set_config
from database.engine import db_session

register_page(__name__, path="/config", name="Configuration", title="Configuration", order=10)


def _ok():
    return session.get("role") in ("ADMIN", "MANAGER")


layout = dmc.Stack(
    [
        dmc.Title("System configuration", order=3),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Alert thresholds", fw=600, mb="sm"),
                        dmc.NumberInput(id="cfg-expiry", label="Expiry warning (days)", min=1, value=30),
                        dmc.NumberInput(id="cfg-audit", label="Audit overdue (days)", min=1, value=60),
                        dmc.NumberInput(id="cfg-dead", label="Dead stock (days)", min=1, value=60),
                        dmc.Button("Save configuration", id="cfg-save", color="cpi"),
                        html.Div(id="cfg-feedback"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Database backup", fw=600, mb="sm"),
                        dmc.Text(
                            id="cfg-backup-hint",
                            size="sm",
                            c="dimmed",
                            style={},
                            children="PostgreSQL is enabled. Use pg_dump/pg_restore for backups.",
                        ),
                        dcc.Download(id="cfg-dl"),
                    ],
                ),
            ],
        ),
        dmc.Card(
            withBorder=True,
            padding="md",
            children=[
                dmc.Text("Activity log (append-only)", fw=600, mb="sm"),
                html.Div(id="cfg-activity"),
            ],
        ),
    ],
    gap="md",
)


@callback(
    Output("cfg-activity", "children"),
    Input("url", "pathname"),
)
def cfg_act(pathname):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    with db_session() as s:
        rows = list_activity(s, 80)
    head = html.Tr([html.Th("Time"), html.Th("Action"), html.Th("Entity"), html.Th("Details")])
    body = [
        html.Tr(
            [
                html.Td(r.created_at.isoformat()[:19] if r.created_at else ""),
                html.Td(r.action),
                html.Td((r.entity_type or "") + (f" #{r.entity_id}" if r.entity_id else "")),
                html.Td((r.details or "")[:80]),
            ]
        )
        for r in rows
    ]
    return dmc.Table(striped=True, highlightOnHover=True, children=[html.Thead(head), html.Tbody(body)])


@callback(
    Output("cfg-backup-hint", "style"),
    Input("url", "pathname"),
)
def cfg_backup_ui(pathname):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    return {}


@callback(
    Output("cfg-feedback", "children"),
    Input("cfg-save", "n_clicks"),
    State("cfg-expiry", "value"),
    State("cfg-audit", "value"),
    State("cfg-dead", "value"),
    prevent_initial_call=True,
)
def cfg_save(_n, ex, au, dd):
    if not _ok():
        raise PreventUpdate
    uid = int(session.get("user_id") or 0)
    with db_session() as s:
        set_config(s, "expiry_warning_days", str(int(ex or 30)), uid)
        set_config(s, "audit_overdue_days", str(int(au or 60)), uid)
        set_config(s, "dead_stock_days", str(int(dd or 60)), uid)
    return dmc.Alert("Configuration saved.", color="green", title="OK")
