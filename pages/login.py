import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from dash_iconify import DashIconify
from sqlalchemy import select

from database import models
from database.dal import insert_activity_log
from database.engine import db_session
from components.branding import capital_pay_logo
from utils import i18n
from utils.auth import login_user, verify_password

register_page(__name__, path="/login", name="Login", title="Login", order=99)


def _title_block(lang: str):
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Title(
                i18n.login_txt(lang, "title"),
                order=3,
                className="cpi-login-title",
                style={
                    "fontWeight": 700,
                    "letterSpacing": "-0.02em",
                    "lineHeight": 1.25,
                    "minWidth": 0,
                },
            ),
            dmc.Text(
                i18n.login_txt(lang, "tagline"),
                size="xs",
                c="dimmed",
                mt="xs",
                maw=400,
                style={"lineHeight": 1.45},
            ),
        ],
    )


layout = html.Div(
    className="cpi-login-root cpi-login-branded",
    children=[
        dmc.Box(
            mx="auto",
            maw=420,
            w="100%",
            px="md",
            py="xl",
            style={"minHeight": "100vh", "display": "flex", "alignItems": "center", "justifyContent": "center"},
            children=[
                dmc.Paper(
                    className="cpi-login-card cpi-login-card--ims",
                    p=0,
                    radius="lg",
                    withBorder=True,
                    shadow="md",
                    w="100%",
                    children=[
                        html.Div(className="cpi-login-flag-bar"),
                        dmc.Stack(
                            gap="lg",
                            p={"base": "lg", "sm": "xl"},
                            children=[
                                dmc.Group(
                                    [
                                        capital_pay_logo(h=48, radius="md"),
                                        html.Div(id="login-title-block", children=_title_block("en")),
                                    ],
                                    gap="md",
                                    align="flex-start",
                                    wrap="nowrap",
                                ),
                                dmc.Stack(
                                    gap="md",
                                    children=[
                                        dmc.TextInput(
                                            id="login-user",
                                            label="Username",
                                            placeholder="",
                                            size="sm",
                                            radius="md",
                                            leftSection=DashIconify(
                                                icon="tabler:user",
                                                width=18,
                                                className="cpi-login-input-icon",
                                            ),
                                            leftSectionPointerEvents="none",
                                            labelProps={"fw": 600, "size": "sm", "mb": 6},
                                            styles={
                                                "input": {
                                                    "fontWeight": 500,
                                                    "fontSize": "0.9375rem",
                                                }
                                            },
                                        ),
                                        dmc.PasswordInput(
                                            id="login-pass",
                                            label="Password",
                                            placeholder="Enter your password",
                                            size="sm",
                                            radius="md",
                                            leftSection=DashIconify(
                                                icon="tabler:lock",
                                                width=18,
                                                className="cpi-login-input-icon",
                                            ),
                                            leftSectionPointerEvents="none",
                                            labelProps={"fw": 600, "size": "sm", "mb": 6},
                                            styles={
                                                "input": {
                                                    "fontWeight": 500,
                                                    "fontSize": "0.9375rem",
                                                }
                                            },
                                        ),
                                        html.Div(
                                            id="login-msg",
                                            style={"minHeight": "1.25rem"},
                                            className="cpi-login-msg-slot",
                                        ),
                                        dmc.Button(
                                            "Sign In",
                                            id="login-submit",
                                            fullWidth=True,
                                            size="sm",
                                            radius="md",
                                            color="cpi",
                                            leftSection=DashIconify(icon="tabler:login-2", width=20),
                                            style={"fontWeight": 600, "letterSpacing": "0.02em"},
                                        ),
                                        dcc.Location(id="login-redirect", refresh=True),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("login-title-block", "children"),
    Output("login-user", "label"),
    Output("login-user", "placeholder"),
    Output("login-pass", "label"),
    Output("login-pass", "placeholder"),
    Output("login-submit", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def login_i18n(pathname, loc):
    if "/login" not in (pathname or ""):
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    return (
        _title_block(lang),
        i18n.login_txt(lang, "user_label"),
        i18n.login_txt(lang, "user_ph"),
        i18n.login_txt(lang, "pass_label"),
        i18n.login_txt(lang, "pass_ph"),
        i18n.login_txt(lang, "signin"),
    )


def _msg_error(text: str):
    return dmc.Text(text, size="sm", c="red", fw=500, ta="center", style={"width": "100%"})


def _msg_ok(text: str):
    return dmc.Text(text, size="sm", c="green", fw=500, ta="center", style={"width": "100%"})


@callback(
    Output("login-redirect", "pathname"),
    Output("login-msg", "children"),
    Input("login-submit", "n_clicks"),
    State("login-user", "value"),
    State("login-pass", "value"),
    State("locale-store", "data"),
    prevent_initial_call=True,
)
def do_login(_n, username: str | None, password: str | None, loc):
    lang = i18n.normalize_lang(loc)
    if not username or not password:
        return dash.no_update, _msg_error(i18n.login_txt(lang, "err_required"))
    with db_session() as s:
        u = s.scalar(select(models.User).where(models.User.username == username))
        if not u or not u.is_active or not verify_password(password, u.password_hash):
            return dash.no_update, _msg_error(i18n.login_txt(lang, "err_invalid"))
        role = s.get(models.Role, u.role_id)
        insert_activity_log(s, user_id=u.id, action="LOGIN", entity_type="session", entity_id=str(u.id))
    login_user(u.id, u.username, role.name if role else "VIEWER", u.full_name)
    return "/", _msg_ok(i18n.login_txt(lang, "ok_redirect"))
