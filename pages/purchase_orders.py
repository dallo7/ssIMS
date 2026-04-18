import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import approve_po, close_po, create_po, list_pos, receive_po, submit_po
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/purchase-orders", name="Purchase Orders", title="Purchase Orders", order=4)

_po_t, _po_h = i18n.page_heading("en", "purchase_orders")


def _uid():
    return int(session.get("user_id") or 1)


def _role():
    return session.get("role", "VIEWER")


COLS = [
    {"field": "id", "hide": True},
    {"field": "po_id", "headerName": "PO #", "filter": True},
    {"field": "supplier", "headerName": "Supplier"},
    {"field": "status", "headerName": "Status"},
    {"field": "expected", "headerName": "Expected"},
]


def rows():
    with db_session() as s:
        pos = list_pos(s)
        sups = {x.id: x.name for x in s.scalars(select(models.Supplier)).all()}
        out = []
        for p in pos:
            out.append(
                {
                    "id": p.id,
                    "po_id": p.po_id,
                    "supplier": sups.get(p.supplier_id, ""),
                    "status": p.status,
                    "expected": str(p.expected_date or ""),
                }
            )
    return out


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="po-version", data=0),
        html.Div(id="purchase-orders-page-header", children=page_header(_po_t, help=_po_h)),
        dmc.Paper(
            className="cpi-toolbar-paper",
            p="md",
            radius="md",
            withBorder=True,
            children=dmc.Group([dmc.Button("Refresh", id="po-refresh", variant="light")], justify="flex-end"),
        ),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("New draft PO", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Select(id="po-supplier", label="Supplier", data=[]),
                        dmc.TextInput(id="po-line-item", label="Item PK (id)", placeholder="e.g. 1"),
                        dmc.NumberInput(id="po-line-qty", label="Qty ordered", min=0, value=10),
                        dmc.NumberInput(id="po-line-cost", label="Unit cost", min=0, value=1),
                        dmc.Button("Create draft", id="po-create", color="cpi"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Workflow (selected row)", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Button("Submit", id="po-submit", variant="light"),
                        dmc.Button("Approve", id="po-approve", color="green", variant="light"),
                        dmc.NumberInput(id="po-recv-qty", label="Receive qty (line)", value=0, min=0),
                        dmc.Button("Receive line", id="po-receive", color="blue", variant="light"),
                        dmc.Button("Close", id="po-close", variant="outline"),
                    ],
                ),
            ],
        ),
        dmc.Text(id="po-msg", size="sm"),
        AgGrid(
            id="po-grid",
            columnDefs=COLS,
            rowData=[],
            dashGridOptions={"pagination": True, "rowSelection": "single"},
            style={"height": "400px", "width": "100%"},
            className="ag-theme-alpine",
        ),
    ],
)


@callback(
    Output("purchase-orders-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def purchase_orders_page_header(pathname, loc):
    if normalize_path(pathname) != "/purchase-orders":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "purchase_orders")
    return page_header(t, help=h)


@callback(
    Output("po-grid", "rowData"),
    Output("po-supplier", "data"),
    Input("_pages_location", "pathname"),
    Input("po-version", "data"),
    Input("po-refresh", "n_clicks"),
)
def po_load(pathname, _v, _r):
    if "/purchase-orders" not in (pathname or ""):
        raise PreventUpdate
    with db_session() as s:
        sups = [{"label": x.name, "value": str(x.id)} for x in s.scalars(select(models.Supplier).where(models.Supplier.is_active == True)).all()]  # noqa: E712
    return rows(), sups


@callback(
    Output("po-version", "data"),
    Output("po-msg", "children"),
    Input("po-create", "n_clicks"),
    Input("po-submit", "n_clicks"),
    Input("po-approve", "n_clicks"),
    Input("po-receive", "n_clicks"),
    Input("po-close", "n_clicks"),
    State("po-version", "data"),
    State("po-supplier", "value"),
    State("po-line-item", "value"),
    State("po-line-qty", "value"),
    State("po-line-cost", "value"),
    State("po-grid", "selectedRows"),
    State("po-recv-qty", "value"),
    prevent_initial_call=True,
)
def po_actions(_c, _s, _a, _rcv, _cl, ver, sup, item, qty, cost, sel, recv_qty):
    if _role() == "VIEWER":
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "po-create" and sup and item and qty:
            with db_session() as s:
                create_po(
                    s,
                    supplier_id=int(sup),
                    created_by=uid,
                    expected_date=None,
                    lines=[{"item_id": int(item), "qty_ordered": float(qty), "unit_cost": float(cost or 0)}],
                )
            return v, dmc.Alert("Draft PO created.", color="green")
        if not sel:
            return (ver or 0), dmc.Alert("Select a PO row.", color="yellow")
        pk = int(sel[0]["id"])
        if tid == "po-submit" and _role() in ("ADMIN", "MANAGER", "STOCK_CLERK"):
            with db_session() as s:
                submit_po(s, pk, uid)
            return v, dmc.Alert("Submitted.", color="blue")
        if tid == "po-approve" and _role() in ("ADMIN", "MANAGER"):
            with db_session() as s:
                approve_po(s, pk, uid)
            return v, dmc.Alert("Approved.", color="green")
        if tid == "po-receive" and recv_qty is not None:
            with db_session() as s:
                po = s.get(models.PurchaseOrder, pk)
                if not po or not po.lines:
                    return (ver or 0), dmc.Alert("No lines.", color="yellow")
                line_id = po.lines[0].id
                receive_po(s, pk, uid, [{"line_id": line_id, "qty_received": float(recv_qty)}])
            return v, dmc.Alert("Receiving posted.", color="green")
        if tid == "po-close":
            with db_session() as s:
                close_po(s, pk, uid)
            return v, dmc.Alert("Closed.", color="gray")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red")
    raise PreventUpdate
