import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import issue_stock_fifo, list_transactions, receive_stock
from database.engine import db_session

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
    [
        dcc.Store(id="mov-version", data=0),
        dmc.Title("Stock movements & ledger", order=3),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 3},
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Receive stock", fw=600, mb="xs"),
                        dmc.Select(id="mov-recv-item", label="Item", data=[]),
                        dmc.NumberInput(id="mov-recv-qty", label="Quantity", min=0, decimalScale=4, value=0),
                        dmc.NumberInput(id="mov-recv-cost", label="Unit cost", min=0, decimalScale=4, value=0),
                        dmc.TextInput(id="mov-recv-ref", label="Reference"),
                        dmc.Button("Post RECEIVE", id="mov-recv-btn", color="green", fullWidth=True, mt="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Issue stock (FIFO)", fw=600, mb="xs"),
                        dmc.Select(id="mov-iss-item", label="Item", data=[]),
                        dmc.NumberInput(id="mov-iss-qty", label="Quantity", min=0, decimalScale=4, value=0),
                        dmc.TextInput(id="mov-iss-ref", label="Reference"),
                        dmc.Button("Post ISSUE", id="mov-iss-btn", color="red", fullWidth=True, mt="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Filter ledger", fw=600, mb="xs"),
                        dmc.Select(id="mov-filter-item", label="Item (optional)", data=[], clearable=True),
                        dmc.Button("Refresh", id="mov-refresh", variant="light", fullWidth=True, mt="sm"),
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
    gap="md",
)


@callback(
    Output("mov-grid", "rowData"),
    Output("mov-recv-item", "data"),
    Output("mov-iss-item", "data"),
    Output("mov-filter-item", "data"),
    Input("url", "pathname"),
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
    fid = int(filt) if filt else None
    return _tx_rows(fid), opts, opts, opts


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
    State("mov-iss-item", "value"),
    State("mov-iss-qty", "value"),
    State("mov-iss-ref", "value"),
    prevent_initial_call=True,
)
def mov_post(_r, _i, ver, ri, rq, rc, rr, ii, iq, ir):
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
                )
            return v, dmc.Alert("ISSUE posted (FIFO).", color="green", title="OK")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red", title="Error")
    raise PreventUpdate
