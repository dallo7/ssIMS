import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, register_page
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from flask import session

from database.dal import create_customer, list_customers
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/customers", name="Customers", title="Customers", order=17)

_cust_t, _cust_h = i18n.page_heading("en", "customers")


def _uid():
    return int(session.get("user_id") or 1)


def _can_write():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


COLS = [
    {"field": "code", "headerName": "Code", "filter": True},
    {"field": "name", "headerName": "Name"},
    {"field": "phone", "headerName": "Phone"},
    {"field": "country", "headerName": "Country"},
]


def _rows():
    with db_session() as s:
        return [
            {
                "code": c.customer_code,
                "name": c.name,
                "phone": c.phone or "",
                "country": c.country,
            }
            for c in list_customers(s)
        ]


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="cust-version", data=0),
        html.Div(id="customers-page-header", children=page_header(_cust_t, help=_cust_h)),
        dmc.Card(
            withBorder=True,
            padding="lg",
            children=[
                dmc.Text("New customer", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                dmc.SimpleGrid(
                    cols={"base": 1, "sm": 2},
                    children=[
                        dmc.TextInput(id="cust-name", label="Name", required=True),
                        dmc.TextInput(id="cust-phone", label="Phone"),
                        dmc.TextInput(id="cust-email", label="Email"),
                        dmc.TextInput(id="cust-country", label="Country"),
                    ],
                ),
                dmc.Textarea(id="cust-address", label="Address", autosize=True, minRows=2, mt="sm"),
                dmc.Button("Create customer", id="cust-save", color="cpi", mt="md"),
            ],
        ),
        dmc.Text(id="cust-msg", size="sm"),
        AgGrid(
            id="cust-grid",
            columnDefs=COLS,
            rowData=[],
            dashGridOptions={"pagination": True, "paginationPageSize": 15},
            style={"height": "400px", "width": "100%"},
            className="ag-theme-alpine",
        ),
    ],
)


@callback(
    Output("customers-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def customers_header(pathname, loc):
    if normalize_path(pathname) != "/customers":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "customers")
    return page_header(t, help=h)


@callback(
    Output("cust-grid", "rowData"),
    Input("_pages_location", "pathname"),
    Input("cust-version", "data"),
)
def cust_load(pathname, _v):
    if "/customers" not in (pathname or ""):
        raise PreventUpdate
    return _rows()


@callback(
    Output("cust-version", "data"),
    Output("cust-msg", "children"),
    Input("cust-save", "n_clicks"),
    State("cust-version", "data"),
    State("cust-name", "value"),
    State("cust-phone", "value"),
    State("cust-email", "value"),
    State("cust-address", "value"),
    State("cust-country", "value"),
    prevent_initial_call=True,
)
def cust_save(_n, ver, name, phone, email, address, country):
    if not _can_write():
        raise PreventUpdate
    if not (name or "").strip():
        return (ver or 0), dmc.Alert("Name is required.", color="yellow", title="Validation")
    v = (ver or 0) + 1
    with db_session() as s:
        create_customer(
            s,
            user_id=_uid(),
            name=name.strip(),
            phone=phone,
            email=email,
            address=address,
            country=(country or "").strip(),
        )
    return v, dmc.Alert("Customer created.", color="green", title="OK")
