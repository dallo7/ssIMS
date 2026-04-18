import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session

from database import models
from database.dal import assemble_kit, delete_bom_line, list_bom_lines, list_items, upsert_bom_line
from database.engine import db_session
from sqlalchemy import select
from components.page import page_header
from utils import i18n
from utils.navigation import normalize_path

register_page(__name__, path="/kits-bom", name="Kits & BOM", title="Kits & BOM", order=20)

_kit_t, _kit_h = i18n.page_heading("en", "kits_bom")


def _uid():
    return int(session.get("user_id") or 1)


def _can_write():
    return session.get("role") in ("ADMIN", "MANAGER", "STOCK_CLERK")


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="kit-version", data=0),
        html.Div(id="kits-bom-page-header", children=page_header(_kit_t, help=_kit_h)),
        dmc.Card(
            withBorder=True,
            padding="lg",
            children=[
                dmc.Text("Bill of materials", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                dmc.Select(id="kit-parent", label="Parent (finished) SKU", data=[]),
                dmc.SimpleGrid(
                    cols={"base": 1, "sm": 2},
                    mt="md",
                    children=[
                        dmc.TextInput(id="kit-comp", label="Component item ID (pk)"),
                        dmc.NumberInput(id="kit-per", label="Qty per 1 parent", min=0, value=1, decimalScale=4),
                    ],
                ),
                dmc.Group(
                    [
                        dmc.Button("Save BOM line", id="kit-save-bom", color="cpi"),
                        dmc.Button("Refresh table", id="kit-refresh", variant="light"),
                    ],
                    mt="sm",
                    gap="sm",
                ),
            ],
        ),
        dmc.Card(
            withBorder=True,
            padding="lg",
            children=[
                dmc.Text("Assemble kits", fw=600, mb="sm", size="sm", tt="uppercase", opacity=0.85),
                dmc.Text(
                    "Consumes components (FIFO) and receives finished goods at rolled-up cost.",
                    size="xs",
                    c="dimmed",
                    mb="sm",
                ),
                dmc.NumberInput(id="kit-build-qty", label="How many parents to build", min=0, value=0),
                dmc.Select(id="kit-build-loc", label="Location (optional)", data=[], clearable=True),
                dmc.Button("Assemble", id="kit-assemble", color="green", mt="sm"),
            ],
        ),
        dmc.Text(id="kit-msg", size="sm"),
        html.Div(id="kit-bom-table"),
    ],
)


@callback(
    Output("kits-bom-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def kit_header(pathname, loc):
    if normalize_path(pathname) != "/kits-bom":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "kits_bom")
    return page_header(t, help=h)


@callback(
    Output("kit-parent", "data"),
    Output("kit-build-loc", "data"),
    Input("_pages_location", "pathname"),
    Input("kit-version", "data"),
)
def kit_opts(pathname, _v):
    if "/kits-bom" not in (pathname or ""):
        raise PreventUpdate
    with db_session() as s:
        items = list_items(s, active_only=True)
        opts = [{"label": f"{i.item_id} — {i.name}", "value": str(i.id)} for i in items]
        locs = [
            {"label": f"{x.warehouse} / {x.name}", "value": str(x.id)}
            for x in s.scalars(select(models.StorageLocation).order_by(models.StorageLocation.name)).all()
        ]
    return opts, locs


@callback(
    Output("kit-bom-table", "children"),
    Input("kit-parent", "value"),
    Input("kit-version", "data"),
    Input("kit-refresh", "n_clicks"),
)
def kit_bom_table(parent_id, _v, _r):
    if not parent_id:
        return dmc.Text("Select a parent SKU.", c="dimmed", size="sm")
    with db_session() as s:
        lines = list_bom_lines(s, int(parent_id))
        items = {i.id: i.name for i in list_items(s, active_only=False)}
    if not lines:
        return dmc.Text("No BOM lines yet.", c="dimmed", size="sm")
    head = html.Tr(
        [
            html.Th("Line id"),
            html.Th("Component"),
            html.Th("Qty / parent"),
            html.Th(""),
        ]
    )
    body = []
    for ln in lines:
        body.append(
            html.Tr(
                [
                    html.Td(str(ln.id)),
                    html.Td(items.get(ln.component_item_id, str(ln.component_item_id))),
                    html.Td(str(ln.quantity_per)),
                    html.Td(
                        dmc.Button(
                            "Delete",
                            size="xs",
                            color="red",
                            variant="light",
                            id={"type": "kit-del", "lid": ln.id},
                        )
                    ),
                ]
            )
        )
    return dmc.Table(striped=True, highlightOnHover=True, withTableBorder=True, children=[html.Thead(head), html.Tbody(body)])


@callback(
    Output("kit-version", "data"),
    Output("kit-msg", "children"),
    Input("kit-save-bom", "n_clicks"),
    Input("kit-assemble", "n_clicks"),
    Input({"type": "kit-del", "lid": ALL}, "n_clicks"),
    State("kit-version", "data"),
    State("kit-parent", "value"),
    State("kit-comp", "value"),
    State("kit-per", "value"),
    State("kit-build-qty", "value"),
    State("kit-build-loc", "value"),
    prevent_initial_call=True,
)
def kit_actions(_s, _a, _d, ver, parent, comp, per, bqty, bloc):
    if not _can_write():
        raise PreventUpdate
    ctx = dash.callback_context
    tid = ctx.triggered_id
    v = (ver or 0) + 1
    uid = _uid()
    try:
        if tid == "kit-save-bom" and parent and comp and per:
            with db_session() as s:
                ok, msg = upsert_bom_line(
                    s,
                    parent_item_id=int(parent),
                    component_item_id=int(comp),
                    quantity_per=float(per),
                    user_id=uid,
                )
            return v, dmc.Alert(msg, color="green" if ok else "yellow", title="BOM")
        if tid == "kit-assemble" and parent and bqty:
            with db_session() as s:
                ok, msg = assemble_kit(
                    s,
                    parent_item_id=int(parent),
                    quantity_built=float(bqty),
                    performed_by=uid,
                    storage_location_id=int(bloc) if bloc else None,
                )
            return v, dmc.Alert(msg, color="green" if ok else "red", title="Assemble")
        if isinstance(tid, dict) and tid.get("type") == "kit-del":
            lid = int(tid["lid"])
            with db_session() as s:
                delete_bom_line(s, lid, uid)
            return v, dmc.Alert("BOM line removed.", color="green", title="OK")
    except Exception as e:
        return (ver or 0), dmc.Alert(str(e), color="red", title="Error")
    raise PreventUpdate
