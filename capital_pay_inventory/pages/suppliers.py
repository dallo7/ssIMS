import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session
from sqlalchemy import select

from database import models
from database.dal import create_supplier, list_suppliers, soft_delete_supplier, update_supplier
from database.engine import db_session

register_page(__name__, path="/suppliers", name="Suppliers", title="Suppliers", order=5)


def _uid():
    return int(session.get("user_id") or 1)


def _ok():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


COLS = [
    {"field": "id", "hide": True},
    {"field": "name", "headerName": "Name", "filter": True},
    {"field": "contact", "headerName": "Contact"},
    {"field": "phone", "headerName": "Phone"},
    {"field": "country", "headerName": "Country"},
    {"field": "lead", "headerName": "Lead days"},
    {"field": "rating", "headerName": "Rating"},
    {"field": "active", "headerName": "Active"},
]


def rows():
    with db_session() as s:
        return [
            {
                "id": x.id,
                "name": x.name,
                "contact": x.contact_person or "",
                "phone": x.phone or "",
                "country": x.country,
                "lead": x.lead_time_days,
                "rating": x.rating,
                "active": "yes" if x.is_active else "no",
            }
            for x in list_suppliers(s, active_only=False)
        ]


layout = dmc.Stack(
    [
        dcc.Store(id="sup-version", data=0),
        dmc.Title("Suppliers", order=3),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.TextInput(id="sup-name", label="Name", required=True),
                        dmc.TextInput(id="sup-contact", label="Contact"),
                        dmc.TextInput(id="sup-phone", label="Phone"),
                        dmc.TextInput(id="sup-email", label="Email"),
                        dmc.Textarea(id="sup-addr", label="Address", minRows=2),
                        dmc.TextInput(id="sup-country", label="Country", value="South Sudan"),
                        dmc.TextInput(id="sup-terms", label="Payment terms"),
                        dmc.NumberInput(id="sup-lead", label="Lead time (days)", value=7, min=0),
                        dmc.NumberInput(id="sup-rate", label="Rating 0–5", value=4, min=0, max=5, decimalScale=1),
                        dmc.Button("Add supplier", id="sup-add", color="cpi"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Selected row", fw=600, mb="xs"),
                        dmc.Button("Update", id="sup-upd", variant="light"),
                        dmc.Button("Soft delete", id="sup-del", color="red", variant="light"),
                        dmc.Button("Refresh", id="sup-refresh", variant="outline"),
                    ],
                ),
            ],
        ),
        dmc.Text(id="sup-msg", size="sm"),
        AgGrid(
            id="sup-grid",
            columnDefs=COLS,
            rowData=[],
            dashGridOptions={"pagination": True, "rowSelection": "single"},
            style={"height": "420px", "width": "100%"},
            className="ag-theme-alpine",
        ),
    ],
    gap="md",
)


@callback(Output("sup-grid", "rowData"), Input("url", "pathname"), Input("sup-version", "data"), Input("sup-refresh", "n_clicks"))
def sup_load(pathname, _v, _r):
    if "/suppliers" not in (pathname or ""):
        raise PreventUpdate
    return rows()


@callback(
    Output("sup-version", "data"),
    Output("sup-msg", "children"),
    Input("sup-add", "n_clicks"),
    Input("sup-upd", "n_clicks"),
    Input("sup-del", "n_clicks"),
    State("sup-version", "data"),
    State("sup-name", "value"),
    State("sup-contact", "value"),
    State("sup-phone", "value"),
    State("sup-email", "value"),
    State("sup-addr", "value"),
    State("sup-country", "value"),
    State("sup-terms", "value"),
    State("sup-lead", "value"),
    State("sup-rate", "value"),
    State("sup-grid", "selectedRows"),
    prevent_initial_call=True,
)
def sup_actions(_a, _u, _d, ver, name, ct, ph, em, ad, co, te, ld, rt, sel):
    if not _ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "sup-add" and name:
            with db_session() as s:
                create_supplier(
                    s,
                    user_id=uid,
                    name=name,
                    contact_person=ct,
                    phone=ph,
                    email=em,
                    address=ad,
                    country=co or "South Sudan",
                    payment_terms=te,
                    lead_time_days=int(ld or 7),
                    rating=float(rt or 3),
                )
            return v, dmc.Alert("Supplier added.", color="green")
        if not sel:
            return (ver or 0), dmc.Alert("Select a row.", color="yellow")
        pk = int(sel[0]["id"])
        if tid == "sup-upd":
            with db_session() as s:
                update_supplier(
                    s,
                    pk,
                    uid,
                    name=name,
                    contact_person=ct,
                    phone=ph,
                    email=em,
                    address=ad,
                    country=co,
                    payment_terms=te,
                    lead_time_days=int(ld or 7),
                    rating=float(rt or 3),
                )
            return v, dmc.Alert("Updated.", color="blue")
        if tid == "sup-del":
            with db_session() as s:
                soft_delete_supplier(s, pk, uid)
            return v, dmc.Alert("Soft deleted.", color="orange")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red")
    raise PreventUpdate
