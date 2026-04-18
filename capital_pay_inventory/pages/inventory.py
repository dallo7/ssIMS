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
from database.dal import create_item, list_items, soft_delete_item, update_item
from database.engine import db_session

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
    [
        dcc.Store(id="inv-version", data=0),
        dmc.Group(
            [
                dmc.Title("Stock register", order=3),
                dmc.Group(
                    [
                        dmc.Button("Refresh", id="inv-refresh", variant="light"),
                        dmc.Button("Add item", id="inv-open-add", color="cpi"),
                        dmc.Button("Edit selected", id="inv-open-edit", variant="light"),
                        dmc.Button("Soft delete", id="inv-soft-del", color="red", variant="light"),
                        dcc.Upload(id="inv-upload", children=dmc.Button("Import CSV"), multiple=False),
                        dmc.Button("Export CSV", id="inv-export-csv", variant="outline"),
                    ],
                    gap="xs",
                ),
            ],
            justify="space-between",
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
                gap="sm",
            ),
        ),
    ],
    gap="md",
)


@callback(
    Output("inv-grid", "rowData"),
    Input("url", "pathname"),
    Input("inv-version", "data"),
)
def inv_load_grid(pathname, _ver):
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
                        create_item(
                            s,
                            name=str(row.get("name", "")),
                            description=str(row.get("description", "")) or None,
                            category_id=int(cats.get(str(row.get("category", "")), first_c)),
                            unit_of_measure_id=int(uoms.get(str(row.get("uom", "pc")), first_u)),
                            quantity_in_stock=float(row.get("qty", 0) or 0),
                            reorder_point=float(row.get("reorder_point", 0) or 0),
                            reorder_quantity=float(row.get("reorder_qty", 0) or 0),
                            unit_cost=float(row.get("unit_cost", 0) or 0),
                            unit_price=float(row.get("unit_price", 0) or 0),
                            storage_location_id=None,
                            supplier_id=None,
                            expiry_date=None,
                            barcode=str(row.get("barcode", "")) or None,
                            sku=str(row.get("sku", "")) or None,
                            created_by=uid,
                        )
                    except Exception:
                        continue
            return v, dash.no_update, dmc.Alert("Import finished — see grid.", color="green", title="CSV")
        except Exception as e:
            return (ver or 0), dash.no_update, dmc.Alert(str(e), color="red", title="Import error")

    if tid == "inv-soft-del":
        if not selected:
            return (ver or 0), dash.no_update, dmc.Alert("Select a row first.", color="yellow")
        pk = int(selected[0]["id"])
        with db_session() as s:
            soft_delete_item(s, pk, uid)
        return v, dash.no_update, ""

    if tid == "inv-save":
        if not name or cat is None or uom is None:
            return (ver or 0), True, dmc.Alert("Name, category, and unit are required.", color="yellow")
        with db_session() as s:
            if edit_id:
                update_item(
                    s,
                    int(edit_id),
                    uid,
                    name=name,
                    description=desc,
                    category_id=int(cat),
                    unit_of_measure_id=int(uom),
                    quantity_in_stock=float(qty or 0),
                    reorder_point=float(rp or 0),
                    reorder_quantity=float(rq or 0),
                    unit_cost=float(cost or 0),
                    unit_price=float(price or 0),
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
                    quantity_in_stock=float(qty or 0),
                    reorder_point=float(rp or 0),
                    reorder_quantity=float(rq or 0),
                    unit_cost=float(cost or 0),
                    unit_price=float(price or 0),
                    storage_location_id=int(loc) if loc not in (None, "") else None,
                    supplier_id=int(sup) if sup not in (None, "") else None,
                    expiry_date=_parse_expiry(exp),
                    barcode=barcode,
                    sku=sku,
                    created_by=uid,
                )
        return v, False, ""

    raise PreventUpdate


@callback(
    Output("inv-f-cat", "data"),
    Output("inv-f-uom", "data"),
    Output("inv-f-loc", "data"),
    Output("inv-f-sup", "data"),
    Input("url", "pathname"),
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
