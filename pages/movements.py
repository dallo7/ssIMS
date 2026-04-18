import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import issue_stock_fifo, list_transactions, receive_stock
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

_mvt_t, _mvt_h = i18n.page_heading("en", "movements")

register_page(__name__, path="/movements", name="Movements", title="Movements", order=3)


def _uid():
    return int(session.get("user_id") or 1)


def _role_ok():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


TX_COLS = [
    {"field": "transaction_id", "headerName": "Txn ID", "filter": True},
    {"field": "ts", "headerName": "Time", "sortable": True},
    {"field": "type", "headerName": "Type"},
    {"field": "item", "headerName": "Item"},
    {"field": "qty", "headerName": "Qty", "type": ["numericColumn"]},
    {"field": "ref", "headerName": "Reference"},
]


def _tx_rows(item_filter=None):
    with db_session() as s:
        tx = list_transactions(s, item_id=item_filter)
        items = {i.id: i.name for i in s.scalars(select(models.InventoryItem)).all()}
        rows = []
        for t in tx[:500]:
            rows.append(
                {
                    "transaction_id": t.transaction_id[:12],
                    "ts": t.timestamp.isoformat(),
                    "type": t.type,
                    "item": items.get(t.item_id, ""),
                    "qty": t.quantity,
                    "ref": t.reference_number or "",
                }
            )
    return rows


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="mov-version", data=0),
        html.Div(id="movements-page-header", children=page_header(_mvt_t, help=_mvt_h)),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 3},
            spacing="md",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="sm",
                    children=[
                        dmc.Text("Stock in", fw=600, mb="xs", size="sm"),
                        dmc.Text("Delivery or return to shelf", size="xs", c="dimmed", mb="sm"),
                        dmc.Select(id="mov-recv-item", label="Which item?", data=[]),
                        dmc.NumberInput(id="mov-recv-qty", label="How many?", min=0, decimalScale=4, value=0),
                        dmc.NumberInput(id="mov-recv-cost", label="Cost per unit (if known)", min=0, decimalScale=4, value=0),
                        dmc.TextInput(id="mov-recv-ref", label="Delivery note or reference (optional)"),
                        dmc.Select(
                            id="mov-recv-loc",
                            label="Receive into location (optional)",
                            data=[],
                            clearable=True,
                        ),
                        dmc.Button("Save stock in", id="mov-recv-btn", color="green", fullWidth=True, mt="sm", size="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="sm",
                    children=[
                        dmc.Text("Stock out", fw=600, mb="xs", size="sm"),
                        dmc.Text("Taken from the shelf (uses oldest stock first)", size="xs", c="dimmed", mb="sm"),
                        dmc.Select(id="mov-iss-item", label="Which item?", data=[]),
                        dmc.NumberInput(id="mov-iss-qty", label="How many?", min=0, decimalScale=4, value=0),
                        dmc.TextInput(id="mov-iss-ref", label="Who / what for? (optional)"),
                        dmc.Select(
                            id="mov-iss-loc",
                            label="Issue from location (optional)",
                            data=[],
                            clearable=True,
                        ),
                        dmc.Button("Save stock out", id="mov-iss-btn", color="red", fullWidth=True, mt="sm", size="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="sm",
                    children=[
                        dmc.Text("History", fw=600, mb="xs", size="sm"),
                        dmc.Text("Filter the list below", size="xs", c="dimmed", mb="sm"),
                        dmc.Select(id="mov-filter-item", label="One item only (optional)", data=[], clearable=True),
                        dmc.Button("Refresh table", id="mov-refresh", variant="light", fullWidth=True, mt="sm", size="sm"),
                    ],
                ),
            ],
        ),
        dmc.Text(id="mov-msg", size="sm"),
        AgGrid(
            id="mov-grid",
            columnDefs=TX_COLS,
            rowData=[],
            dashGridOptions={"pagination": True, "paginationPageSize": 20},
            style={"height": "480px", "width": "100%"},
            className="ag-theme-alpine",
        ),
    ],
)


@callback(
    Output("movements-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def movements_page_header(pathname, loc):
    if normalize_path(pathname) != "/movements":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "movements")
    return page_header(t, help=h)


@callback(
    Output("mov-grid", "rowData"),
    Output("mov-recv-item", "data"),
    Output("mov-iss-item", "data"),
    Output("mov-filter-item", "data"),
    Output("mov-recv-loc", "data"),
    Output("mov-iss-loc", "data"),
    Input("_pages_location", "pathname"),
    Input("mov-version", "data"),
    Input("mov-refresh", "n_clicks"),
    State("mov-filter-item", "value"),
    prevent_initial_call=False,
)
def mov_load(pathname, _v, _r, filt):
    p = pathname or ""
    if "/movements" not in p:
        raise PreventUpdate
    with db_session() as s:
        opts = [{"label": f"{i.item_id} — {i.name}", "value": str(i.id)} for i in s.scalars(select(models.InventoryItem).where(models.InventoryItem.is_active == True)).all()]  # noqa: E712
        loc_opts = [
            {"label": f"{x.warehouse} / {x.name}", "value": str(x.id)}
            for x in s.scalars(select(models.StorageLocation).order_by(models.StorageLocation.name)).all()
        ]
    fid = int(filt) if filt else None
    return _tx_rows(fid), opts, opts, opts, loc_opts, loc_opts


@callback(
    Output("mov-version", "data"),
    Output("mov-msg", "children"),
    Input("mov-recv-btn", "n_clicks"),
    Input("mov-iss-btn", "n_clicks"),
    State("mov-version", "data"),
    State("mov-recv-item", "value"),
    State("mov-recv-qty", "value"),
    State("mov-recv-cost", "value"),
    State("mov-recv-ref", "value"),
    State("mov-recv-loc", "value"),
    State("mov-iss-item", "value"),
    State("mov-iss-qty", "value"),
    State("mov-iss-ref", "value"),
    State("mov-iss-loc", "value"),
    prevent_initial_call=True,
)
def mov_post(_r, _i, ver, ri, rq, rc, rr, rloc, ii, iq, ir, iloc):
    if not _role_ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "mov-recv-btn" and ri and rq and rc is not None:
            with db_session() as s:
                receive_stock(
                    s,
                    item_id=int(ri),
                    quantity=float(rq),
                    unit_cost=float(rc),
                    performed_by=uid,
                    reference_number=rr,
                    storage_location_id=int(rloc) if rloc else None,
                )
            return v, dmc.Alert("RECEIVE posted.", color="green", title="OK")
        if tid == "mov-iss-btn" and ii and iq:
            with db_session() as s:
                issue_stock_fifo(
                    s,
                    item_id=int(ii),
                    quantity=float(iq),
                    performed_by=uid,
                    reference_number=ir,
                    storage_location_id=int(iloc) if iloc else None,
                )
            return v, dmc.Alert("ISSUE posted (FIFO).", color="green", title="OK")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red", title="Error")
    raise PreventUpdate
