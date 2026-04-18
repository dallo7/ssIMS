import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import approve_audit, create_audit_session, generate_audit_sheet, list_audits, submit_audit_counts
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/auditing", name="Auditing", title="Auditing", order=6)

_aud_t, _aud_h = i18n.page_heading("en", "auditing")


def _uid():
    return int(session.get("user_id") or 1)


def _ok():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


COLS = [
    {"field": "id", "hide": True},
    {"field": "ref", "headerName": "Audit ref"},
    {"field": "title", "headerName": "Title"},
    {"field": "status", "headerName": "Status"},
    {"field": "type", "headerName": "Type"},
]


def rows():
    with db_session() as s:
        return [
            {"id": a.id, "ref": a.audit_ref, "title": a.title, "status": a.status, "type": a.audit_type}
            for a in list_audits(s)
        ]


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="aud-version", data=0),
        html.Div(id="auditing-page-header", children=page_header(_aud_t, help=_aud_h)),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.TextInput(id="aud-title", label="Session title", placeholder="March cycle — Zone A"),
                        dmc.Select(id="aud-type", label="Type", data=[{"label": "Cycle", "value": "CYCLE"}, {"label": "Full", "value": "FULL"}], value="CYCLE"),
                        dmc.Select(id="aud-cat", label="Category filter (optional)", data=[], clearable=True),
                        dmc.Button("Create session", id="aud-create", color="cpi"),
                        dmc.Button("Generate sheet", id="aud-gen", variant="light"),
                        dmc.NumberInput(id="aud-count", label="Counted qty (first line)", value=0, decimalScale=4),
                        dmc.Button("Submit counts", id="aud-submit", variant="light"),
                        dmc.Button("Approve adjustments", id="aud-approve", color="green", variant="light"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Instructions", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Text(
                            "Create → Generate sheet → enter count for first line → Submit → Manager approves.",
                            size="sm",
                            c="dimmed",
                            style={"lineHeight": 1.55},
                        ),
                    ],
                ),
            ],
        ),
        dmc.Text(id="aud-msg", size="sm"),
        AgGrid(id="aud-grid", columnDefs=COLS, rowData=[], dashGridOptions={"rowSelection": "single"}, style={"height": "360px", "width": "100%"}, className="ag-theme-alpine"),
    ],
)


@callback(
    Output("auditing-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def auditing_page_header(pathname, loc):
    if normalize_path(pathname) != "/auditing":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "auditing")
    return page_header(t, help=h)


@callback(Output("aud-grid", "rowData"), Output("aud-cat", "data"), Input("_pages_location", "pathname"), Input("aud-version", "data"))
def aud_load(pathname, _v):
    if "/auditing" not in (pathname or ""):
        raise PreventUpdate
    with db_session() as s:
        cats = [{"label": c.name, "value": str(c.id)} for c in s.scalars(select(models.Category)).all()]
    return rows(), cats


@callback(
    Output("aud-version", "data"),
    Output("aud-msg", "children"),
    Input("aud-create", "n_clicks"),
    Input("aud-gen", "n_clicks"),
    Input("aud-submit", "n_clicks"),
    Input("aud-approve", "n_clicks"),
    State("aud-version", "data"),
    State("aud-title", "value"),
    State("aud-type", "value"),
    State("aud-cat", "value"),
    State("aud-grid", "selectedRows"),
    State("aud-count", "value"),
    prevent_initial_call=True,
)
def aud_act(_c, _g, _s, _a, ver, title, typ, cat, sel, cnt):
    if not _ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "aud-create" and title:
            with db_session() as s:
                create_audit_session(
                    s,
                    title=title,
                    audit_type=typ or "CYCLE",
                    created_by=uid,
                    category_id=int(cat) if cat else None,
                    location_id=None,
                    scheduled_for=None,
                )
            return v, dmc.Alert("Audit session created.", color="green")
        if not sel:
            return (ver or 0), dmc.Alert("Select audit row.", color="yellow")
        aid = int(sel[0]["id"])
        if tid == "aud-gen":
            with db_session() as s:
                n = generate_audit_sheet(s, aid)
            return v, dmc.Alert(f"Generated {n} lines.", color="blue")
        if tid == "aud-submit":
            with db_session() as s:
                au = s.get(models.AuditSession, aid)
                if not au or not au.lines:
                    return (ver or 0), dmc.Alert("No lines.", color="yellow")
                lid = au.lines[0].id
                submit_audit_counts(s, aid, uid, [{"line_id": lid, "counted_qty": float(cnt or 0)}])
            return v, dmc.Alert("Counts submitted for review.", color="blue")
        if tid == "aud-approve" and session.get("role") in ("ADMIN", "MANAGER"):
            with db_session() as s:
                approve_audit(s, aid, uid)
            return v, dmc.Alert("Approved — adjustments posted as ADJUSTMENT txns.", color="green")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red")
    raise PreventUpdate
