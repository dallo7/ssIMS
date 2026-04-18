import base64
import csv
import io
from datetime import date as date_type
from datetime import datetime

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import (
    create_item,
    list_items,
    queue_inventory_change,
    sanitize_float,
    soft_delete_item,
    update_item,
)
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/inventory", name="Inventory", title="Inventory", order=2)


def _parse_expiry(exp):
    if exp is None or exp == "":
        return None
    if isinstance(exp, date_type):
        return exp
    if isinstance(exp, str):
        try:
            return datetime.strptime(exp[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    if hasattr(exp, "date"):
        try:
            return exp.date()
        except Exception:
            return None
    return None


def _role():
    return session.get("role", "VIEWER")


def _clerk_must_queue():
    return _role() == "STOCK_CLERK"


def _fields_payload(
    name,
    desc,
    cat,
    uom,
    qty,
    rp,
    rq,
    cost,
    price,
    loc,
    sup,
    exp,
    barcode,
    sku,
):
    exp_d = _parse_expiry(exp)
    return {
        "name": name,
        "description": desc if desc else None,
        "category_id": int(cat),
        "unit_of_measure_id": int(uom),
        "quantity_in_stock": sanitize_float(qty, 0.0),
        "reorder_point": sanitize_float(rp, 0.0),
        "reorder_quantity": sanitize_float(rq, 0.0),
        "unit_cost": sanitize_float(cost, 0.0),
        "unit_price": sanitize_float(price, 0.0),
        "storage_location_id": int(loc) if loc not in (None, "") else None,
        "supplier_id": int(sup) if sup not in (None, "") else None,
        "expiry_date": exp_d.isoformat() if exp_d else None,
        "barcode": barcode,
        "sku": sku or None,
    }


def _uid():
    return int(session.get("user_id") or 0)


COLS = [
    {"field": "id", "headerName": "PK", "hide": True},
    {"field": "item_id", "headerName": "Item ID", "filter": True, "sortable": True},
    {"field": "name", "headerName": "Name", "filter": True, "sortable": True},
    {"field": "category", "headerName": "Category", "filter": True},
    {"field": "uom", "headerName": "UoM"},
    {"field": "qty", "headerName": "Qty", "type": ["numericColumn"]},
    {"field": "reorder_pt", "headerName": "Reorder"},
    {"field": "unit_cost", "headerName": "Cost", "type": ["numericColumn"]},
    {"field": "location", "headerName": "Location"},
    {"field": "active", "headerName": "Active"},
]


def _rows():
    with db_session() as s:
        items = list_items(s, active_only=False)
        cats = {c.id: c.name for c in s.scalars(select(models.Category)).all()}
        uoms = {u.id: u.code for u in s.scalars(select(models.UnitOfMeasure)).all()}
        locs = {l.id: l.name for l in s.scalars(select(models.StorageLocation)).all()}
        rows = []
        for it in items:
            rows.append(
                {
                    "id": it.id,
                    "item_id": it.item_id,
                    "name": it.name,
                    "category": cats.get(it.category_id, ""),
                    "uom": uoms.get(it.unit_of_measure_id, ""),
                    "qty": it.quantity_in_stock,
                    "reorder_pt": it.reorder_point,
                    "unit_cost": it.unit_cost,
                    "location": locs.get(it.storage_location_id or 0, ""),
                    "active": "yes" if it.is_active else "no",
                }
            )
    return rows


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="inv-version", data=0),
        html.Div(id="inv-clerk-notice"),
        html.Div(id="inv-header-slot"),
        dmc.Paper(
            id="inv-toolbar-paper",
            className="cpi-toolbar-paper",
            p="md",
            radius="md",
            withBorder=True,
            children=dmc.Group(
                [
                    dmc.Group(
                        [
                            dmc.Button("Refresh list", id="inv-refresh", variant="light", size="sm"),
                            dmc.Button("Add item", id="inv-open-add", color="cpi", size="sm"),
                            dmc.Button("Edit selected row", id="inv-open-edit", variant="default", size="sm"),
                        ],
                        gap="sm",
                        wrap="wrap",
                    ),
                    html.Div(
                        id="inv-toolbar-advanced",
                        children=dmc.Group(
                            [
                                dmc.Button("Remove item (soft)", id="inv-soft-del", color="red", variant="light", size="sm"),
                                dcc.Upload(id="inv-upload", children=dmc.Button("Import CSV", size="sm"), multiple=False),
                                dmc.Button("Export CSV", id="inv-export-csv", variant="outline", size="sm"),
                            ],
                            gap="sm",
                            wrap="wrap",
                        ),
                    ),
                ],
                gap="md",
                wrap="wrap",
                justify="space-between",
                align="flex-end",
            ),
        ),
        dmc.Text(id="inv-upload-msg", size="sm", c="dimmed"),
        AgGrid(
            id="inv-grid",
            columnDefs=COLS,
            rowData=[],
            defaultColDef={"resizable": True, "sortable": True, "filter": True},
            dashGridOptions={"pagination": True, "paginationPageSize": 15, "rowSelection": "single"},
            style={"height": "520px", "width": "100%"},
            className="ag-theme-alpine",
        ),
        dcc.Download(id="inv-dl"),
        dmc.Modal(
            id="inv-modal",
            title="Inventory item",
            size="lg",
            opened=False,
            children=dmc.Stack(
                [
                    dmc.TextInput(id="inv-f-name", label="Name", required=True),
                    dmc.Textarea(id="inv-f-desc", label="Description", minRows=2),
                    dmc.Select(id="inv-f-cat", label="Category", data=[], searchable=True),
                    dmc.Select(id="inv-f-uom", label="Unit", data=[], searchable=True),
                    dmc.NumberInput(id="inv-f-qty", label="Quantity", value=0, min=0, decimalScale=4),
                    dmc.NumberInput(id="inv-f-rp", label="Reorder point", value=0, min=0, decimalScale=4),
                    dmc.NumberInput(id="inv-f-rq", label="Reorder qty", value=0, min=0, decimalScale=4),
                    dmc.NumberInput(id="inv-f-cost", label="Unit cost", value=0, min=0, decimalScale=4),
                    dmc.NumberInput(id="inv-f-price", label="Unit price", value=0, min=0, decimalScale=4),
                    dmc.Select(id="inv-f-loc", label="Location", data=[], searchable=True, clearable=True),
                    dmc.Select(id="inv-f-sup", label="Supplier", data=[], searchable=True, clearable=True),
                    dmc.Stack(
                        [
                            dmc.Text("Expiry (optional)", size="sm", fw=500),
                            dcc.DatePickerSingle(
                                id="inv-f-exp",
                                display_format="YYYY-MM-DD",
                                placeholder="Select date",
                                clearable=True,
                            ),
                        ],
                        gap=4,
                    ),
                    dmc.TextInput(id="inv-f-barcode", label="Barcode"),
                    dmc.TextInput(id="inv-f-sku", label="SKU"),
                    dmc.Group(
                        [
                            dmc.Button("Save", id="inv-save", color="cpi"),
                            dmc.Button("Cancel", id="inv-cancel", variant="default"),
                        ],
                        justify="flex-end",
                    ),
                    dcc.Store(id="inv-edit-id", data=None),
                ],
                gap="md",
            ),
        ),
    ],
)


@callback(
    Output("inv-header-slot", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def inv_header(pathname, loc):
    if normalize_path(pathname) != "/inventory":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    if _clerk_must_queue():
        return page_header(
            i18n.inventory_header(lang, "title_clerk"),
            help=i18n.inventory_header(lang, "help_clerk"),
        )
    return page_header(
        i18n.inventory_header(lang, "title_full"),
        help=i18n.inventory_header(lang, "help_full"),
    )


@callback(Output("inv-toolbar-paper", "className"), Input("_pages_location", "pathname"))
def inv_toolbar_shell_class(pathname):
    if "/inventory" not in (pathname or ""):
        raise PreventUpdate
    base = "cpi-toolbar-paper"
    if _clerk_must_queue():
        return f"{base} cpi-clerk-toolbar"
    return base


@callback(Output("inv-toolbar-advanced", "style"), Input("_pages_location", "pathname"))
def inv_toolbar_advanced_visibility(pathname):
    if "/inventory" not in (pathname or ""):
        raise PreventUpdate
    if _clerk_must_queue():
        return {"display": "none"}
    return {"display": "block"}


@callback(Output("inv-clerk-notice", "children"), Input("_pages_location", "pathname"))
def inv_clerk_notice(pathname):
    if "/inventory" not in (pathname or ""):
        raise PreventUpdate
    if _clerk_must_queue():
        return dmc.Alert(
            "Your saves are sent to a manager for approval before stock numbers change.",
            color="blue",
            variant="light",
        )
    return ""


@callback(
    Output("inv-grid", "rowData"),
    Input("_pages_location", "pathname"),
    Input("inv-version", "data"),
    Input("cpi-inventory-refresh", "data"),
)
def inv_load_grid(pathname, _ver, _ext):
    p = pathname or ""
    if "/inventory" not in p:
        raise PreventUpdate
    return _rows()


@callback(
    Output("inv-modal", "opened"),
    Output("inv-f-name", "value"),
    Output("inv-f-desc", "value"),
    Output("inv-f-cat", "value"),
    Output("inv-f-uom", "value"),
    Output("inv-f-qty", "value"),
    Output("inv-f-rp", "value"),
    Output("inv-f-rq", "value"),
    Output("inv-f-cost", "value"),
    Output("inv-f-price", "value"),
    Output("inv-f-loc", "value"),
    Output("inv-f-sup", "value"),
    Output("inv-f-exp", "date"),
    Output("inv-f-barcode", "value"),
    Output("inv-f-sku", "value"),
    Output("inv-edit-id", "data"),
    Input("inv-open-add", "n_clicks"),
    Input("inv-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def inv_modal_add_cancel(_add, _cancel):
    tid = dash.callback_context.triggered_id
    if tid == "inv-cancel":
        return False, "", "", None, None, 0, 0, 0, 0, 0, None, None, None, "", "", None
    if _role() == "VIEWER":
        raise PreventUpdate
    return True, "", "", None, None, 0, 0, 0, 0, 0, None, None, None, "", "", None


@callback(
    Output("inv-modal", "opened", allow_duplicate=True),
    Output("inv-f-name", "value", allow_duplicate=True),
    Output("inv-f-desc", "value", allow_duplicate=True),
    Output("inv-f-cat", "value", allow_duplicate=True),
    Output("inv-f-uom", "value", allow_duplicate=True),
    Output("inv-f-qty", "value", allow_duplicate=True),
    Output("inv-f-rp", "value", allow_duplicate=True),
    Output("inv-f-rq", "value", allow_duplicate=True),
    Output("inv-f-cost", "value", allow_duplicate=True),
    Output("inv-f-price", "value", allow_duplicate=True),
    Output("inv-f-loc", "value", allow_duplicate=True),
    Output("inv-f-sup", "value", allow_duplicate=True),
    Output("inv-f-exp", "date", allow_duplicate=True),
    Output("inv-f-barcode", "value", allow_duplicate=True),
    Output("inv-f-sku", "value", allow_duplicate=True),
    Output("inv-edit-id", "data", allow_duplicate=True),
    Input("inv-open-edit", "n_clicks"),
    State("inv-grid", "selectedRows"),
    prevent_initial_call=True,
)
def inv_modal_edit(_n, selected):
    if _role() == "VIEWER" or not selected:
        raise PreventUpdate
    pk = int(selected[0]["id"])
    with db_session() as s:
        it = s.get(models.InventoryItem, pk)
        if not it:
            raise PreventUpdate
        return (
            True,
            it.name,
            it.description or "",
            str(it.category_id),
            str(it.unit_of_measure_id),
            it.quantity_in_stock,
            it.reorder_point,
            it.reorder_quantity,
            it.unit_cost,
            it.unit_price,
            str(it.storage_location_id) if it.storage_location_id else None,
            str(it.supplier_id) if it.supplier_id else None,
            it.expiry_date.isoformat() if it.expiry_date else None,
            it.barcode or "",
            it.sku or "",
            pk,
        )


@callback(
    Output("inv-version", "data"),
    Output("inv-modal", "opened", allow_duplicate=True),
    Output("inv-upload-msg", "children"),
    Input("inv-save", "n_clicks"),
    Input("inv-soft-del", "n_clicks"),
    Input("inv-upload", "contents"),
    Input("inv-refresh", "n_clicks"),
    State("inv-version", "data"),
    State("inv-f-name", "value"),
    State("inv-f-desc", "value"),
    State("inv-f-cat", "value"),
    State("inv-f-uom", "value"),
    State("inv-f-qty", "value"),
    State("inv-f-rp", "value"),
    State("inv-f-rq", "value"),
    State("inv-f-cost", "value"),
    State("inv-f-price", "value"),
    State("inv-f-loc", "value"),
    State("inv-f-sup", "value"),
    State("inv-f-exp", "date"),
    State("inv-f-barcode", "value"),
    State("inv-f-sku", "value"),
    State("inv-edit-id", "data"),
    State("inv-grid", "selectedRows"),
    prevent_initial_call=True,
)
def inv_mutate(
    _sv,
    _sd,
    upload_contents,
    _rf,
    ver,
    name,
    desc,
    cat,
    uom,
    qty,
    rp,
    rq,
    cost,
    price,
    loc,
    sup,
    exp,
    barcode,
    sku,
    edit_id,
    selected,
):
    if _role() == "VIEWER":
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid() or 1

    if tid == "inv-refresh":
        return v, dash.no_update, ""

    if tid == "inv-upload" and upload_contents:
        try:
            _, content_string = upload_contents.split(",", 1)
            raw = base64.b64decode(content_string)
            df = pd.read_csv(io.BytesIO(raw))
            with db_session() as s:
                cats = {c.name: c.id for c in s.scalars(select(models.Category)).all()}
                uoms = {u.code: u.id for u in s.scalars(select(models.UnitOfMeasure)).all()}
                first_c = next(iter(cats.values()))
                first_u = next(iter(uoms.values()))
                for _, row in df.iterrows():
                    try:
                        nm = str(row.get("name", ""))
                        fields = {
                            "name": nm,
                            "description": str(row.get("description", "")) or None,
                            "category_id": int(cats.get(str(row.get("category", "")), first_c)),
                            "unit_of_measure_id": int(uoms.get(str(row.get("uom", "pc")), first_u)),
                            "quantity_in_stock": sanitize_float(row.get("qty"), 0.0),
                            "reorder_point": sanitize_float(row.get("reorder_point"), 0.0),
                            "reorder_quantity": sanitize_float(row.get("reorder_qty"), 0.0),
                            "unit_cost": sanitize_float(row.get("unit_cost"), 0.0),
                            "unit_price": sanitize_float(row.get("unit_price"), 0.0),
                            "storage_location_id": None,
                            "supplier_id": None,
                            "expiry_date": None,
                            "barcode": str(row.get("barcode", "")) or None,
                            "sku": str(row.get("sku", "")) or None,
                        }
                        if _clerk_must_queue():
                            queue_inventory_change(
                                s,
                                action="CREATE",
                                submitted_by=uid,
                                fields=fields,
                                item_display=nm,
                            )
                        else:
                            create_item(s, created_by=uid, **fields)
                    except Exception:
                        continue
            msg = (
                "Rows queued for approval — managers can apply them from Approvals."
                if _clerk_must_queue()
                else "Import finished — see grid."
            )
            return v, dash.no_update, dmc.Alert(msg, color="green", title="CSV")
        except Exception as e:
            return (ver or 0), dash.no_update, dmc.Alert(str(e), color="red", title="Import error")

    if tid == "inv-soft-del":
        if not selected:
            return (ver or 0), dash.no_update, dmc.Alert("Select a row first.", color="yellow")
        pk = int(selected[0]["id"])
        with db_session() as s:
            if _clerk_must_queue():
                it = s.get(models.InventoryItem, pk)
                display = it.name if it else ""
                queue_inventory_change(
                    s,
                    action="SOFT_DELETE",
                    submitted_by=uid,
                    item_pk=pk,
                    fields={},
                    item_display=display,
                )
            else:
                soft_delete_item(s, pk, uid)
        return v, dash.no_update, "" if not _clerk_must_queue() else dmc.Alert(
            "Deletion submitted for approval.", color="blue", title="Queued"
        )

    if tid == "inv-save":
        if not name or cat is None or uom is None:
            return (ver or 0), True, dmc.Alert("Name, category, and unit are required.", color="yellow")
        with db_session() as s:
            if _clerk_must_queue():
                payload = _fields_payload(
                    name, desc, cat, uom, qty, rp, rq, cost, price, loc, sup, exp, barcode, sku
                )
                if edit_id:
                    queue_inventory_change(
                        s,
                        action="UPDATE",
                        submitted_by=uid,
                        item_pk=int(edit_id),
                        fields=payload,
                        item_display=name,
                    )
                else:
                    queue_inventory_change(
                        s,
                        action="CREATE",
                        submitted_by=uid,
                        fields=payload,
                        item_display=name,
                    )
            elif edit_id:
                update_item(
                    s,
                    int(edit_id),
                    uid,
                    name=name,
                    description=desc,
                    category_id=int(cat),
                    unit_of_measure_id=int(uom),
                    quantity_in_stock=sanitize_float(qty, 0.0),
                    reorder_point=sanitize_float(rp, 0.0),
                    reorder_quantity=sanitize_float(rq, 0.0),
                    unit_cost=sanitize_float(cost, 0.0),
                    unit_price=sanitize_float(price, 0.0),
                    storage_location_id=int(loc) if loc not in (None, "") else None,
                    supplier_id=int(sup) if sup not in (None, "") else None,
                    expiry_date=_parse_expiry(exp),
                    barcode=barcode,
                    sku=sku,
                )
            else:
                create_item(
                    s,
                    name=name,
                    description=desc,
                    category_id=int(cat),
                    unit_of_measure_id=int(uom),
                    quantity_in_stock=sanitize_float(qty, 0.0),
                    reorder_point=sanitize_float(rp, 0.0),
                    reorder_quantity=sanitize_float(rq, 0.0),
                    unit_cost=sanitize_float(cost, 0.0),
                    unit_price=sanitize_float(price, 0.0),
                    storage_location_id=int(loc) if loc not in (None, "") else None,
                    supplier_id=int(sup) if sup not in (None, "") else None,
                    expiry_date=_parse_expiry(exp),
                    barcode=barcode,
                    sku=sku,
                    created_by=uid,
                )
        extra = (
            dmc.Alert("Submitted for manager approval.", color="blue", title="Queued")
            if _clerk_must_queue()
            else ""
        )
        return v, False, extra

    raise PreventUpdate


@callback(
    Output("inv-f-cat", "data"),
    Output("inv-f-uom", "data"),
    Output("inv-f-loc", "data"),
    Output("inv-f-sup", "data"),
    Input("_pages_location", "pathname"),
)
def inv_refdata(pathname):
    if pathname and "/inventory" not in pathname:
        raise PreventUpdate
    with db_session() as s:
        cats = [{"label": c.name, "value": str(c.id)} for c in s.scalars(select(models.Category)).all()]
        uoms = [{"label": f"{u.code} — {u.label}", "value": str(u.id)} for u in s.scalars(select(models.UnitOfMeasure)).all()]
        locs = [{"label": l.name, "value": str(l.id)} for l in s.scalars(select(models.StorageLocation)).all()]
        sups = [{"label": x.name, "value": str(x.id)} for x in s.scalars(select(models.Supplier)).all()]
    return cats, uoms, locs, sups


@callback(
    Output("inv-dl", "data"),
    Input("inv-export-csv", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(_n):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["item_id", "name", "category", "uom", "qty", "reorder_point", "unit_cost", "unit_price"])
    for r in _rows():
        if r["active"] == "yes":
            w.writerow([r["item_id"], r["name"], r["category"], r["uom"], r["qty"], r["reorder_pt"], r["unit_cost"], ""])
    return dict(content=buf.getvalue(), filename="inventory_export.csv", type="text/csv")