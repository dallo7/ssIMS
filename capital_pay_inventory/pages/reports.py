import io
from pathlib import Path

import dash
import dash_mantine_components as dmc
import plotly.express as px
from dash import Input, Output, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from database import models
from database.dal import list_items
from database.engine import db_session

register_page(__name__, path="/reports", name="Reports", title="Reports", order=7)

_CAPITALPAY_LOGO = Path(__file__).resolve().parent.parent / "assets" / "capitalpay-logo.png"


def _ok():
    return session.get("user_id")


layout = dmc.Stack(
    [
        dmc.Title("Reports & analytics", order=3),
        dmc.SimpleGrid(
            cols={"base": 1, "lg": 2},
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Inventory valuation by category", fw=600, mb="sm"),
                        dcc.Graph(id="rep-val-chart"),
                        dmc.Button("Export valuation CSV", id="rep-val-csv", variant="outline", mt="sm"),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    children=[
                        dmc.Text("Reorder report (at/below reorder point)", fw=600, mb="sm"),
                        html.Div(id="rep-reorder-table"),
                        dmc.Button("Export reorder CSV", id="rep-reo-csv", variant="outline", mt="sm"),
                    ],
                ),
            ],
        ),
        dmc.Card(
            withBorder=True,
            padding="md",
            children=[
                dmc.Text("Summary PDF", fw=600, mb="sm"),
                dmc.Button("Download PDF snapshot", id="rep-pdf", color="cpi"),
            ],
        ),
        dcc.Download(id="rep-dl"),
    ],
    gap="md",
)


@callback(
    Output("rep-val-chart", "figure"),
    Output("rep-reorder-table", "children"),
    Input("url", "pathname"),
)
def rep_load(pathname):
    if "/reports" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate
    with db_session() as s:
        rows = s.execute(
            select(models.Category.name, func.sum(models.InventoryItem.quantity_in_stock * models.InventoryItem.unit_cost))
            .join(models.InventoryItem, models.InventoryItem.category_id == models.Category.id)
            .where(models.InventoryItem.is_active == True)  # noqa: E712
            .group_by(models.Category.name)
        ).all()
        items = list_items(s, active_only=True)
    fig = px.bar([{"c": r[0], "v": float(r[1] or 0)} for r in rows], x="c", y="v", title="Valuation (cost basis)")
    fig.update_layout(template="plotly_white", margin=dict(t=40, b=40))
    reo = [i for i in items if i.quantity_in_stock <= i.reorder_point]
    tbl = dmc.Table(
        striped=True,
        highlightOnHover=True,
        children=[
            html.Thead(html.Tr([html.Th("SKU"), html.Th("Name"), html.Th("Qty"), html.Th("Reorder"), html.Th("Suggest")])),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(i.item_id),
                            html.Td(i.name[:40]),
                            html.Td(i.quantity_in_stock),
                            html.Td(i.reorder_point),
                            html.Td(i.reorder_quantity),
                        ]
                    )
                    for i in reo[:40]
                ]
            ),
        ],
    )
    return fig, tbl


@callback(
    Output("rep-dl", "data"),
    Input("rep-val-csv", "n_clicks"),
    Input("rep-reo-csv", "n_clicks"),
    Input("rep-pdf", "n_clicks"),
    prevent_initial_call=True,
)
def rep_export(vc, rc, pdf):
    if not _ok():
        raise PreventUpdate
    tid = dash.callback_context.triggered_id
    if tid == "rep-val-csv":
        buf = io.StringIO()
        with db_session() as s:
            rows = s.execute(
                select(models.Category.name, func.sum(models.InventoryItem.quantity_in_stock * models.InventoryItem.unit_cost))
                .join(models.InventoryItem, models.InventoryItem.category_id == models.Category.id)
                .where(models.InventoryItem.is_active == True)  # noqa: E712
                .group_by(models.Category.name)
            ).all()
        for r in rows:
            buf.write(f"{r[0]},{float(r[1] or 0)}\n")
        return dict(content=buf.getvalue(), filename="valuation_by_category.csv", type="text/csv")
    if tid == "rep-reo-csv":
        buf = io.StringIO()
        buf.write("item_id,name,qty,reorder_point,reorder_qty\n")
        with db_session() as s:
            for i in list_items(s, active_only=True):
                if i.quantity_in_stock <= i.reorder_point:
                    buf.write(f"{i.item_id},{i.name},{i.quantity_in_stock},{i.reorder_point},{i.reorder_quantity}\n")
        return dict(content=buf.getvalue(), filename="reorder_report.csv", type="text/csv")
    if tid == "rep-pdf":
        bio = io.BytesIO()
        c = canvas.Canvas(bio, pagesize=letter)
        title = "Smart-Shop Stock Inventory — snapshot · CapitalPay"
        if _CAPITALPAY_LOGO.is_file():
            c.drawImage(str(_CAPITALPAY_LOGO), 72, 698, width=22, height=22, preserveAspectRatio=True, mask="auto")
            c.drawString(100, 718, title)
        else:
            c.drawString(72, 718, title)
        y = 686
        with db_session() as s:
            for i in list_items(s, active_only=True)[:40]:
                c.drawString(72, y, f"{i.item_id}  {i.name[:50]}  qty={i.quantity_in_stock}")
                y -= 16
                if y < 72:
                    c.showPage()
                    y = 720
        c.save()
        return dict(content=bio.getvalue(), filename="inventory_snapshot.pdf", type="application/pdf")
    raise PreventUpdate
