import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import (
    create_storage_location,
    list_item_location_stock_matrix,
    list_items,
    list_storage_locations,
    transfer_bin_stock,
)
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/locations", name="Locations", title="Locations", order=19)

_loc_t, _loc_h = i18n.page_heading("en", "locations")


def _uid():
    return int(session.get("user_id") or 1)


def _can_write():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


BIN_COLS = [
    {"field": "item_code", "headerName": "SKU", "filter": True},
    {"field": "item_name", "headerName": "Item"},
    {"field": "warehouse", "headerName": "Warehouse"},
    {"field": "location", "headerName": "Bin"},
    {"field": "qty", "headerName": "Qty here", "type": ["numericColumn"]},
    {"field": "total_on_hand", "headerName": "Total", "type": ["numericColumn"]},
]


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="loc-version", data=0),
        html.Div(id="locations-page-header", children=page_header(_loc_t, help=_loc_h)),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("New storage location", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.TextInput(id="loc-name", label="Bin / aisle name"),
                        dmc.TextInput(id="loc-wh", label="Warehouse", value="Main"),
                        dmc.TextInput(id="loc-zone", label="Zone (optional)"),
                        dmc.Button("Create location", id="loc-create", color="cpi", mt="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Transfer between bins", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Text(
                            "Moves quantity between bins without changing system-wide on-hand (FIFO layers unchanged).",
                            size="xs",
                            c="dimmed",
                            mb="sm",
                        ),
                        dmc.Select(id="loc-tr-item", label="Item", data=[]),
                        dmc.Select(id="loc-tr-from", label="From", data=[]),
                        dmc.Select(id="loc-tr-to", label="To", data=[]),
                        dmc.NumberInput(id="loc-tr-qty", label="Quantity", min=0, value=0),
                        dmc.TextInput(id="loc-tr-ref", label="Reference (optional)"),
                        dmc.Button("Transfer", id="loc-tr-btn", color="blue", mt="sm"),
                    ],
                ),
            ],
        ),
        dmc.Text(id="loc-msg", size="sm"),
        AgGrid(
            id="loc-grid",
            columnDefs=BIN_COLS,
            rowData=[],
            dashGridOptions={"pagination": True, "paginationPageSize": 20},
            style={"height": "520px", "width": "100%"},
            className="ag-theme-alpine",
        ),
    ],
)


@callback(
    Output("locations-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def loc_header(pathname, loc):
    if normalize_path(pathname) != "/locations":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "locations")
    return page_header(t, help=h)


@callback(
    Output("loc-grid", "rowData"),
    Output("loc-tr-item", "data"),
    Output("loc-tr-from", "data"),
    Output("loc-tr-to", "data"),
    Input("_pages_location", "pathname"),
    Input("loc-version", "data"),
)
def loc_load(pathname, _v):
    if "/locations" not in (pathname or ""):
        raise PreventUpdate
    with db_session() as s:
        rows = list_item_location_stock_matrix(s)
        item_opts = [
            {"label": f"{i.item_id} — {i.name}", "value": str(i.id)}
            for i in list_items(s, active_only=True)
        ]
        loc_opts = [
            {"label": f"{x.warehouse} / {x.name}", "value": str(x.id)} for x in list_storage_locations(s)
        ]
    return rows, item_opts, loc_opts, loc_opts


@callback(
    Output("loc-version", "data"),
    Output("loc-msg", "children"),
    Input("loc-create", "n_clicks"),
    Input("loc-tr-btn", "n_clicks"),
    State("loc-version", "data"),
    State("loc-name", "value"),
    State("loc-wh", "value"),
    State("loc-zone", "value"),
    State("loc-tr-item", "value"),
    State("loc-tr-from", "value"),
    State("loc-tr-to", "value"),
    State("loc-tr-qty", "value"),
    State("loc-tr-ref", "value"),
    prevent_initial_call=True,
)
def loc_actions(_c, _t, ver, name, wh, zone, iid, fr, to, qty, ref):
    if not _can_write():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "loc-create" and name and wh:
            with db_session() as s:
                create_storage_location(
                    s, name=name.strip(), warehouse=wh.strip(), zone=zone, user_id=uid
                )
            return v, dmc.Alert("Location created.", color="green", title="OK")
        if tid == "loc-tr-btn" and iid and fr and to and qty:
            with db_session() as s:
                transfer_bin_stock(
                    s,
                    item_id=int(iid),
                    from_location_id=int(fr),
                    to_location_id=int(to),
                    quantity=float(qty),
                    performed_by=uid,
                    reference_number=ref,
                )
            return v, dmc.Alert("Transfer posted.", color="green", title="OK")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red", title="Error")
    raise PreventUpdate
