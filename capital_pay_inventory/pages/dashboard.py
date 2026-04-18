import dash
import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, register_page
from dash_iconify import DashIconify
from flask import session

from database.dal import (
    abc_distribution,
    dashboard_kpis,
    list_alerts_with_ack_state,
    movement_timeseries,
    stock_by_category,
    top_movers,
)
from database.engine import db_session

register_page(__name__, path="/", name="Dashboard", title="Dashboard", order=0)


def _can_view():
    return bool(session.get("user_id"))


layout = dmc.Stack(
    [
        dmc.Group(
            [
                dmc.DatePickerRange(id="dash-dates", mb="sm"),
                dmc.SegmentedControl(
                    id="dash-move-window",
                    data=[
                        {"label": "30d", "value": "30"},
                        {"label": "60d", "value": "60"},
                        {"label": "90d", "value": "90"},
                    ],
                    value="30",
                    mb="sm",
                ),
            ],
            grow=True,
        ),
        dmc.SimpleGrid(
            cols={"base": 1, "sm": 2, "lg": 5},
            spacing="md",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="md",
                    children=dmc.Group(
                        [DashIconify(icon="tabler:packages", width=28), dmc.Stack(gap=0, id="kpi-skus-inner")],
                        align="flex-start",
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="md",
                    children=dmc.Group(
                        [DashIconify(icon="tabler:coins", width=28), dmc.Stack(gap=0, id="kpi-val-inner")],
                        align="flex-start",
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="md",
                    children=dmc.Group(
                        [DashIconify(icon="tabler:alert-triangle", width=28), dmc.Stack(gap=0, id="kpi-low-inner")],
                        align="flex-start",
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="md",
                    children=dmc.Group(
                        [DashIconify(icon="tabler:ban", width=28), dmc.Stack(gap=0, id="kpi-oos-inner")],
                        align="flex-start",
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    padding="md",
                    radius="md",
                    children=dmc.Group(
                        [DashIconify(icon="tabler:truck", width=28), dmc.Stack(gap=0, id="kpi-po-inner")],
                        align="flex-start",
                    ),
                ),
            ],
        ),
        dmc.SimpleGrid(
            cols={"base": 1, "lg": 2},
            spacing="md",
            children=[
                dcc.Graph(id="chart-cat", config={"displayModeBar": True}),
                dcc.Graph(id="chart-abc", config={"displayModeBar": True}),
            ],
        ),
        dcc.Graph(id="chart-move", config={"displayModeBar": True}),
        dmc.SimpleGrid(
            cols={"base": 1, "lg": 2},
            spacing="md",
            children=[dcc.Graph(id="chart-fast", config={"displayModeBar": True}), dcc.Graph(id="chart-slow", config={"displayModeBar": True})],
        ),
        dmc.Card(
            withBorder=True,
            padding="md",
            radius="md",
            children=[
                dmc.Title("Operational alerts", order=4, mb="sm"),
                html.Div(id="dash-alerts-panel"),
            ],
        ),
    ],
    gap="md",
)


@callback(
    Output("kpi-skus-inner", "children"),
    Output("kpi-val-inner", "children"),
    Output("kpi-low-inner", "children"),
    Output("kpi-oos-inner", "children"),
    Output("kpi-po-inner", "children"),
    Output("chart-cat", "figure"),
    Output("chart-abc", "figure"),
    Output("chart-move", "figure"),
    Output("chart-fast", "figure"),
    Output("chart-slow", "figure"),
    Output("dash-alerts-panel", "children"),
    Input("dash-dates", "value"),
    Input("dash-move-window", "value"),
    Input("url", "pathname"),
)
def refresh_dashboard(dates, window, _pathname):
    if not _can_view():
        return [dash.no_update] * 11
    window_days = int(window or 30)
    with db_session() as s:
        k = dashboard_kpis(s)
        cats = stock_by_category(s)
        abc = abc_distribution(s)
        ts = movement_timeseries(s, window_days)
        fast, slow = top_movers(s, window_days, 10)
        alerts = [a for a in list_alerts_with_ack_state(s, 50) if not a["acknowledged"]]

    def kpi_stack(title, val, sub=None):
        return [dmc.Text(title, size="xs", c="dimmed"), dmc.Title(str(val), order=3), dmc.Text(sub or "", size="xs")] if sub else [dmc.Text(title, size="xs", c="dimmed"), dmc.Title(str(val), order=3)]

    fig_cat = px.bar(cats or [{"category": "—", "qty": 0}], x="category", y="qty", title="Stock level by category")
    fig_cat.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=50, b=40))
    fig_abc = px.pie(abc or [{"class": "B", "count": 1}], names="class", values="count", title="ABC class distribution (by SKU count)", hole=0.45)
    fig_abc.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=50, b=20))
    df_ts = ts or [{"date": "", "net": 0}]
    fig_m = go.Figure()
    fig_m.add_trace(go.Scatter(x=[r["date"] for r in df_ts], y=[r["net"] for r in df_ts], mode="lines+markers", name="Net movement"))
    fig_m.update_layout(title=f"Stock movement (net receive − issue) — last {window_days} days", template="plotly_white", margin=dict(l=40, r=20, t=50, b=40))
    fig_f = px.bar(fast or [{"name": "—", "qty": 0}], x="name", y="qty", title="Top fast-moving (issue volume)")
    fig_f.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=50, b=120))
    fig_s = px.bar(slow or [{"name": "—", "qty": 0}], x="name", y="qty", title="Slow-moving (lowest issue volume)")
    fig_s.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=50, b=120))

    alert_children = (
        dmc.Stack(
            [dmc.Alert(a["message"], color="red" if a["severity"] == "CRITICAL" else "yellow", title=a["severity"]) for a in alerts[:12]],
            gap="xs",
        )
        if alerts
        else dmc.Text("No active alerts.", c="dimmed")
    )

    return (
        kpi_stack("Total SKUs", int(k["skus"])),
        kpi_stack("Stock value (cost)", f"SSP {k['stock_value']:,.0f}"),
        kpi_stack("Low stock", int(k["low_stock"])),
        kpi_stack("Out of stock", int(k["out_of_stock"])),
        kpi_stack("Pending POs", int(k["pending_po"])),
        fig_cat,
        fig_abc,
        fig_m,
        fig_f,
        fig_s,
        alert_children,
    )
