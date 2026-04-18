import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import create_user
from database.engine import db_session
from utils.auth import hash_password

register_page(__name__, path="/users", name="Users", title="Users", order=9)


def _admin():
    return session.get("role") == "ADMIN"


layout = dmc.Stack(
    [
        dcc.Store(id="usr-version", data=0),
        dmc.Title("User management (RBAC)", order=3),
        dmc.Alert("Only ADMIN may create users. Default roles: ADMIN, MANAGER, STOCK_CLERK, VIEWER.", color="blue", title="Policy"),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.TextInput(id="usr-name", label="Username"),
                        dmc.PasswordInput(id="usr-pass", label="Temporary password"),
                        dmc.TextInput(id="usr-full", label="Full name"),
                        dmc.Select(id="usr-role", label="Role", data=[], value=None),
                        dmc.Button("Create user", id="usr-create", color="cpi"),
                    ],
                ),
                dmc.Card(withBorder=True, padding="md", children=[html.Div(id="usr-table")]),
            ],
        ),
    ],
    gap="md",
)


@callback(
    Output("usr-table", "children"),
    Output("usr-role", "data"),
    Output("usr-role", "value"),
    Input("url", "pathname"),
    Input("usr-version", "data"),
)
def usr_list(pathname, _v):
    if "/users" not in (pathname or ""):
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    with db_session() as s:
        users = s.scalars(select(models.User)).all()
        roles = {r.id: r.name for r in s.scalars(select(models.Role)).all()}
        role_opts = [{"label": f"{r.name}", "value": str(r.id)} for r in s.scalars(select(models.Role)).all()]
        viewer = next((str(r.id) for r in s.scalars(select(models.Role)).all() if r.name == "VIEWER"), None)
    head = html.Tr([html.Th("User"), html.Th("Name"), html.Th("Role"), html.Th("Active")])
    body = [
        html.Tr([html.Td(u.username), html.Td(u.full_name), html.Td(roles.get(u.role_id)), html.Td("yes" if u.is_active else "no")])
        for u in users
    ]
    return (
        dmc.Table(striped=True, highlightOnHover=True, children=[html.Thead(head), html.Tbody(body)]),
        role_opts,
        viewer,
    )


@callback(
    Output("usr-version", "data"),
    Input("usr-create", "n_clicks"),
    State("usr-version", "data"),
    State("usr-name", "value"),
    State("usr-pass", "value"),
    State("usr-full", "value"),
    State("usr-role", "value"),
    prevent_initial_call=True,
)
def usr_create(_n, ver, un, pw, full, rid):
    if not _admin():
        raise PreventUpdate
    if not un or not pw or not full or not rid:
        raise PreventUpdate
    with db_session() as s:
        create_user(s, username=un, password_hash=hash_password(pw), full_name=full, role_id=int(rid), actor_id=int(session.get("user_id")))
    return (ver or 0) + 1
