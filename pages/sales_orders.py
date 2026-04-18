import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import models
from database.dal import (
    add_sales_order_line,
    cancel_sales_order,
    confirm_sales_order,
    create_sales_order_draft,
    list_customers,
    list_sales_orders,
    ship_sales_order_line,
)
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/sales-orders", name="Sales orders", title="Sales orders", order=18)

_so_t, _so_h = i18n.page_heading("en", "sales_orders")


def _uid():
    return int(session.get("user_id") or 1)


def _can_write():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="so-version", data=0),
        html.Div(id="sales-orders-page-header", children=page_header(_so_t, help=_so_h)),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("New sales order", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Select(id="so-new-cust", label="Customer", data=[]),
                        dmc.Button("Create draft", id="so-new-btn", color="cpi", mt="sm"),
                        dmc.Divider(mt="md", mb="md", label="Add line (draft only)", labelPosition="center"),
                        dmc.TextInput(id="so-line-item", label="Item ID (pk)", placeholder="e.g. 1"),
                        dmc.NumberInput(id="so-line-qty", label="Qty", min=0, value=1),
                        dmc.NumberInput(id="so-line-price", label="Unit price (SSP)", min=0, value=0),
                        dmc.Button("Add line", id="so-add-line", variant="light", mt="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=[
                        dmc.Text("Workflow", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                        dmc.Select(id="so-pick", label="Select order", data=[], value=None),
                        dmc.Text(id="so-status", size="sm", c="dimmed", mb="sm"),
                        dmc.Group(
                            [
                                dmc.Button("Confirm", id="so-confirm", color="green", variant="light"),
                                dmc.Button("Cancel order", id="so-cancel", color="red", variant="light"),
                            ],
                            gap="xs",
                        ),
                        dmc.Divider(mt="md", mb="md", label="Ship line", labelPosition="center"),
                        dmc.Select(id="so-ship-line", label="Order line", data=[]),
                        dmc.NumberInput(id="so-ship-qty", label="Qty to ship", min=0, value=0),
                        dmc.Select(id="so-ship-loc", label="From location (optional)", data=[], clearable=True),
                        dmc.Button("Ship", id="so-ship-btn", color="blue", mt="sm"),
                    ],
                ),
            ],
        ),
        dmc.Text(id="so-msg", size="sm"),
        html.Div(id="so-lines-wrap"),
    ],
)


@callback(
    Output("sales-orders-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def so_header(pathname, loc):
    if normalize_path(pathname) != "/sales-orders":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "sales_orders")
    return page_header(t, help=h)


@callback(
    Output("so-new-cust", "data"),
    Output("so-pick", "data"),
    Output("so-ship-loc", "data"),
    Input("_pages_location", "pathname"),
    Input("so-version", "data"),
)
def so_load_opts(pathname, _v):
    if "/sales-orders" not in (pathname or ""):
        raise PreventUpdate
    with db_session() as s:
        cust = [{"label": f"{c.customer_code} — {c.name}", "value": str(c.id)} for c in list_customers(s)]
        orders = list_sales_orders(s, limit=100)
        so_opts = [{"label": f"{o.so_number} ({o.status})", "value": str(o.id)} for o in orders]
        locs = [
            {"label": f"{x.warehouse} / {x.name}", "value": str(x.id)}
            for x in s.scalars(select(models.StorageLocation).order_by(models.StorageLocation.name)).all()
        ]
    return cust, so_opts, locs


@callback(
    Output("so-lines-wrap", "children"),
    Output("so-status", "children"),
    Output("so-ship-line", "data"),
    Input("so-pick", "value"),
    Input("so-version", "data"),
)
def so_lines_detail(so_id, _v):
    if not so_id:
        return html.Div(), "", []
    with db_session() as s:
        oid = int(so_id)
        so = s.scalar(
            select(models.SalesOrder)
            .options(selectinload(models.SalesOrder.lines))
            .where(models.SalesOrder.id == oid)
        )
        if not so:
            return html.Div(), "", []
        items = {i.id: i.name for i in s.scalars(select(models.InventoryItem)).all()}
        rows = []
        line_opts = []
        for ln in so.lines:
            rows.append(
                html.Tr(
                    [
                        html.Td(str(ln.id)),
                        html.Td(items.get(ln.item_id, "")),
                        html.Td(str(ln.quantity_ordered)),
                        html.Td(str(ln.quantity_shipped)),
                        html.Td(str(ln.unit_price)),
                    ]
                )
            )
            rem = float(ln.quantity_ordered) - float(ln.quantity_shipped)
            if rem > 1e-9 and so.status in ("CONFIRMED", "PICKING"):
                line_opts.append(
                    {
                        "label": f"#{ln.id} {items.get(ln.item_id, '')[:40]} (rem {rem})",
                        "value": str(ln.id),
                    }
                )
        head = html.Tr(
            [
                html.Th("Line"),
                html.Th("Item"),
                html.Th("Ordered"),
                html.Th("Shipped"),
                html.Th("Price"),
            ]
        )
        tbl = dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=True,
            children=[html.Thead(head), html.Tbody(rows)],
        )
        st = f"Status: **{so.status}** · Customer id {so.customer_id}"
        return tbl, dmc.Text(st), line_opts


@callback(
    Output("so-version", "data"),
    Output("so-msg", "children"),
    Input("so-new-btn", "n_clicks"),
    Input("so-add-line", "n_clicks"),
    Input("so-confirm", "n_clicks"),
    Input("so-cancel", "n_clicks"),
    Input("so-ship-btn", "n_clicks"),
    State("so-version", "data"),
    State("so-new-cust", "value"),
    State("so-pick", "value"),
    State("so-line-item", "value"),
    State("so-line-qty", "value"),
    State("so-line-price", "value"),
    State("so-ship-line", "value"),
    State("so-ship-qty", "value"),
    State("so-ship-loc", "value"),
    prevent_initial_call=True,
)
def so_actions(
    _a, _b, _c, _d, _e, ver, cust, so_pick, item_pk, qty, price, line_id, ship_q, ship_loc
):
    if not _can_write():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "so-new-btn" and cust:
            with db_session() as s:
                create_sales_order_draft(s, customer_id=int(cust), created_by=uid, notes=None)
            return v, dmc.Alert("Draft order created — select it in the list.", color="green", title="OK")
        if tid == "so-add-line" and so_pick and item_pk:
            with db_session() as s:
                ln = add_sales_order_line(
                    s,
                    so_pk=int(so_pick),
                    item_id=int(item_pk),
                    qty=float(qty or 0),
                    unit_price=float(price or 0),
                )
            if not ln:
                return (ver or 0), dmc.Alert("Could not add line (order must be DRAFT).", color="yellow")
            return v, dmc.Alert("Line added.", color="green", title="OK")
        if tid == "so-confirm" and so_pick:
            with db_session() as s:
                ok, msg = confirm_sales_order(s, int(so_pick), uid)
            return v, dmc.Alert(msg, color="green" if ok else "yellow", title="Confirm")
        if tid == "so-cancel" and so_pick:
            with db_session() as s:
                ok, msg = cancel_sales_order(s, int(so_pick), uid)
            return v, dmc.Alert(msg, color="green" if ok else "yellow", title="Cancel")
        if tid == "so-ship-btn" and line_id and ship_q:
            with db_session() as s:
                ok, msg = ship_sales_order_line(
                    s,
                    so_line_id=int(line_id),
                    ship_qty=float(ship_q),
                    performed_by=uid,
                    storage_location_id=int(ship_loc) if ship_loc else None,
                )
            return v, dmc.Alert(msg, color="green" if ok else "red", title="Ship")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red", title="Error")
    raise PreventUpdate
