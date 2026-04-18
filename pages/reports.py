import base64
import io
from datetime import datetime, timedelta
from pathlib import Path

import dash
import dash_mantine_components as dmc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate
from flask import session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from database import models
from database.dal import daily_issue_sales_proxy, list_items, movement_summary
from database.engine import db_session
from components.page import page_header
from utils import i18n
from utils.app_text import primary_app_name
from utils.navigation import normalize_path
from utils.predictive_analytics import (
    apply_what_if_to_forecast,
    build_kpi_block,
    daily_to_prophet_df,
    prophet_runtime_info,
    run_prophet_forecast,
)

register_page(__name__, path="/reports", name="Reports", title="Reports", order=7)

_rep_t, _rep_h = i18n.page_heading("en", "reports")

_CAPITALPAY_LOGO = Path(__file__).resolve().parent.parent / "assets" / "capitalpay-logo.png"


def _plotly_template(theme_data: dict | None) -> str:
    return "plotly_dark" if (theme_data or {}).get("scheme", "dark") == "dark" else "plotly_white"


def _ok():
    return session.get("user_id")


def _kpi_card(title: str, value: str, hint: str = ""):
    return dmc.Card(
        withBorder=True,
        padding="md",
        radius="md",
        className="cpi-rep-kpi-card",
        children=[
            dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=600, style={"letterSpacing": "0.04em"}),
            dmc.Title(value, order=4, mt=6, className="cpi-rep-kpi-value"),
            dmc.Text(hint, size="xs", c="dimmed", mt=4) if hint else html.Span(),
        ],
    )


def _fmt_report_day(ds: str) -> str:
    try:
        return datetime.strptime(str(ds)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(ds)


def _fmt_units_cell(x: float) -> str:
    return f"{x:,.2f}"


def _fmt_ssp_cell(x: float) -> str:
    return f"SSP {x:,.2f}"


def _pad_range(lo: float, hi: float, *, frac: float = 0.08) -> tuple[float, float]:
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return 0.0, 1.0
    span = hi - lo
    pad = span * frac if span > 1e-12 else max(abs(hi) * frac, 1.0)
    return lo - pad, hi + pad


def _apply_axis_titles(fig: go.Figure, *, x_title: str, y_title: str) -> None:
    fig.update_xaxes(title_text=x_title, showgrid=True, zeroline=True, automargin=True)
    fig.update_yaxes(title_text=y_title, showgrid=True, zeroline=True, automargin=True)


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        html.Div(id="reports-page-header", children=page_header(_rep_t, help=_rep_h)),
        # --- KPIs (analytics + planning) ---
        dmc.Stack(
            gap="sm",
            children=[
                dmc.Title("Key performance indicators", order=3, fw=700),
                dmc.Text(
                    "Top row summarises inventory health; cards below summarise demand using stock-out (ISSUE) as a sales proxy.",
                    size="sm",
                    c="dimmed",
                ),
                dmc.SimpleGrid(
                    id="rep-kpi-health",
                    cols={"base": 1, "sm": 2, "lg": 5},
                    spacing="md",
                    children=[],
                ),
                dmc.SimpleGrid(
                    id="rep-kpi-analytics",
                    cols={"base": 1, "sm": 2, "lg": 5},
                    spacing="md",
                    children=[],
                ),
            ],
        ),
        dmc.Paper(
            className="cpi-toolbar-paper",
            p="md",
            radius="md",
            withBorder=True,
            children=dmc.Stack(
                gap="md",
                children=[
                    dmc.Text("Forecast controls", fw=600, size="sm"),
                    dmc.Group(
                        [
                            dmc.Stack(
                                gap="xs",
                                style={"minWidth": 200, "flex": 1},
                                children=[
                                    dmc.Text("History window", size="xs", c="dimmed"),
                                    dmc.Select(
                                        id="rep-hist-days",
                                        data=[
                                            {"label": "90 days", "value": "90"},
                                            {"label": "180 days", "value": "180"},
                                            {"label": "365 days", "value": "365"},
                                        ],
                                        value="180",
                                    ),
                                ],
                            ),
                            dmc.Stack(
                                gap="xs",
                                style={"minWidth": 200, "flex": 1},
                                children=[
                                    dmc.Text("Forecast horizon", size="xs", c="dimmed"),
                                    dmc.Select(
                                        id="rep-fc-horizon",
                                        data=[
                                            {"label": "14 days", "value": "14"},
                                            {"label": "30 days", "value": "30"},
                                            {"label": "60 days", "value": "60"},
                                        ],
                                        value="30",
                                    ),
                                ],
                            ),
                            dmc.Stack(
                                gap="xs",
                                style={"minWidth": 240, "flex": 2},
                                children=[
                                    dmc.Text("What-if vs Prophet baseline (% demand shift)", size="xs", c="dimmed"),
                                    dmc.Slider(
                                        id="rep-whatif",
                                        min=-30,
                                        max=50,
                                        step=5,
                                        value=0,
                                        marks=[
                                            {"value": -30, "label": "-30%"},
                                            {"value": 0, "label": "0"},
                                            {"value": 50, "label": "+50%"},
                                        ],
                                        mb="xl",
                                    ),
                                ],
                            ),
                        ],
                        grow=True,
                        align="flex-end",
                        wrap="wrap",
                    ),
                ],
            ),
        ),
        html.Div(id="rep-ana-status", children=[]),
        # --- Details by category ---
        dmc.Title("Details by category", order=3, fw=700, mt="sm"),
        dmc.Stack(
            gap="xl",
            children=[
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    children=[
                        dmc.Text(
                            "1 — Operational reports & exports",
                            fw=700,
                            mb="md",
                            size="sm",
                            tt="uppercase",
                        ),
                        dmc.SimpleGrid(
                            cols={"base": 1, "lg": 2},
                            spacing="lg",
                            children=[
                                dmc.Card(
                                    withBorder=True,
                                    padding="lg",
                                    children=[
                                        dmc.Text(
                                            "Inventory valuation by category",
                                            fw=600,
                                            mb="md",
                                            size="sm",
                                            tt="uppercase",
                                            opacity=0.85,
                                        ),
                                        dcc.Graph(id="rep-val-chart"),
                                        dmc.Button("Export valuation CSV", id="rep-val-csv", variant="outline", mt="sm"),
                                    ],
                                ),
                                dmc.Card(
                                    withBorder=True,
                                    padding="lg",
                                    children=[
                                        dmc.Text(
                                            "Reorder report (at/below reorder point)",
                                            fw=600,
                                            mb="md",
                                            size="sm",
                                            tt="uppercase",
                                            opacity=0.85,
                                        ),
                                        html.Div(id="rep-reorder-table"),
                                        dmc.Button("Export reorder CSV", id="rep-reo-csv", variant="outline", mt="sm"),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Card(
                            withBorder=True,
                            padding="lg",
                            mt="md",
                            children=[
                                dmc.Text("Summary PDF", fw=600, mb="md", size="sm", tt="uppercase", opacity=0.85),
                                dmc.Button("Download PDF snapshot", id="rep-pdf", color="cpi"),
                            ],
                        ),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    className="cpi-rep-analytics-card",
                    children=[
                        dmc.Group(
                            justify="space-between",
                            align="flex-start",
                            wrap="wrap",
                            gap="sm",
                            mb="xs",
                            children=[
                                dmc.Stack(
                                    gap=4,
                                    style={"minWidth": 200},
                                    children=[
                                        dmc.Text(
                                            "2 — Demand analytics",
                                            fw=700,
                                            size="sm",
                                            tt="uppercase",
                                        ),
                                        dmc.Text(
                                            "Stock-out (ISSUE) treated as sales · revenue = qty × unit price",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                    ],
                                ),
                                dmc.Group(
                                    gap="xs",
                                    children=[
                                        dmc.Badge("Prophet", color="cpi", variant="light", size="sm"),
                                        dmc.Badge("What-if", color="gray", variant="outline", size="sm"),
                                    ],
                                ),
                            ],
                        ),
                        dmc.Divider(my="sm"),
                        dmc.Alert(
                            "Each ISSUE line is a sale: units sold = quantity issued; revenue proxy = Σ(qty × current "
                            "SKU unit_price). Prophet uses that series; the what-if control scales only the future "
                            "part of the forecast.",
                            title="Modelling assumption",
                            color="blue",
                            variant="light",
                            mb="md",
                        ),
                        dmc.Text("Forecast vs history", size="xs", fw=600, c="dimmed", tt="uppercase", mb="xs"),
                        dmc.Paper(
                            className="cpi-rep-chart-shell",
                            p="xs",
                            radius="md",
                            children=[
                                dcc.Graph(
                                    id="rep-ana-fig-prophet",
                                    config={"displayModeBar": True, "responsive": True},
                                    style={"minHeight": 420},
                                )
                            ],
                        ),
                        dmc.Text(
                            "Decomposition (trend + seasonality)",
                            size="xs",
                            fw=600,
                            c="dimmed",
                            tt="uppercase",
                            mt="lg",
                            mb="xs",
                        ),
                        dmc.Paper(
                            className="cpi-rep-chart-shell",
                            p="xs",
                            radius="md",
                            children=[
                                dcc.Graph(
                                    id="rep-ana-fig-prophet-comp",
                                    config={"displayModeBar": True, "responsive": True},
                                    style={"minHeight": 380},
                                )
                            ],
                        ),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    className="cpi-rep-analytics-card",
                    children=[
                        dmc.Group(
                            justify="space-between",
                            align="flex-start",
                            wrap="wrap",
                            gap="sm",
                            mb="xs",
                            children=[
                                dmc.Stack(
                                    gap=4,
                                    style={"minWidth": 200},
                                    children=[
                                        dmc.Text(
                                            "3 — Daily observations",
                                            fw=700,
                                            size="sm",
                                            tt="uppercase",
                                        ),
                                        dmc.Text(
                                            "Most recent days first · amounts in SSP where shown",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                    ],
                                ),
                                dmc.Badge("Up to 60 rows", color="navy", variant="light", size="sm"),
                            ],
                        ),
                        dmc.Divider(my="sm"),
                        html.Div(id="rep-ana-table-wrap"),
                    ],
                ),
            ],
        ),
        dcc.Download(id="rep-dl"),
    ],
)


@callback(
    Output("reports-page-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def reports_page_header(pathname, loc):
    if normalize_path(pathname) != "/reports":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    t, h = i18n.page_heading(lang, "reports")
    return page_header(t, help=h)


@callback(
    Output("rep-val-chart", "figure"),
    Output("rep-reorder-table", "children"),
    Input("_pages_location", "pathname"),
    Input("theme-store", "data"),
)
def rep_load(pathname, theme_data):
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
    data = [{"c": r[0], "v": float(r[1] or 0)} for r in rows]
    fig = px.bar(data or [{"c": "—", "v": 0}], x="c", y="v", title="Valuation (cost basis)")
    pt = _plotly_template(theme_data)
    fig.update_layout(template=pt, margin=dict(t=48, b=80, l=72, r=32))
    vals = [d["v"] for d in data] if data else [0.0]
    vmax = max(vals) if vals else 0.0
    y0, y1 = _pad_range(0.0, vmax if vmax > 0 else 1.0, frac=0.1)
    fig.update_yaxes(range=[max(0.0, y0), y1])
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=[d["c"] for d in data] if data else ["—"],
    )
    _apply_axis_titles(fig, x_title="Category", y_title="SSP (cost basis)")
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
    Output("rep-kpi-health", "children"),
    Output("rep-kpi-analytics", "children"),
    Output("rep-ana-status", "children"),
    Output("rep-ana-fig-prophet", "figure"),
    Output("rep-ana-fig-prophet-comp", "figure"),
    Output("rep-ana-table-wrap", "children"),
    Input("_pages_location", "pathname"),
    Input("theme-store", "data"),
    Input("rep-hist-days", "value"),
    Input("rep-fc-horizon", "value"),
    Input("rep-whatif", "value"),
)
def rep_analytics_bundle(pathname, theme_data, hist_days, fc_horizon, whatif):
    if "/reports" not in (pathname or ""):
        raise PreventUpdate
    if not _ok():
        raise PreventUpdate

    pt = _plotly_template(theme_data)
    days = int(hist_days or 180)
    periods = int(fc_horizon or 30)
    whatif_f = float(whatif or 0)

    until = datetime.utcnow()
    since_30 = until - timedelta(days=30)
    since_mov = until - timedelta(days=days)

    with db_session() as s:
        rows = s.execute(
            select(models.Category.name, func.sum(models.InventoryItem.quantity_in_stock * models.InventoryItem.unit_cost))
            .join(models.InventoryItem, models.InventoryItem.category_id == models.Category.id)
            .where(models.InventoryItem.is_active == True)  # noqa: E712
            .group_by(models.Category.name)
        ).all()
        items = list_items(s, active_only=True)
        mov = movement_summary(s, since_mov, until)
        mov30 = movement_summary(s, since_30, until)
        daily = daily_issue_sales_proxy(s, days)

    stock_value = sum(float(r[1] or 0) for r in rows)
    n_skus = len(items)
    low = sum(1 for i in items if 0 < i.quantity_in_stock < i.reorder_point)
    oos = sum(1 for i in items if i.quantity_in_stock <= 0)

    health_children = [
        _kpi_card("Active SKUs", f"{n_skus:,}", "Catalogue breadth"),
        _kpi_card("Inventory value (cost)", f"SSP {stock_value:,.0f}", "Stock quantity × unit cost"),
        _kpi_card("Low-stock SKUs", f"{low:,}", "Below reorder point"),
        _kpi_card("Out-of-stock SKUs", f"{oos:,}", "Qty ≤ 0"),
        _kpi_card("Issued (30d)", f"{mov30['issued']:,.1f} u", f"Net {mov['net']:+.1f} u over {days}d"),
    ]

    ddf = pd.DataFrame(daily) if daily else pd.DataFrame()
    if len(ddf):
        # Calendar-date window avoids tz-naive vs tz-aware Timestamp compare (pandas 2.2+).
        cut_d = (until - timedelta(days=30)).date()
        d_days = pd.to_datetime(ddf["ds"], errors="coerce").dt.date
        m = d_days >= cut_d
        last_30_units = float(ddf.loc[m, "y_units"].sum()) if "y_units" in ddf.columns else 0.0
        last_30_rev = float(ddf.loc[m, "y_revenue"].sum()) if "y_revenue" in ddf.columns else 0.0
    else:
        last_30_units = 0.0
        last_30_rev = 0.0

    df = daily_to_prophet_df(daily, "y_revenue")
    fc, fc_full, p_err = (
        run_prophet_forecast(df, periods) if len(df) else (None, None, "No ISSUE history.")
    )

    prophet_sum = None
    prophet_whatif_sum = None
    if fc is not None and len(df):
        hlen = len(df)
        prophet_sum = float(fc["yhat"].iloc[-periods:].sum())
        yhat_w = apply_what_if_to_forecast(fc, hlen, whatif_f)
        prophet_whatif_sum = float(yhat_w.iloc[-periods:].sum())

    kpi_meta = build_kpi_block(
        daily,
        last_30_units,
        last_30_rev,
        prophet_sum,
        p_err,
        whatif_f,
    )

    fc_label = f"Next {periods}d (Prophet)"
    what_hint = ""
    if whatif_f != 0 and prophet_whatif_sum is not None:
        what_hint = f" What-if total SSP {prophet_whatif_sum:,.0f}."

    analytics_children = [
        _kpi_card(
            "Avg daily revenue proxy",
            f"SSP {kpi_meta['avg_daily_revenue_proxy']:,.0f}",
            f"{kpi_meta['history_days_loaded']} days in window",
        ),
        _kpi_card(
            "Avg daily units (stock-out)",
            f"{kpi_meta['avg_daily_units_out']:,.1f}",
            "ISSUE = units sold",
        ),
        _kpi_card("Last 30d revenue proxy", f"SSP {last_30_rev:,.0f}", f"{last_30_units:,.1f} units"),
        _kpi_card(
            fc_label,
            f"SSP {prophet_sum:,.0f}" if prophet_sum is not None else "—",
            (kpi_meta["prophet_status"] if prophet_sum is None else "") + what_hint,
        ),
        _kpi_card(
            "Peak day (proxy)",
            f"SSP {kpi_meta['peak_day_revenue_proxy']:,.0f}",
            str(kpi_meta["peak_day"]),
        ),
    ]

    status = []
    prophet_ok, prophet_ver = prophet_runtime_info()
    if fc is not None:
        status.append(
            dmc.Alert(
                f"Prophet {prophet_ver} is active. Forecast uses additive seasonality on your stock-out revenue proxy.",
                title="Forecast engine",
                color="green",
                variant="light",
            )
        )
    elif not prophet_ok:
        status.append(
            dmc.Alert(
                "Prophet is not importable in this environment — install with pip install prophet "
                "(on Windows, enable long paths or use a shorter venv path if extraction fails).",
                title="Prophet",
                color="yellow",
                variant="light",
            )
        )
    elif p_err:
        status.append(dmc.Alert(p_err, title="Prophet", color="yellow", variant="light"))
    if len(df) < 10:
        status.append(
            dmc.Alert(
                "Add more daily ISSUE movements to strengthen the Prophet forecast (at least 10 days in the window).",
                color="blue",
                variant="light",
            )
        )

    # --- Prophet figure (explicit X/Y range = full data + forecast) ---
    fig_p = go.Figure()
    yhat_w = None
    if len(df):
        fig_p.add_trace(
            go.Scatter(
                x=df["ds"],
                y=df["y"],
                mode="lines+markers",
                name="Actual revenue proxy",
            )
        )
    if fc is not None and len(df):
        hlen = len(df)
        fig_p.add_trace(
            go.Scatter(
                x=fc["ds"],
                y=fc["yhat_upper"],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig_p.add_trace(
            go.Scatter(
                x=fc["ds"],
                y=fc["yhat_lower"],
                mode="lines",
                line=dict(width=0),
                fillcolor="rgba(99, 110, 250, 0.2)",
                fill="tonexty",
                name="Prophet 80% band",
                hoverinfo="skip",
            )
        )
        fig_p.add_trace(go.Scatter(x=fc["ds"], y=fc["yhat"], mode="lines", name="Prophet yhat"))
        yhat_w = apply_what_if_to_forecast(fc, hlen, whatif_f)
        fig_p.add_trace(
            go.Scatter(
                x=fc["ds"].iloc[hlen:],
                y=yhat_w.iloc[hlen:],
                mode="lines",
                line=dict(dash="dash", width=2),
                name=f"What-if ({whatif_f:+.0f}%)",
            )
        )
    fig_p.update_layout(
        title="Facebook Prophet — revenue proxy (ISSUE × unit price)",
        template=pt,
        margin=dict(t=52, b=72, l=72, r=32),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    if fc is not None and len(df):
        x0, x1 = fc["ds"].min(), fc["ds"].max()
        parts = [
            df["y"].astype(float).values,
            fc["yhat"].astype(float).values,
            fc["yhat_lower"].astype(float).values,
            fc["yhat_upper"].astype(float).values,
        ]
        if yhat_w is not None:
            parts.append(yhat_w.astype(float).values)
        y_concat = np.concatenate(parts)
        ymin, ymax = float(np.nanmin(y_concat)), float(np.nanmax(y_concat))
        y0, y1 = _pad_range(ymin, ymax)
        fig_p.update_xaxes(range=[x0, x1])
        fig_p.update_yaxes(range=[y0, y1])
    elif len(df):
        x0, x1 = df["ds"].min(), df["ds"].max()
        y0, y1 = _pad_range(float(df["y"].min()), float(df["y"].max()))
        fig_p.update_xaxes(range=[x0, x1])
        fig_p.update_yaxes(range=[y0, y1])
    _apply_axis_titles(fig_p, x_title="Date", y_title="SSP (revenue proxy)")

    # --- Prophet components (full X/Y) ---
    fig_pc = go.Figure()
    if fc_full is not None and "trend" in fc_full.columns:
        fig_pc.add_trace(
            go.Scatter(x=fc_full["ds"], y=fc_full["trend"], mode="lines", name="Trend")
        )
        for col, label in (
            ("weekly", "Weekly seasonality"),
            ("yearly", "Yearly seasonality"),
        ):
            if col in fc_full.columns and float(np.nanmax(np.abs(fc_full[col].astype(float)))) > 1e-9:
                fig_pc.add_trace(
                    go.Scatter(x=fc_full["ds"], y=fc_full[col], mode="lines", name=label)
                )
    else:
        fig_pc.add_annotation(
            text="Run a successful Prophet forecast to see decomposition.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
    fig_pc.update_layout(
        title="Prophet components",
        template=pt,
        margin=dict(t=52, b=72, l=72, r=32),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    if fc_full is not None and "trend" in fc_full.columns:
        x0, x1 = fc_full["ds"].min(), fc_full["ds"].max()
        ys = [fc_full["trend"].astype(float).values]
        for col in ("weekly", "yearly"):
            if col in fc_full.columns:
                ys.append(fc_full[col].astype(float).values)
        y_concat = np.concatenate(ys)
        ymin, ymax = float(np.nanmin(y_concat)), float(np.nanmax(y_concat))
        y0, y1 = _pad_range(ymin, ymax)
        fig_pc.update_xaxes(range=[x0, x1])
        fig_pc.update_yaxes(range=[y0, y1])
    _apply_axis_titles(fig_pc, x_title="Date", y_title="Component (SSP)")

    # --- Daily detail table ---
    tail = sorted(daily, key=lambda r: r["ds"], reverse=True)[:60]
    n_show = len(tail)
    sum_u = sum(float(r.get("y_units") or 0) for r in tail)
    sum_r = sum(float(r.get("y_revenue") or 0) for r in tail)

    def _stat_tile(label: str, value: str, sub: str = ""):
        return dmc.Paper(
            p="sm",
            radius="md",
            withBorder=True,
            className="cpi-rep-daily-stat-tile",
            children=[
                dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
                dmc.Text(value, fw=700, size="lg", mt=4),
                dmc.Text(sub, size="xs", c="dimmed") if sub else html.Span(),
            ],
        )

    if not tail:
        wrap = dmc.Text(
            "No ISSUE transactions in this window — forecasts will be empty.",
            c="dimmed",
            size="sm",
        )
    else:
        tbl = dmc.Table(
            striped=True,
            highlightOnHover=True,
            verticalSpacing="sm",
            horizontalSpacing="md",
            stickyHeader=True,
            stickyHeaderOffset=0,
            withTableBorder=True,
            withColumnBorders=True,
            className="cpi-rep-daily-mantine-table",
            children=[
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Trade date"),
                            html.Th("Units issued", style={"textAlign": "right"}),
                            html.Th("Revenue proxy", style={"textAlign": "right"}),
                        ]
                    )
                ),
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(
                                    _fmt_report_day(r["ds"]),
                                    className="cpi-rep-col-date",
                                ),
                                html.Td(
                                    _fmt_units_cell(float(r.get("y_units") or 0)),
                                    className="cpi-rep-col-num",
                                ),
                                html.Td(
                                    _fmt_ssp_cell(float(r.get("y_revenue") or 0)),
                                    className="cpi-rep-col-num cpi-rep-col-rev",
                                ),
                            ]
                        )
                        for r in tail
                    ]
                ),
            ],
        )
        wrap = dmc.Stack(
            gap="md",
            children=[
                dmc.SimpleGrid(
                    cols={"base": 1, "sm": 3},
                    spacing="sm",
                    className="cpi-rep-daily-toolbar",
                    children=[
                        _stat_tile("Days listed", str(n_show), "newest first"),
                        _stat_tile("Units (sum)", _fmt_units_cell(sum_u), "ISSUE = stock-out"),
                        _stat_tile("Revenue proxy (sum)", _fmt_ssp_cell(sum_r), "qty × unit price"),
                    ],
                ),
                html.Div(className="cpi-rep-daily-scroll", children=[tbl]),
            ],
        )

    return (
        health_children,
        analytics_children,
        status,
        fig_p,
        fig_pc,
        wrap,
    )


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
        title = f"{primary_app_name()} — snapshot"
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
        raw = bio.getvalue()
        return dict(
            content=base64.b64encode(raw).decode("ascii"),
            filename="inventory_snapshot.pdf",
            type="application/pdf",
            base64=True,
        )
    raise PreventUpdate
