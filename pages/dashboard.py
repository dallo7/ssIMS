from datetime import datetime

import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate
from dash_iconify import DashIconify
from flask import session

from database.dal import (
    abc_distribution,
    dashboard_kpis,
    list_alerts_with_ack_state,
    movement_timeseries,
    stock_by_category,
    top_movers,
    unique_items_status_review,
)
from database.engine import db_session
from components.page import page_header
from utils import i18n

_dch_t, _dch_h = i18n.page_heading("en", "dash_clerk")
_dah_t, _dah_h = i18n.page_heading("en", "dash_analytics")

register_page(__name__, path="/", name="Dashboard", title="Dashboard", order=0)


def _plotly_template(theme_data: dict | None) -> str:
    return "plotly_dark" if (theme_data or {}).get("scheme", "dark") == "dark" else "plotly_white"


def _can_view():
    return bool(session.get("user_id"))


def _kpi_card(icon: str, inner_id: str):
    return dmc.Card(
        withBorder=True,
        padding="lg",
        radius="md",
        className="cpi-kpi-card cpi-kpi-card--accent",
        children=dmc.Group(
            [
                DashIconify(icon=icon, width=32, className="cpi-kpi-card-icon"),
                dmc.Stack(gap=4, id=inner_id, className="cpi-kpi-card-inner", style={"minWidth": 0}),
            ],
            align="flex-start",
            gap="md",
            wrap="nowrap",
        ),
    )


_FLOW_STATUS_META: dict[str, dict[str, str]] = {
    "OUT":  {"label": "Out of stock",  "color": "red",    "icon": "tabler:ban"},
    "LOW":  {"label": "Low stock",     "color": "orange", "icon": "tabler:alert-triangle"},
    "OVER": {"label": "Overstocked",   "color": "violet", "icon": "tabler:stack-2"},
    "OK":   {"label": "In good shape", "color": "teal",   "icon": "tabler:check"},
}


def _flow_relative_time(dt: datetime | None) -> str:
    """Compact, human-friendly age for the last-movement timestamp."""
    if dt is None:
        return "No movement"
    delta = datetime.utcnow() - dt
    secs = delta.total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    if delta.days < 7:
        return f"{delta.days}d ago"
    return dt.strftime("%Y-%m-%d")


def _flow_card(row: dict) -> dmc.Card:
    """One card per unique SKU: status badge, on-hand vs reorder, in / out / net."""
    status = row["status"]
    meta = _FLOW_STATUS_META[status]
    on = float(row["on_hand"] or 0)
    rp = float(row["reorder_point"] or 0)
    rq = float(row["reorder_quantity"] or 0)
    received = float(row["received"] or 0)
    issued = float(row["issued"] or 0)
    net = float(row["net"] or 0)

    # Progress: on-hand expressed as % of (reorder_point + 1.5 * reorder_qty),
    # capped at 100. Items at "OK" / "OVER" naturally fill the bar; OUT / LOW
    # leave it visibly short, reinforcing the colour-coded accent stripe.
    cap = max(1.0, rp + (rq * 1.5)) if (rp or rq) else max(1.0, on, 1.0)
    pct = max(0.0, min(100.0, (on / cap) * 100.0))

    last_dt = row.get("last_movement_at")
    last_iso = last_dt.strftime("%Y-%m-%d %H:%M") if last_dt else "No movement in window"

    name_label = row.get("name") or "—"
    sub_label = row.get("sku") or row.get("item_id") or ""

    net_color = "#15803d" if net >= 0 else "#b91c1c"

    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        className=f"cpi-item-flow-card cpi-item-flow-card--{status.lower()}",
        children=[
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Text(
                                name_label,
                                fw=600,
                                size="sm",
                                lineClamp=1,
                                className="cpi-item-flow-card-name",
                            ),
                            dmc.Text(sub_label, size="xs", c="dimmed"),
                        ],
                        gap=2,
                        style={"flex": 1, "minWidth": 0},
                    ),
                    dmc.Badge(
                        meta["label"],
                        color=meta["color"],
                        variant="light",
                        leftSection=DashIconify(icon=meta["icon"], width=12),
                        size="sm",
                        radius="sm",
                    ),
                ],
                justify="space-between",
                align="flex-start",
                wrap="nowrap",
            ),
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Text("On hand", size="xs", c="dimmed"),
                            dmc.Text(
                                f"{on:,.0f}",
                                fw=700,
                                size="md",
                                className="cpi-item-flow-card-onhand",
                            ),
                        ],
                        justify="space-between",
                        wrap="nowrap",
                    ),
                    dmc.Progress(
                        value=pct,
                        color=meta["color"],
                        size="sm",
                        radius="xl",
                        className="cpi-item-flow-progress",
                    ),
                    dmc.Group(
                        [
                            dmc.Text(f"Reorder at {rp:,.0f}", size="xs", c="dimmed"),
                            dmc.Tooltip(
                                label=last_iso,
                                position="top",
                                withArrow=True,
                                children=dmc.Text(
                                    _flow_relative_time(last_dt),
                                    size="xs",
                                    c="dimmed",
                                ),
                            ),
                        ],
                        justify="space-between",
                        wrap="nowrap",
                    ),
                ],
                gap=6,
                mt="sm",
            ),
            dmc.Divider(my="sm"),
            dmc.SimpleGrid(
                cols=3,
                spacing="xs",
                className="cpi-item-flow-flowgrid",
                children=[
                    dmc.Stack(
                        [
                            dmc.Group(
                                [
                                    DashIconify(
                                        icon="tabler:arrow-down-right",
                                        width=14,
                                        color="#15803d",
                                    ),
                                    dmc.Text("In", size="xs", c="dimmed"),
                                ],
                                gap=4,
                                wrap="nowrap",
                            ),
                            dmc.Text(
                                f"{received:,.0f}",
                                fw=600,
                                size="sm",
                                className="cpi-item-flow-in",
                            ),
                        ],
                        gap=2,
                    ),
                    dmc.Stack(
                        [
                            dmc.Group(
                                [
                                    DashIconify(
                                        icon="tabler:arrow-up-right",
                                        width=14,
                                        color="#b91c1c",
                                    ),
                                    dmc.Text("Out", size="xs", c="dimmed"),
                                ],
                                gap=4,
                                wrap="nowrap",
                            ),
                            dmc.Text(
                                f"{issued:,.0f}",
                                fw=600,
                                size="sm",
                                className="cpi-item-flow-out",
                            ),
                        ],
                        gap=2,
                    ),
                    dmc.Stack(
                        [
                            dmc.Group(
                                [
                                    DashIconify(
                                        icon="tabler:arrows-exchange",
                                        width=14,
                                        color="#1e3a8a",
                                    ),
                                    dmc.Text("Net", size="xs", c="dimmed"),
                                ],
                                gap=4,
                                wrap="nowrap",
                            ),
                            dmc.Text(
                                f"{net:+,.0f}",
                                fw=600,
                                size="sm",
                                style={"color": net_color},
                                className="cpi-item-flow-net",
                            ),
                        ],
                        gap=2,
                    ),
                ],
            ),
        ],
    )


def _clerk_action_card(
    icon: str,
    title: str,
    body: str,
    cta: str,
    href: str,
    *,
    primary: bool,
) -> dmc.Card:
    """Same shell as dashboard KPI tiles: accent card + icon + stack; CTA matches KPI emphasis."""
    btn_cls = "cpi-clerk-dash-btn " + (
        "cpi-clerk-dash-btn--primary" if primary else "cpi-clerk-dash-btn--secondary"
    )
    return dmc.Card(
        withBorder=True,
        padding="lg",
        radius="md",
        className="cpi-kpi-card cpi-kpi-card--accent cpi-dash-action-card",
        children=dmc.Group(
            [
                DashIconify(icon=icon, width=32, className="cpi-kpi-card-icon"),
                dmc.Stack(
                    [
                        dmc.Text(title, fw=700, size="md", style={"lineHeight": 1.35}),
                        dmc.Text(body, size="sm", c="dimmed"),
                        dcc.Link(cta, href=href, className=btn_cls),
                    ],
                    gap="xs",
                    className="cpi-dash-action-card-inner",
                    style={"minWidth": 0, "flex": 1},
                ),
            ],
            align="flex-start",
            gap="md",
            wrap="nowrap",
        ),
    )


layout = dmc.Stack(
    className="cpi-page-wrap",
    style={"width": "100%", "maxWidth": "100%", "boxSizing": "border-box"},
    gap="lg",
    children=[
        html.Div(
            id="dash-clerk-home",
            style={"display": "none"},
            className="cpi-clerk-dashboard",
            children=[
                html.Div(id="dash-clerk-welcome-top"),
                html.Div(id="dash-clerk-header", children=page_header(_dch_t, help=_dch_h)),
                html.Div(id="dash-clerk-quick"),
                html.Div(id="dash-clerk-more"),
                html.Div(id="dash-clerk-alerts-stack", style={"marginTop": "var(--mantine-spacing-md)"}),
            ],
        ),
        html.Div(
            id="dash-analytics-block",
            children=[
                html.Div(id="dash-analytics-header", children=page_header(_dah_t, help=_dah_h)),
                html.Div(id="dash-welcome"),
                dmc.Paper(
                    className="cpi-toolbar-paper",
                    p="md",
                    radius="md",
                    withBorder=True,
                    children=dmc.Group(
                        [
                            html.Div(
                                dcc.DatePickerRange(
                                    id="dash-dates",
                                    display_format="YYYY-MM-DD",
                                    start_date_placeholder_text="Start",
                                    end_date_placeholder_text="End",
                                ),
                                style={"display": "inline-block"},
                            ),
                            dmc.SegmentedControl(
                                id="dash-move-window",
                                data=[
                                    {"label": "30d", "value": "30"},
                                    {"label": "60d", "value": "60"},
                                    {"label": "90d", "value": "90"},
                                ],
                                value="30",
                            ),
                        ],
                        grow=True,
                        align="center",
                        justify="flex-start",
                        wrap="wrap",
                        gap="md",
                    ),
                ),
                dmc.SimpleGrid(
                    cols={"base": 1, "sm": 2, "lg": 5},
                    spacing="lg",
                    children=[
                        _kpi_card("tabler:packages", "kpi-skus-inner"),
                        _kpi_card("tabler:coins", "kpi-val-inner"),
                        _kpi_card("tabler:alert-triangle", "kpi-low-inner"),
                        _kpi_card("tabler:ban", "kpi-oos-inner"),
                        _kpi_card("tabler:truck", "kpi-po-inner"),
                    ],
                ),
                dmc.SimpleGrid(
                    cols={"base": 1, "lg": 2},
                    spacing="lg",
                    children=[
                        dcc.Graph(id="chart-cat", config={"displayModeBar": True, "responsive": True}),
                        dcc.Graph(id="chart-abc", config={"displayModeBar": True, "responsive": True}),
                    ],
                ),
                dcc.Graph(id="chart-move", config={"displayModeBar": True, "responsive": True}),
                dmc.SimpleGrid(
                    cols={"base": 1, "lg": 2},
                    spacing="lg",
                    children=[
                        dcc.Graph(id="chart-fast", config={"displayModeBar": True, "responsive": True}),
                        dcc.Graph(id="chart-slow", config={"displayModeBar": True, "responsive": True}),
                    ],
                ),
                dmc.Card(
                    withBorder=True,
                    padding="lg",
                    radius="md",
                    children=[
                        dmc.Title("Operational alerts", order=4, mb="md", fw=600),
                        html.Div(id="dash-alerts-panel"),
                    ],
                ),
            ],
        ),
        # ----------------------------------------------------------------------
        # Unique items — stock flow review.
        # Lives OUTSIDE the role-gated analytics / clerk blocks so every signed-in
        # user (including stock clerks) sees a card per active SKU.
        # ----------------------------------------------------------------------
        dmc.Card(
            withBorder=True,
            padding="lg",
            radius="md",
            className="cpi-item-flow-shell",
            children=[
                dmc.Group(
                    [
                        dmc.Stack(
                            [
                                dmc.Title(
                                    "Unique items — stock flow review",
                                    order=4,
                                    fw=600,
                                ),
                                dmc.Text(
                                    "One card per active product. Status reflects current "
                                    "on-hand vs the reorder point; In / Out / Net summarise "
                                    "stock movement over the selected window.",
                                    size="sm",
                                    c="dimmed",
                                ),
                            ],
                            gap=2,
                            style={"flex": 1, "minWidth": 0},
                        ),
                        dmc.SegmentedControl(
                            id="dash-flow-window",
                            data=[
                                {"label": "7d", "value": "7"},
                                {"label": "30d", "value": "30"},
                                {"label": "90d", "value": "90"},
                            ],
                            value="30",
                            size="xs",
                        ),
                    ],
                    justify="space-between",
                    align="flex-start",
                    wrap="wrap",
                    gap="md",
                ),
                dmc.Group(
                    [
                        dmc.TextInput(
                            id="dash-flow-search",
                            placeholder="Filter by name or SKU…",
                            leftSection=DashIconify(icon="tabler:search", width=16),
                            size="sm",
                            radius="md",
                            className="cpi-item-flow-search",
                            style={"flex": 1, "minWidth": "200px", "maxWidth": "420px"},
                        ),
                        dmc.Text(
                            id="dash-flow-summary",
                            size="xs",
                            c="dimmed",
                            children="",
                        ),
                    ],
                    justify="space-between",
                    align="center",
                    wrap="wrap",
                    gap="sm",
                    mt="md",
                ),
                html.Div(
                    id="dash-item-flow-grid",
                    className="cpi-item-flow-grid-wrap",
                    style={"marginTop": "var(--mantine-spacing-md)"},
                ),
            ],
        ),
    ],
)


@callback(
    Output("dash-clerk-header", "children"),
    Output("dash-analytics-header", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def dash_page_headers(pathname, loc):
    from utils.navigation import normalize_path

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    c_t, c_h = i18n.page_heading(lang, "dash_clerk")
    a_t, a_h = i18n.page_heading(lang, "dash_analytics")
    return page_header(c_t, help=c_h), page_header(a_t, help=a_h)


@callback(
    Output("dash-analytics-block", "style"),
    Output("dash-clerk-home", "style"),
    Input("_pages_location", "pathname"),
)
def dash_workspace_switch(pathname):
    from utils.navigation import normalize_path

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    if session.get("role") == "STOCK_CLERK":
        return {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}


def _clerk_severity_title(lang: str, severity: str | None) -> str:
    s = (severity or "").upper()
    if s == "CRITICAL":
        return i18n.clerk_home_txt(lang, "sev_critical")
    if s in ("WARNING", "WARN"):
        return i18n.clerk_home_txt(lang, "sev_warning")
    return i18n.clerk_home_txt(lang, "sev_notice")


@callback(
    Output("dash-clerk-welcome-top", "children"),
    Output("dash-clerk-quick", "children"),
    Output("dash-clerk-more", "children"),
    Input("_pages_location", "pathname"),
    Input("locale-store", "data"),
)
def dash_clerk_home_shell(pathname, loc):
    from utils.navigation import normalize_path

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    if session.get("role") != "STOCK_CLERK" or not session.get("user_id"):
        raise PreventUpdate
    lang = i18n.normalize_lang(loc)
    raw_name = (session.get("full_name") or session.get("username") or "").strip()
    first = raw_name.split()[0] if raw_name else i18n.clerk_home_txt(lang, "name_fallback")
    welcome_title = i18n.clerk_home_txt(lang, "welcome_title").format(name=first)
    welcome = dmc.Paper(
        className="cpi-store-welcome",
        p="md",
        radius="md",
        withBorder=True,
        children=dmc.Stack(
            [
                dmc.Text(welcome_title, fw=700, size="lg"),
                dmc.Text(i18n.clerk_home_txt(lang, "welcome_sub"), size="sm", c="dimmed"),
            ],
            gap="xs",
        ),
    )
    quick = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2},
        spacing="lg",
        children=[
            _clerk_action_card(
                "tabler:packages",
                i18n.clerk_home_txt(lang, "card_stock_title"),
                i18n.clerk_home_txt(lang, "card_stock_body"),
                i18n.clerk_home_txt(lang, "card_stock_cta"),
                "/inventory",
                primary=True,
            ),
            _clerk_action_card(
                "tabler:arrows-exchange",
                i18n.clerk_home_txt(lang, "card_move_title"),
                i18n.clerk_home_txt(lang, "card_move_body"),
                i18n.clerk_home_txt(lang, "card_move_cta"),
                "/movements",
                primary=False,
            ),
        ],
    )
    more_paths = [
        "/customers",
        "/sales-orders",
        "/purchase-orders",
        "/suppliers",
        "/locations",
        "/kits-bom",
        "/auditing",
        "/reports",
        "/monitoring",
    ]
    more = dmc.Stack(
        gap="xs",
        mt="sm",
        children=[
            dmc.Text(i18n.clerk_home_txt(lang, "section_more"), size="sm", fw=600),
            dmc.Group(
                [
                    dmc.Anchor(i18n.clerk_link_label(p, lang), href=p, size="sm")
                    for p in more_paths
                ],
                gap="md",
                wrap="wrap",
            ),
        ],
    )
    return welcome, quick, more


@callback(
    Output("dash-clerk-alerts-stack", "children"),
    Input("_pages_location", "pathname"),
    Input("alert-interval", "n_intervals"),
    Input("locale-store", "data"),
)
def dash_clerk_alerts_strip(pathname, _n, loc):
    from utils.navigation import normalize_path

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    if session.get("role") != "STOCK_CLERK" or not session.get("user_id"):
        return ""
    lang = i18n.normalize_lang(loc)
    with db_session() as s:
        alerts = [a for a in list_alerts_with_ack_state(s, 24) if not a["acknowledged"]]
    body = (
        dmc.Text(i18n.clerk_home_txt(lang, "no_warnings"), size="sm", c="dimmed")
        if not alerts
        else dmc.Stack(
            [
                dmc.Alert(
                    a["message"],
                    color="red" if a["severity"] == "CRITICAL" else "yellow",
                    title=_clerk_severity_title(lang, a.get("severity")),
                )
                for a in alerts[:10]
            ],
            gap="xs",
        )
    )
    return dmc.Stack(
        [
            dmc.Text(i18n.clerk_home_txt(lang, "warnings_title"), size="sm", fw=600),
            body,
        ],
        gap="sm",
    )


@callback(Output("dash-welcome", "children"), Input("_pages_location", "pathname"))
def dash_welcome_banner(pathname):
    from utils.navigation import allowed_paths_for_role, normalize_path, role_workspace_label

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    role = session.get("role", "VIEWER")
    if role == "STOCK_CLERK":
        return ""
    n = len(allowed_paths_for_role(role))
    return dmc.Alert(
        f"{role_workspace_label(role)} — the sidebar lists {n} area(s) you can open. "
        "Other modules are hidden; if you need access, ask an administrator.",
        title="Personalized view",
        color="cpi",
        variant="light",
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
    Input("dash-dates", "start_date"),
    Input("dash-dates", "end_date"),
    Input("dash-move-window", "value"),
    Input("_pages_location", "pathname"),
    Input("theme-store", "data"),
)
def refresh_dashboard(_start_date, _end_date, window, _pathname, theme_data):
    from utils.navigation import normalize_path

    if normalize_path(_pathname) != "/":
        raise PreventUpdate
    if not _can_view():
        raise PreventUpdate
    if session.get("role") == "STOCK_CLERK":
        return (no_update,) * 11
    window_days = int(window or 30)
    pt = _plotly_template(theme_data)
    with db_session() as s:
        k = dashboard_kpis(s)
        cats = stock_by_category(s)
        abc = abc_distribution(s)
        ts = movement_timeseries(s, window_days)
        fast, slow = top_movers(s, window_days, 10)
        alerts = [a for a in list_alerts_with_ack_state(s, 50) if not a["acknowledged"]]

    def kpi_stack(title, val, sub=None):
        label = dmc.Text(
            title,
            size="xs",
            c="dimmed",
            tt="uppercase",
            fw=600,
            style={"letterSpacing": "0.04em"},
        )
        tit = dmc.Title(str(val), order=3, className="cpi-kpi-value")
        if sub:
            return [label, tit, dmc.Text(sub, size="xs", c="dimmed")]
        return [label, tit]

    fig_cat = px.bar(cats or [{"category": "—", "qty": 0}], x="category", y="qty", title="Stock level by category")
    fig_cat.update_layout(template=pt, margin=dict(l=40, r=20, t=50, b=40))
    fig_abc = px.pie(abc or [{"class": "B", "count": 1}], names="class", values="count", title="ABC class distribution (by SKU count)", hole=0.45)
    fig_abc.update_layout(template=pt, margin=dict(l=20, r=20, t=50, b=20))
    df_ts = ts or [{"date": "", "net": 0}]
    fig_m = go.Figure()
    fig_m.add_trace(go.Scatter(x=[r["date"] for r in df_ts], y=[r["net"] for r in df_ts], mode="lines+markers", name="Net movement"))
    fig_m.update_layout(title=f"Stock movement (net receive − issue) — last {window_days} days", template=pt, margin=dict(l=40, r=20, t=50, b=40))
    fig_f = px.bar(fast or [{"name": "—", "qty": 0}], x="name", y="qty", title="Top fast-moving (issue volume)")
    fig_f.update_layout(template=pt, margin=dict(l=40, r=20, t=50, b=120))
    fig_s = px.bar(slow or [{"name": "—", "qty": 0}], x="name", y="qty", title="Slow-moving (lowest issue volume)")
    fig_s.update_layout(template=pt, margin=dict(l=40, r=20, t=50, b=120))

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


@callback(
    Output("dash-item-flow-grid", "children"),
    Output("dash-flow-summary", "children"),
    Input("dash-flow-window", "value"),
    Input("dash-flow-search", "value"),
    Input("_pages_location", "pathname"),
)
def refresh_item_flow(window, search, pathname):
    """Render one card per unique active product, for every signed-in user."""
    from utils.navigation import normalize_path

    if normalize_path(pathname) != "/":
        raise PreventUpdate
    if not session.get("user_id"):
        raise PreventUpdate
    try:
        days = max(1, min(int(window or 30), 365))
    except (TypeError, ValueError):
        days = 30

    with db_session() as s:
        # limit=None → return every active SKU. The search filter below trims
        # the visible grid client-side via Python without hitting the DB again.
        rows = unique_items_status_review(s, days=days, limit=None)

    total = len(rows)
    needle = (search or "").strip().lower()
    if needle:
        def _matches(r: dict) -> bool:
            return (
                needle in (r.get("name") or "").lower()
                or needle in (r.get("sku") or "").lower()
                or needle in (r.get("item_id") or "").lower()
            )
        rows = [r for r in rows if _matches(r)]

    shown = len(rows)

    if total == 0:
        return (
            dmc.Text(
                "No active products to review yet. Add an item under Inventory.",
                c="dimmed",
                ta="center",
                py="md",
            ),
            "",
        )
    if shown == 0:
        summary = f"No matches — {total:,} product{'s' if total != 1 else ''} in catalogue."
        return (
            dmc.Text(
                f"No products match \u201c{search}\u201d.",
                c="dimmed",
                ta="center",
                py="md",
            ),
            summary,
        )

    if needle:
        summary = f"Showing {shown:,} of {total:,} products · last {days}d"
    else:
        summary = f"Showing all {total:,} products · last {days}d"

    grid = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "md": 3, "xl": 4},
        spacing="md",
        children=[_flow_card(r) for r in rows],
    )
    return grid, summary
