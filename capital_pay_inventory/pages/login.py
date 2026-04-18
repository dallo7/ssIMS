import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask import session
from sqlalchemy import select

from database import models
from database.dal import insert_activity_log
from database.engine import db_session
from components.branding import capital_pay_logo, powered_by_capitalpay_en
from utils.auth import login_user, verify_password

register_page(__name__, path="/login", name="Login", title="Login", order=99)

layout = dmc.Container(
    [
        dmc.Center(
            style={"minHeight": "85vh"},
            children=dmc.Paper(
                [
                    dmc.Stack(
                        [
                            dmc.Center(children=capital_pay_logo(h=56, radius="md")),
                            dmc.Title("Smart-Shop Stock Inventory", order=2, ta="center"),
                            dmc.Text("Management system", size="sm", c="dimmed"),
                            powered_by_capitalpay_en(text_size="sm"),
                            dmc.Text("South Sudan", size="xs", c="dimmed", opacity=0.75),
                            dmc.TextInput(id="login-user", label="Username", placeholder="admin"),
                            dmc.PasswordInput(id="login-pass", label="Password"),
                            dmc.Button("Sign in", id="login-submit", fullWidth=True, color="cpi"),
                            html.Div(id="login-msg"),
                            dcc.Location(id="login-redirect", refresh=True),
                        ],
                        gap="md",
                    )
                ],
                p="xl",
                radius="md",
                shadow="md",
                maw=420,
                w="100%",
            ),
        )
    ],
    fluid=True,
)


@callback(
    Output("login-redirect", "pathname"),
    Output("login-msg", "children"),
    Input("login-submit", "n_clicks"),
    State("login-user", "value"),
    State("login-pass", "value"),
    prevent_initial_call=True,
)
def do_login(_n, username: str | None, password: str | None):
    if not username or not password:
        return dash.no_update, dmc.Alert("Enter username and password.", color="yellow", title="Validation")
    with db_session() as s:
        u = s.scalar(select(models.User).where(models.User.username == username))
        if not u or not u.is_active or not verify_password(password, u.password_hash):
            return dash.no_update, dmc.Alert("Invalid credentials.", color="red", title="Error")
        role = s.get(models.Role, u.role_id)
        insert_activity_log(s, user_id=u.id, action="LOGIN", entity_type="session", entity_id=str(u.id))
    login_user(u.id, u.username, role.name if role else "VIEWER", u.full_name)
    return "/", dmc.Alert("Success — redirecting…", color="green", title="Welcome")
