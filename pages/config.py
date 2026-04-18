import dash
import dash_mantine_components as dmc
from dash import ALL
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import (
    clear_user_approval_pin,
    create_api_token,
    list_activity,
    list_api_tokens,
    revoke_api_token,
    set_config,
    set_user_approval_pin,
    user_has_approval_pin,
)
from database.engine import db_session
from components.branding import capital_pay_logo, powered_by_capitalpay
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/config", name="Configuration", title="Configuration", order=10)

_cfg_t, _cfg_h = i18n.page_heading("en", "config")


def _ok():
    return session.get("role") in ("ADMIN", "MANAGER")


def _admin():
    return session.get("role") == "ADMIN"


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        html.Div(id="config-page-header", children=page_header(_cfg_t, help=_cfg_h)),
        dcc.Store(id="cfg-api-version", data=0),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Alert thresholds", fw=600, mb="md", size="sm", tt="uppercase", opacity=0.85),
                        dmc.NumberInput(id="cfg-expiry", label="Expiry warning (days)", min=1, value=30),
                        dmc.NumberInput(id="cfg-audit", label="Audit overdue (days)", min=1, value=60),
                        dmc.NumberInput(id="cfg-dead", label="Dead stock (days)", min=1, value=60),
                        dmc.Button("Save configuration", id="cfg-save", color="cpi"),
                        html.Div(id="cfg-feedback"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Database backup", fw=600, mb="md", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text(
                                    id="cfg-backup-hint",
                                    size="sm",
                                    c="dimmed",
                                    style={},
                                    children="PostgreSQL is enabled. Use pg_dump/pg_restore for backups.",
                                ),
                            ],
                        ),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Stack(
                            gap="md",
                            children=[
                                dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Text(
                                            "Inventory approval PIN",
                                            fw=600,
                                            size="sm",
                                            tt="uppercase",
                                            opacity=0.85,
                                        ),
                                        dmc.Text(
                                            "Managers and administrators enter this PIN when approving or rejecting clerk inventory submissions on the Approvals page.",
                                            size="sm",
                                            c="dimmed",
                                            style={"lineHeight": 1.55},
                                            maw=640,
                                        ),
                                    ],
                                ),
                                html.Div(id="cfg-pin-status"),
                                dmc.Divider(variant="dashed", opacity=0.55),
                                dmc.Stack(
                                    gap="md",
                                    children=[
                                        dmc.PasswordInput(
                                            id="cfg-pin-current",
                                            label="Current PIN (if changing or removing)",
                                            placeholder="Leave blank when setting first time",
                                        ),
                                        dmc.PasswordInput(
                                            id="cfg-pin-new",
                                            label="New PIN or passphrase",
                                            placeholder="At least 4 characters",
                                        ),
                                        dmc.PasswordInput(id="cfg-pin-confirm", label="Confirm new", placeholder="Re-enter new PIN"),
                                    ],
                                ),
                                dmc.Group(
                                    [
                                        dmc.Button("Save PIN", id="cfg-pin-save", color="cpi"),
                                        dmc.Button("Remove PIN", id="cfg-pin-clear", color="red", variant="light"),
                                    ],
                                    gap="sm",
                                ),
                                html.Div(id="cfg-pin-feedback"),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        dmc.Card(
            withBorder=True,
            padding="lg",
            children=[
                dmc.Text("Integration API", fw=600, mb="xs", size="sm", tt="uppercase", opacity=0.85),
                dmc.Group(
                    [
                        capital_pay_logo(h=22),
                        dmc.Text(
                            "REST API for read-only inventory exports (Bearer tokens).",
                            size="sm",
                            c="dimmed",
                            style={"flex": 1, "minWidth": 0},
                        ),
                    ],
                    gap="sm",
                    align="flex-start",
                    mb="xs",
                ),
                html.Div(powered_by_capitalpay("en"), style={"marginBottom": "0.5rem"}),
                dmc.Text(
                    "HTTPS REST under /api/v1/ (same host as the app). Send header: Authorization: Bearer <token>. "
                    "Endpoints: GET /health, /items, /items/<id>, /stock-by-location; POST /sales-orders, /movements/issue.",
                    size="sm",
                    c="dimmed",
                    mb="md",
                ),
                html.Div(id="cfg-api-admin-ui"),
                html.Div(id="cfg-api-new-secret"),
                html.Div(id="cfg-api-token-table", style={"marginTop": "0.75rem"}),
            ],
        ),
        dmc.Card(
            withBorder=True,
            padding="lg",
            children=[
                dmc.Stack(
                    gap="sm",
                    mb="md",
                    children=[
                        dmc.Text(
                            "Activity log",
                            fw=600,
                            size="sm",
                            tt="uppercase",
                            opacity=0.85,
                        ),
                        dmc.Group(
                            [
                                dmc.Badge("Append-only", size="xs", variant="light", color="cpi"),
                                dmc.Text(
                                    "Recent sign-ins, configuration changes, and inventory workflow events.",
                                    size="sm",
                                    c="dimmed",
                                    style={"lineHeight": 1.55},
                                    maw=720,
                                ),
                            ],
                            gap="sm",
                            align="flex-start",
                            wrap="wrap",
                        ),
                    ],
                ),
                dmc.Paper(
                    p=0,
                    radius="md",
                    withBorder=True,
                    className="cpi-activity-shell",
                    children=html.Div(id="cfg-activity", style={"minHeight": "120px"}),
                ),
            ],
        ),
    ],
)


@callback(
    Output("config-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def config_page_header(pathname, loc):
    if normalize_path(pathname) != "/config":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "config")
    return page_header(t, help=h)


def _th(label: str, **style):
    base = {
        "fontWeight": 600,
        "fontSize": "0.6875rem",
        "textTransform": "uppercase",
        "letterSpacing": "0.06em",
        "color": "var(--mantine-color-dimmed)",
        "paddingTop": "0.75rem",
        "paddingBottom": "0.75rem",
        "borderBottom": "1px solid color-mix(in srgb, var(--mantine-color-gray-4), transparent 55%)",
    }
    base.update(style)
    return html.Th(label, style=base)


def _fmt_activity_time(r) -> str:
    if not r.created_at:
        return "—"
    return r.created_at.strftime("%Y-%m-%d %H:%M:%S")


@callback(
    Output("cfg-activity", "children"),
    Input("_pages_location", "pathname"),
)
def cfg_act(pathname):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    with db_session() as s:
        rows = list_activity(s, 80)
    if not rows:
        inner = dmc.Stack(
            align="center",
            justify="center",
            gap="xs",
            py="xl",
            px="md",
            children=[
                dmc.Text("No activity yet", fw=500, size="sm"),
                dmc.Text(
                    "Events will appear here as users work in the system.",
                    size="sm",
                    c="dimmed",
                    ta="center",
                ),
            ],
        )
    else:
        head = html.Tr(
            [
                _th("Time", width="11.5rem", whiteSpace="nowrap"),
                _th("Action", minWidth="8rem"),
                _th("Entity", minWidth="10rem"),
                _th("Details"),
            ]
        )
        body = []
        for r in rows:
            ent = (r.entity_type or "") + (f" #{r.entity_id}" if r.entity_id else "")
            details = (r.details or "")[:120]
            body.append(
                html.Tr(
                    [
                        html.Td(
                            _fmt_activity_time(r),
                            style={
                                "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                                "fontSize": "0.75rem",
                                "whiteSpace": "nowrap",
                                "color": "var(--mantine-color-dimmed)",
                            },
                        ),
                        html.Td(
                            r.action or "—",
                            style={"fontSize": "0.8125rem", "fontWeight": 500},
                        ),
                        html.Td(ent or "—", style={"fontSize": "0.8125rem"}),
                        html.Td(
                            details or "—",
                            style={
                                "fontSize": "0.8125rem",
                                "maxWidth": "22rem",
                                "wordBreak": "break-word",
                            },
                        ),
                    ]
                )
            )
        inner = html.Div(
            className="cpi-activity-table-wrap",
            children=dmc.Table(
                striped=True,
                highlightOnHover=True,
                stickyHeader=True,
                stickyHeaderOffset=0,
                verticalSpacing="sm",
                horizontalSpacing="md",
                withTableBorder=False,
                withColumnBorders=False,
                withRowBorders=True,
                children=[html.Thead(head), html.Tbody(body)],
            ),
        )
    return dmc.ScrollArea(
        h=440,
        type="hover",
        offsetScrollbars=True,
        className="cpi-activity-scroll",
        children=inner,
    )


@callback(
    Output("cfg-backup-hint", "children"),
    Output("cfg-backup-hint", "style"),
    Input("_pages_location", "pathname"),
)
def cfg_backup_ui(pathname):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    return "PostgreSQL is enabled. Use pg_dump/pg_restore for backups.", {}



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


@callback(Output("cfg-pin-status", "children"), Input("_pages_location", "pathname"))
def cfg_pin_status(pathname):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    uid = int(session.get("user_id") or 0)
    with db_session() as s:
        has = user_has_approval_pin(s, uid)
    if has:
        return dmc.Paper(
            p="sm",
            radius="md",
            withBorder=True,
            className="cpi-pin-status-box cpi-pin-status-box--ok",
            children=dmc.Group(
                [
                    dmc.Badge("Approval PIN is set", color="green", variant="light"),
                    dmc.Text("You can approve inventory changes from the Approvals page.", size="sm", style={"lineHeight": 1.5}),
                ],
                gap="sm",
                align="flex-start",
                wrap="nowrap",
            ),
        )
    return dmc.Paper(
        p="sm",
        radius="md",
        withBorder=True,
        className="cpi-pin-status-box cpi-pin-status-box--warn",
        children=dmc.Group(
            [
                dmc.Badge("No approval PIN yet", color="orange", variant="light"),
                dmc.Text("Set a PIN before you can use the Approvals page.", size="sm", style={"lineHeight": 1.5}),
            ],
            gap="sm",
            align="flex-start",
            wrap="nowrap",
        ),
    )


@callback(
    Output("cfg-pin-feedback", "children"),
    Input("cfg-pin-save", "n_clicks"),
    State("cfg-pin-current", "value"),
    State("cfg-pin-new", "value"),
    State("cfg-pin-confirm", "value"),
    prevent_initial_call=True,
)
def cfg_pin_save(_n, current, new_pin, confirm):
    if not _ok():
        raise PreventUpdate
    uid = int(session.get("user_id") or 0)
    new_pin = (new_pin or "").strip()
    confirm = (confirm or "").strip()
    if new_pin != confirm:
        return dmc.Alert("New PIN and confirmation do not match.", color="yellow", title="Check fields")
    with db_session() as s:
        ok, msg = set_user_approval_pin(
            s,
            user_id=uid,
            new_pin=new_pin,
            old_pin=(current or "").strip() or None,
        )
    color = "green" if ok else "red"
    title = "Saved" if ok else "Could not save"
    return dmc.Alert(msg, color=color, title=title)


@callback(
    Output("cfg-pin-feedback", "children", allow_duplicate=True),
    Input("cfg-pin-clear", "n_clicks"),
    State("cfg-pin-current", "value"),
    prevent_initial_call=True,
)
def cfg_pin_clear(_n, current):
    if not _ok():
        raise PreventUpdate
    uid = int(session.get("user_id") or 0)
    with db_session() as s:
        ok, msg = clear_user_approval_pin(s, user_id=uid, old_pin=(current or "").strip())
    color = "green" if ok else "red"
    return dmc.Alert(msg, color=color, title="Removed" if ok else "Could not remove")


@callback(
    Output("cfg-api-admin-ui", "children"),
    Output("cfg-api-token-table", "children"),
    Input("_pages_location", "pathname"),
    Input("cfg-api-version", "data"),
)
def cfg_api_table(pathname, _v):
    if "/config" not in (pathname or ""):
        raise PreventUpdate
    if not _admin():
        return (
            dmc.Alert("Only administrators can create or revoke API tokens.", color="gray", title="API"),
            "",
        )
    ui = dmc.Group(
        [
            dmc.TextInput(id="cfg-api-label", label="New token label", w=280, placeholder="e.g. Branch POS"),
            dmc.Button("Generate token", id="cfg-api-gen", color="cpi"),
        ],
        gap="md",
        align="flex-end",
    )
    with db_session() as s:
        tokens = list_api_tokens(s)
    if not tokens:
        tbl = dmc.Text("No tokens yet.", size="sm", c="dimmed")
    else:
        head = html.Tr(
            [
                html.Th("ID", style={"padding": "0.5rem"}),
                html.Th("Label", style={"padding": "0.5rem"}),
                html.Th("Active", style={"padding": "0.5rem"}),
                html.Th("", style={"padding": "0.5rem"}),
            ]
        )
        body = []
        for t in tokens[:50]:
            body.append(
                html.Tr(
                    [
                        html.Td(str(t.id)),
                        html.Td(t.label),
                        html.Td("yes" if t.is_active else "no"),
                        html.Td(
                            dmc.Button(
                                "Revoke",
                                id={"type": "cfg-api-revoke", "tid": t.id},
                                size="xs",
                                color="red",
                                variant="light",
                                disabled=not t.is_active,
                            )
                        ),
                    ]
                )
            )
        tbl = html.Table([html.Thead(head), html.Tbody(body)])
    return ui, tbl


@callback(
    Output("cfg-api-new-secret", "children"),
    Output("cfg-api-version", "data", allow_duplicate=True),
    Input("cfg-api-gen", "n_clicks"),
    State("cfg-api-label", "value"),
    State("cfg-api-version", "data"),
    prevent_initial_call=True,
)
def cfg_api_gen(_n, label, ver):
    if not _admin():
        raise PreventUpdate
    uid = int(session.get("user_id") or 0)
    with db_session() as s:
        _row, plain = create_api_token(s, user_id=uid, label=label or "API key")
    alert = dmc.Alert(
        [
            dmc.Text("Copy this token now — it will not be shown again.", size="sm", mb="xs"),
            dmc.Code(plain, block=True),
        ],
        color="yellow",
        title="New API token",
    )
    return alert, (ver or 0) + 1


@callback(
    Output("cfg-api-version", "data", allow_duplicate=True),
    Input({"type": "cfg-api-revoke", "tid": ALL}, "n_clicks"),
    State("cfg-api-version", "data"),
    prevent_initial_call=True,
)
def cfg_api_revoke(clicks, ver):
    if not _admin():
        raise PreventUpdate
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    t = ctx.triggered_id
    if not isinstance(t, dict) or t.get("type") != "cfg-api-revoke":
        raise PreventUpdate
    tid = int(t["tid"])
    uid = int(session.get("user_id") or 0)
    with db_session() as s:
        revoke_api_token(s, tid, uid)
    return (ver or 0) + 1
