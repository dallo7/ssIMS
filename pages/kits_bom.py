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


def _section_label(text: str) -> dmc.Text:
    return dmc.Text(text, fw=600, size="sm", tt="uppercase", c="dimmed")


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        dcc.Store(id="kit-version", data=0),
        html.Div(id="kits-bom-page-header", children=page_header(_kit_t, help=_kit_h)),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 2},
            spacing="lg",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=dmc.Stack(
                        gap="md",
                        children=[
                            _section_label("Bill of materials"),
                            dmc.Select(
                                id="kit-parent",
                                label="Finished product",
                                data=[],
                                searchable=True,
                                clearable=True,
                                nothingFoundMessage="No items",
                                placeholder="Select the product to define…",
                            ),
                            dmc.SimpleGrid(
                                cols={"base": 1, "sm": 2},
                                spacing="sm",
                                children=[
                                    dmc.Select(
                                        id="kit-comp",
                                        label="Component",
                                        data=[],
                                        searchable=True,
                                        clearable=True,
                                        nothingFoundMessage="No items",
                                        placeholder="Search components…",
                                    ),
                                    dmc.NumberInput(
                                        id="kit-per",
                                        label="Qty per parent",
                                        min=0,
                                        value=1,
                                        decimalScale=4,
                                    ),
                                ],
                            ),
                            dmc.Group(
                                [
                                    dmc.Button("Save component", id="kit-save-bom", color="cpi", style={"flex": 1}),
                                    dmc.Button("Refresh", id="kit-refresh", variant="light"),
                                ],
                                gap="sm",
                                wrap="nowrap",
                            ),
                        ],
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    children=dmc.Stack(
                        gap="md",
                        children=[
                            _section_label("Assemble kits"),
                            dmc.NumberInput(
                                id="kit-build-qty",
                                label="Quantity to build",
                                min=0,
                                value=0,
                            ),
                            dmc.Select(
                                id="kit-build-loc",
                                label="Receive into location",
                                data=[],
                                clearable=True,
                                placeholder="Optional",
                            ),
                            dmc.Button("Assemble", id="kit-assemble", color="green", fullWidth=True),
                        ],
                    ),
                ),
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


_NUM_CELL = {"textAlign": "right", "fontVariantNumeric": "tabular-nums", "whiteSpace": "nowrap"}


def _fmt_qty(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return f"{int(f):,}" if f.is_integer() else f"{f:,.4f}".rstrip("0").rstrip(".")


@callback(
    Output("kit-parent", "data"),
    Output("kit-comp", "data"),
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
    return opts, opts, locs


@callback(
    Output("kit-bom-table", "children"),
    Input("kit-parent", "value"),
    Input("kit-version", "data"),
    Input("kit-refresh", "n_clicks"),
)
def kit_bom_table(parent_id, _v, _r):
    empty_card = dmc.Card(
        withBorder=True,
        padding="md",
        children=dmc.Stack(
            gap="sm",
            children=[
                _section_label("Components"),
                dmc.Text(
                    "Pick a finished product above to view or edit its components.",
                    c="dimmed",
                    size="sm",
                ),
            ],
        ),
    )
    if not parent_id:
        return empty_card
    with db_session() as s:
        lines = list_bom_lines(s, int(parent_id))
        items = {i.id: i.name for i in list_items(s, active_only=False)}
    head = html.Tr(
        [
            html.Th("#", style=_NUM_CELL),
            html.Th("Component"),
            html.Th("Qty per parent", style=_NUM_CELL),
            html.Th(""),
        ]
    )
    if not lines:
        body = html.Tbody(
            [
                html.Tr(
                    html.Td(
                        dmc.Text("No components yet — add one above.", size="sm", c="dimmed", ta="center"),
                        colSpan=4,
                        style={"padding": "1rem"},
                    )
                )
            ]
        )
    else:
        rows = []
        for ln in lines:
            rows.append(
                html.Tr(
                    [
                        html.Td(str(ln.id), style=_NUM_CELL),
                        html.Td(items.get(ln.component_item_id, str(ln.component_item_id))),
                        html.Td(_fmt_qty(ln.quantity_per), style=_NUM_CELL),
                        html.Td(
                            dmc.Button(
                                "Remove",
                                size="xs",
                                color="red",
                                variant="light",
                                id={"type": "kit-del", "lid": ln.id},
                            ),
                            style={"textAlign": "right"},
                        ),
                    ]
                )
            )
        body = html.Tbody(rows)
    tbl = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[html.Thead(head), body],
    )
    return dmc.Card(
        withBorder=True,
        padding="md",
        children=dmc.Stack(
            gap="sm",
            children=[
                dmc.Group(
                    [
                        _section_label("Components"),
                        dmc.Text(f"{len(lines)} component(s)", size="xs", c="dimmed"),
                    ],
                    justify="space-between",
                ),
                tbl,
            ],
        ),
    )


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
