import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import models
from database.dal import create_user
from database.engine import db_session
from utils.auth import hash_password
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/users", name="Users", title="Users", order=9)

_usr_t, _usr_h = i18n.page_heading("en", "users")


def _admin():
    return session.get("role") == "ADMIN"


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="usr-version", data=0),
        html.Div(id="users-page-header", children=page_header(_usr_t, help=_usr_h)),
        dmc.Alert("Only ADMIN may create users. Default roles: ADMIN, MANAGER, STOCK_CLERK, VIEWER.", color="blue", title="Policy"),
        html.Div(id="usr-feedback"),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    className="cpi-users-form-card",
                    children=[
                        dmc.Text("New account", fw=700, size="sm", tt="uppercase", mb="xs"),
                        dmc.Text("Credentials and role for the new sign-in.", size="xs", c="dimmed", mb="md"),
                        dmc.Stack(
                            gap="md",
                            children=[
                                dmc.TextInput(id="usr-name", label="Username", radius="md"),
                                dmc.PasswordInput(id="usr-pass", label="Temporary password", radius="md"),
                                dmc.TextInput(id="usr-full", label="Full name", radius="md"),
                                dmc.Select(
                                    id="usr-role",
                                    label="Role",
                                    data=[],
                                    value=None,
                                    radius="md",
                                    searchable=True,
                                ),
                                dmc.Button(
                                    "Create user",
                                    id="usr-create",
                                    color="cpi",
                                    radius="md",
                                    fullWidth=True,
                                    mt="lg",
                                ),
                            ],
                        ),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    className="cpi-users-directory-card",
                    children=[
                        dmc.Text("Team directory", fw=700, size="sm", tt="uppercase", mb="xs"),
                        dmc.Text("All accounts in the system.", size="xs", c="dimmed", mb="md"),
                        html.Div(id="usr-table", className="cpi-users-table-wrap"),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("users-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def users_page_header(pathname, loc):
    if normalize_path(pathname) != "/users":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "users")
    return page_header(t, help=h)


@callback(
    Output("usr-table", "children"),
    Output("usr-role", "data"),
    Output("usr-role", "value"),
    Input("_pages_location", "pathname"),
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
    head = html.Tr(
        [
            html.Th("User"),
            html.Th("Name"),
            html.Th("Role"),
            html.Th("Active", style={"textAlign": "center"}),
        ]
    )
    body = [
        html.Tr(
            [
                html.Td(dmc.Text(u.username, fw=500, size="sm")),
                html.Td(dmc.Text(u.full_name, size="sm", lineClamp=2)),
                html.Td(
                    dmc.Badge(
                        roles.get(u.role_id) or "—",
                        size="sm",
                        variant="light",
                        color="navy",
                    )
                ),
                html.Td(
                    dmc.Badge(
                        "Active" if u.is_active else "Inactive",
                        size="sm",
                        variant="dot",
                        color="green" if u.is_active else "gray",
                    ),
                    style={"textAlign": "center"},
                ),
            ]
        )
        for u in users
    ]
    tbl = dmc.Table(
        striped=True,
        highlightOnHover=True,
        verticalSpacing="sm",
        horizontalSpacing="md",
        withTableBorder=True,
        withColumnBorders=True,
        stickyHeader=True,
        stickyHeaderOffset=0,
        className="cpi-users-table",
        children=[html.Thead(head), html.Tbody(body)],
    )
    return (
        tbl,
        role_opts,
        viewer,
    )


@callback(
    Output("usr-version", "data"),
    Output("usr-feedback", "children"),
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
        return dash.no_update, dmc.Alert(
            "Your role cannot create users.",
            color="red",
            title="Access denied",
        )
    if not un or not (un.strip()) or not pw or not full or not (full.strip()) or not rid:
        return dash.no_update, dmc.Alert(
            "Username, password, full name, and role are required.",
            color="yellow",
            title="Missing fields",
        )
    try:
        with db_session() as s:
            create_user(
                s,
                username=un.strip(),
                password_hash=hash_password(pw),
                full_name=full.strip(),
                role_id=int(rid),
                actor_id=int(session.get("user_id")),
            )
    except IntegrityError:
        return dash.no_update, dmc.Alert(
            "That username is already taken.",
            color="red",
            title="Duplicate user",
        )
    except Exception as e:
        return dash.no_update, dmc.Alert(
            str(e) or "Could not create user.",
            color="red",
            title="Error",
        )
    return (ver or 0) + 1, dmc.Alert(f"User {un.strip()!r} was created.", color="green", title="Success")
