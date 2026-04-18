"""App chrome: sidebar, header, flag strip, navigation."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from components.branding import capital_pay_logo

NAV = [
    ("/", "Dashboard", "tabler:layout-dashboard"),
    ("/inventory", "Inventory", "tabler:packages"),
    ("/movements", "Movements", "tabler:arrows-exchange"),
    ("/purchase-orders", "Purchase Orders", "tabler:shopping-cart"),
    ("/suppliers", "Suppliers", "tabler:truck-delivery"),
    ("/auditing", "Auditing", "tabler:clipboard-check"),
    ("/reports", "Reports", "tabler:report-analytics"),
    ("/monitoring", "Alerts", "tabler:bell-ringing"),
    ("/users", "Users", "tabler:users"),
    ("/config", "Configuration", "tabler:settings"),
]


def _nav_links():
    return [
        dmc.NavLink(
            label=label,
            href=path,
            leftSection=DashIconify(icon=icon, width=20),
        )
        for path, label, icon in NAV
    ]


def sidebar(user: dict | None, alert_count: int = 0):
    role = user.get("role", "—") if user else "—"
    name = user.get("full_name", "Guest") if user else "Guest"
    return html.Div(
        [
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            capital_pay_logo(h=40),
                            dmc.Stack(
                                [
                                    dmc.Text("Smart-Shop", fw=700, size="sm", c="cpi.8"),
                                    dmc.Text("Stock inventory", size="xs", c="dimmed"),
                                    dmc.Text(
                                        "Powered by CapitalPay",
                                        size="xs",
                                        c="dimmed",
                                        mt=4,
                                        style={"opacity": 0.92, "letterSpacing": "0.02em"},
                                    ),
                                ],
                                gap=0,
                            ),
                        ],
                        gap="sm",
                    ),
                    html.Div(
                        className="ss-flag-strip",
                        style={
                            "height": 6,
                            "borderRadius": 4,
                            "background": "linear-gradient(180deg, #000 0%, #000 33%, #CE1126 33%, #CE1126 66%, #078930 66%, #078930 100%)",
                            "position": "relative",
                        },
                    ),
                    dmc.Divider(),
                    dmc.Group(
                        [
                            html.Img(
                                src="/assets/flag-ss.svg",
                                alt="South Sudan",
                                width=36,
                                height=24,
                                style={"borderRadius": 4, "boxShadow": "0 1px 4px rgba(0,0,0,0.15)"},
                            ),
                            dmc.Stack(
                                [
                                    dmc.Text(name, size="sm", fw=600, truncate=True),
                                    dmc.Badge(role, size="xs", variant="light", color="cpi"),
                                ],
                                gap=2,
                            ),
                        ],
                        gap="sm",
                    ),
                    dmc.ScrollArea(
                        h="calc(100vh - 280px)",
                        children=dmc.Stack(_nav_links(), gap=4),
                    ),
                    dmc.Divider(),
                    dmc.Group(
                        [
                            DashIconify(icon="tabler:bell", width=20),
                            dmc.Text("Alerts", size="sm"),
                            dmc.Badge(str(alert_count), color="red", size="sm") if alert_count else dmc.Badge("0", color="gray", variant="outline", size="sm"),
                        ],
                        justify="space-between",
                    ),
                ],
                gap="md",
                p="md",
            )
        ],
        style={
            "minHeight": "100vh",
            "borderRight": "1px solid var(--mantine-color-gray-3)",
            "background": "linear-gradient(180deg, #f8fafc 0%, #ffffff 40%)",
        },
    )


def header_bar(color_scheme: str, user: dict | None):
    return dmc.Paper(
        shadow="xs",
        p="sm",
        radius=0,
        withBorder=False,
        style={"borderBottom": "1px solid var(--mantine-color-gray-3)"},
        children=dmc.Group(
            [
                dmc.Title("Smart-Shop Stock Inventory", order=4, flex=1),
                dmc.Group(
                    [
                        dmc.ActionIcon(
                            DashIconify(icon="tabler:sun" if color_scheme == "dark" else "tabler:moon", width=22),
                            id="btn-theme-toggle",
                            variant="light",
                            color="cpi",
                            size="lg",
                        ),
                        dmc.Button("Logout", id="btn-logout", variant="subtle", color="red", size="sm"),
                    ],
                    gap="xs",
                ),
            ],
            justify="space-between",
            align="center",
        ),
    )


def main_shell(page_container, user: dict | None, color_scheme: str, alert_count: int = 0):
    return dmc.Grid(
        gutter=0,
        children=[
            dmc.GridCol(
                span={"base": 12, "sm": 3, "md": 2},
                id="sidebar-col",
                style={"padding": 0},
                children=sidebar(user, alert_count),
            ),
            dmc.GridCol(
                span={"base": 12, "sm": 9, "md": 10},
                style={"padding": 0, "minHeight": "100vh", "background": "var(--mantine-color-body)"},
                children=dmc.Stack(
                    [
                        header_bar(color_scheme, user),
                        dmc.Container(page_container, fluid=True, p="md", style={"maxWidth": "100%"}),
                    ],
                    gap=0,
                ),
            ),
        ],
    )
