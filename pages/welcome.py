"""Public landing page (/welcome).

Marketing-style entry point shown to unauthenticated visitors. The sole goal
is to establish trust quickly and funnel the user to /login via one of the
prominent call-to-action buttons.

The page is chrome-less (no sidebar, no app header) and wide: layout styling
lives in ``assets/custom.css`` under the ``cpi-landing-*`` prefix so the
Python code stays declarative and easy to edit.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html, register_page
from dash_iconify import DashIconify

from components.branding import capital_pay_logo
from utils.app_text import primary_app_name

register_page(
    __name__,
    path="/welcome",
    name="Welcome",
    title="Welcome",
    order=-1,
)


def _nav_bar() -> html.Div:
    return html.Div(
        className="cpi-landing-nav",
        children=dmc.Group(
            justify="space-between",
            align="center",
            wrap="nowrap",
            children=[
                dmc.Group(
                    gap="sm",
                    align="center",
                    wrap="nowrap",
                    children=[
                        capital_pay_logo(h=36, radius="md"),
                        dmc.Text(
                            primary_app_name(),
                            className="cpi-landing-brand",
                        ),
                    ],
                ),
                dcc.Link(
                    dmc.Button(
                        "Sign in",
                        leftSection=DashIconify(icon="tabler:login-2", width=18),
                        size="sm",
                        radius="md",
                        color="cpi",
                        className="cpi-landing-cta-nav",
                    ),
                    href="/login",
                    refresh=True,
                    style={"textDecoration": "none"},
                ),
            ],
        ),
    )


def _hero() -> html.Div:
    return html.Div(
        className="cpi-landing-hero",
        children=[
            html.Div(className="cpi-landing-hero-orb cpi-landing-hero-orb--a"),
            html.Div(className="cpi-landing-hero-orb cpi-landing-hero-orb--b"),
            html.Div(className="cpi-landing-hero-grid"),
            dmc.Container(
                size="xl",
                className="cpi-landing-hero-inner",
                children=dmc.Grid(
                    gutter=48,
                    align="center",
                    children=[
                        dmc.GridCol(
                            span={"base": 12, "md": 7},
                            children=dmc.Stack(
                                gap="xl",
                                children=[
                                    dmc.Badge(
                                        "Inventory OS for growing businesses",
                                        size="lg",
                                        radius="xl",
                                        variant="light",
                                        color="cpi",
                                        className="cpi-landing-eyebrow",
                                        leftSection=DashIconify(
                                            icon="tabler:sparkles",
                                            width=14,
                                        ),
                                    ),
                                    dmc.Title(
                                        order=1,
                                        className="cpi-landing-title",
                                        children=[
                                            "Run your stockroom ",
                                            html.Span(
                                                "with confidence",
                                                className="cpi-landing-title-accent",
                                            ),
                                            ".",
                                        ],
                                    ),
                                    dmc.Text(
                                        (
                                            "Real-time inventory, multi-warehouse visibility, "
                                            "and intelligent alerts in one elegant workspace. "
                                            "Built for the shop floor, scaled for the boardroom."
                                        ),
                                        className="cpi-landing-lead",
                                    ),
                                    dmc.Group(
                                        gap="md",
                                        wrap="wrap",
                                        children=[
                                            dcc.Link(
                                                dmc.Button(
                                                    "Get started",
                                                    size="lg",
                                                    radius="md",
                                                    color="cpi",
                                                    rightSection=DashIconify(
                                                        icon="tabler:arrow-right",
                                                        width=20,
                                                    ),
                                                    className="cpi-landing-cta-primary",
                                                ),
                                                href="/login",
                                                refresh=True,
                                                style={"textDecoration": "none"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ),
                        dmc.GridCol(
                            span={"base": 12, "md": 5},
                            children=_hero_visual(),
                        ),
                    ],
                ),
            ),
        ],
    )


def _hero_visual() -> html.Div:
    """Stylised preview card — a static 'dashboard snapshot'."""
    return html.Div(
        className="cpi-landing-visual",
        children=[
            html.Div(
                className="cpi-landing-visual-card cpi-landing-visual-card--back",
                children=[
                    _chip("tabler:alert-triangle", "Low stock", "cpi-chip--warn"),
                    _chip("tabler:arrow-up-right", "+12.4%", "cpi-chip--ok"),
                    html.Div(className="cpi-landing-bar cpi-landing-bar--1"),
                    html.Div(className="cpi-landing-bar cpi-landing-bar--2"),
                    html.Div(className="cpi-landing-bar cpi-landing-bar--3"),
                    html.Div(className="cpi-landing-bar cpi-landing-bar--4"),
                    html.Div(className="cpi-landing-bar cpi-landing-bar--5"),
                ],
            ),
            html.Div(
                className="cpi-landing-visual-card cpi-landing-visual-card--front",
                children=dmc.Stack(
                    gap="sm",
                    children=[
                        dmc.Group(
                            gap="xs",
                            justify="space-between",
                            children=[
                                dmc.Text(
                                    "Today's snapshot",
                                    className="cpi-landing-visual-title",
                                ),
                                dmc.Badge(
                                    "Live",
                                    color="green",
                                    variant="light",
                                    size="sm",
                                    radius="sm",
                                    leftSection=DashIconify(
                                        icon="tabler:circle-filled",
                                        width=8,
                                    ),
                                ),
                            ],
                        ),
                        _visual_row("Stock value", "$128,430", "tabler:wallet"),
                        _visual_row("SKUs tracked", "1,842", "tabler:packages"),
                        _visual_row("Open alerts", "3", "tabler:bell-ringing"),
                        _visual_row("Warehouses", "6", "tabler:building-warehouse"),
                    ],
                ),
            ),
        ],
    )


def _visual_row(label: str, value: str, icon: str) -> html.Div:
    return html.Div(
        className="cpi-landing-visual-row",
        children=[
            html.Div(
                className="cpi-landing-visual-row-icon",
                children=DashIconify(icon=icon, width=18),
            ),
            dmc.Text(label, className="cpi-landing-visual-row-label"),
            dmc.Text(value, className="cpi-landing-visual-row-value"),
        ],
    )


def _chip(icon: str, label: str, extra_class: str) -> html.Div:
    return html.Div(
        className=f"cpi-landing-chip {extra_class}",
        children=[
            DashIconify(icon=icon, width=14),
            html.Span(label),
        ],
    )


STEPS: list[dict[str, str]] = [
    {
        "n": "01",
        "title": "Sign in securely",
        "body": "Use your issued credentials. Sessions are server-side with full audit trail.",
    },
    {
        "n": "02",
        "title": "Move stock in and out",
        "body": "Receive from suppliers, pick for sales orders, transfer between warehouses — all with two clicks.",
    },
    {
        "n": "03",
        "title": "Act on insights",
        "body": "Dashboards, reports and alerts bring the right number in front of the right person at the right time.",
    },
]


def _how_it_works() -> html.Div:
    return html.Div(
        id="how",
        className="cpi-landing-section cpi-landing-section--tinted",
        children=dmc.Container(
            size="xl",
            children=dmc.Stack(
                gap="xl",
                children=[
                    _section_heading(
                        eyebrow="How it works",
                        title="From first click to first insight in under a minute.",
                    ),
                    dmc.SimpleGrid(
                        cols={"base": 1, "md": 3},
                        spacing="lg",
                        children=[
                            _step(s["n"], s["title"], s["body"]) for s in STEPS
                        ],
                    ),
                ],
            ),
        ),
    )


def _step(num: str, title: str, body: str) -> html.Div:
    return html.Div(
        className="cpi-landing-step",
        children=[
            dmc.Text(num, className="cpi-landing-step-num"),
            dmc.Text(title, className="cpi-landing-step-title"),
            dmc.Text(body, className="cpi-landing-step-body"),
        ],
    )


def _cta() -> html.Div:
    return html.Div(
        className="cpi-landing-cta-strip",
        children=dmc.Container(
            size="lg",
            children=dmc.Stack(
                gap="lg",
                align="center",
                children=[
                    dmc.Title(
                        "Ready to take control of your inventory?",
                        order=2,
                        className="cpi-landing-cta-title",
                        ta="center",
                    ),
                    dmc.Text(
                        "Sign in to your workspace and see today's numbers in seconds.",
                        className="cpi-landing-cta-subtitle",
                        ta="center",
                    ),
                    dcc.Link(
                        dmc.Button(
                            "Sign in to continue",
                            size="lg",
                            radius="md",
                            color="cpi",
                            rightSection=DashIconify(
                                icon="tabler:arrow-right",
                                width=20,
                            ),
                            className="cpi-landing-cta-primary",
                        ),
                        href="/login",
                        refresh=True,
                        style={"textDecoration": "none"},
                    ),
                ],
            ),
        ),
    )


def _footer() -> html.Div:
    return html.Div(
        className="cpi-landing-footer",
        children=dmc.Container(
            size="xl",
            children=dmc.Group(
                justify="space-between",
                align="center",
                wrap="wrap",
                children=[
                    dmc.Text(
                        "© CapitalPay. All rights reserved.",
                        className="cpi-landing-footer-copy",
                    ),
                    dmc.Group(
                        gap="lg",
                        children=[
                            dcc.Link(
                                "Sign in",
                                href="/login",
                                refresh=True,
                                className="cpi-landing-footer-link",
                            ),
                            dmc.Anchor(
                                "How it works",
                                href="#how",
                                className="cpi-landing-footer-link",
                                underline="never",
                            ),
                        ],
                    ),
                ],
            ),
        ),
    )


def _section_heading(
    *,
    eyebrow: str,
    title: str,
    subtitle: str | None = None,
) -> dmc.Stack:
    children = [
        dmc.Text(eyebrow, className="cpi-landing-eyebrow-text"),
        dmc.Title(title, order=2, className="cpi-landing-section-title"),
    ]
    if subtitle:
        children.append(
            dmc.Text(subtitle, className="cpi-landing-section-sub")
        )
    return dmc.Stack(gap="xs", className="cpi-landing-section-head", children=children)


layout = html.Div(
    className="cpi-landing-root",
    children=[
        _nav_bar(),
        _hero(),
        _how_it_works(),
        _cta(),
        _footer(),
    ],
)
