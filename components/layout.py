"""App chrome: sidebar, header, flag strip, role-filtered navigation."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from components.branding import capital_pay_logo
from utils import i18n
from utils.app_text import primary_app_name
from utils.navigation import nav_entries_for_role, normalize_path


def _initials(full_name: str) -> str:
    parts = [p for p in (full_name or "User").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return (parts[0][:2] if parts else "U").upper()


def _nav_blocks(role: str | None, current_path: str | None, lang: str) -> list:
    entries = nav_entries_for_role(role, lang)
    if not entries:
        return [dmc.Text(i18n.t(lang, "sidebar_no_pages"), size="sm", c="dimmed")]

    cur = normalize_path(current_path)
    by_section: dict[str, list] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)

    blocks = []
    for section, items in by_section.items():
        blocks.append(
            dmc.Text(
                section,
                size="xs",
                fw=600,
                c="dimmed",
                mt="sm" if blocks else 0,
            )
        )
        for e in items:
            here = cur == normalize_path(e["path"])
            blocks.append(
                dmc.NavLink(
                    label=e["label"],
                    href=e["path"],
                    active=here,
                    leftSection=DashIconify(icon=e["icon"], width=18),
                    className="cpi-nav-link",
                )
            )
    return blocks


def sidebar(user: dict | None, alert_count: int = 0, *, current_path: str | None = None, lang: str = "en"):
    role = user.get("role", "VIEWER") if user else "VIEWER"
    name = user.get("full_name", "Guest") if user else "Guest"
    workspace = i18n.workspace_label(role, lang)

    clerk = role == "STOCK_CLERK"
    shell_cls = "cpi-sidebar-shell" + (" cpi-sidebar--clerk" if clerk else "")
    brand_title = primary_app_name()

    return html.Div(
        [
            dmc.Stack(
                [
                    html.Div(
                        className="cpi-sidebar-brand",
                        children=[
                            dmc.Group(
                                [
                                    capital_pay_logo(h=36),
                                    dmc.Stack(
                                        [
                                            dmc.Text(brand_title, fw=600, size="sm"),
                                            dmc.Text(i18n.t(lang, "sidebar_tag"), size="xs", c="dimmed"),
                                            dmc.Text(
                                                i18n.t(lang, "powered_by"),
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
                        ],
                    ),
                    dmc.Divider(my="sm"),
                    dmc.Paper(
                        withBorder=True,
                        shadow="xs",
                        radius="sm",
                        p="sm",
                        className="cpi-user-card",
                        children=dmc.Group(
                            [
                                dmc.Avatar(
                                    color="cpi",
                                    radius="sm",
                                    size="sm",
                                    children=_initials(name),
                                    style={"flexShrink": 0},
                                ),
                                dmc.Stack(
                                    [
                                        dmc.Text(name, size="sm", fw=600, lineClamp=2),
                                        dmc.Badge(
                                            workspace,
                                            size="xs",
                                            variant="light",
                                            color="navy",
                                            className="cpi-user-workspace-badge",
                                        ),
                                    ]
                                    + (
                                        []
                                        if clerk
                                        else [
                                            dmc.Text(
                                                f"{i18n.t(lang, 'role_prefix')}: {i18n.role_short_ui(role, lang)}",
                                                size="xs",
                                                c="dimmed",
                                            )
                                        ]
                                    ),
                                    gap="xs",
                                    style={"flex": "1 1 0%", "minWidth": 0, "maxWidth": "100%"},
                                ),
                            ],
                            gap="sm",
                            align="flex-start",
                            wrap="nowrap",
                            style={"width": "100%", "minWidth": 0},
                        ),
                    ),
                    dmc.ScrollArea(
                        className="cpi-sidebar-nav",
                        h="calc(100vh - 220px)",
                        mih=168,
                        offsetScrollbars=True,
                        type="hover",
                        children=dmc.Stack(_nav_blocks(role, current_path, lang), gap=4),
                    ),
                    dmc.Box(
                        pt="sm",
                        className="cpi-alert-strip",
                        children=dmc.Group(
                            [
                                DashIconify(icon="tabler:bell", width=18, className="cpi-icon-muted"),
                                dmc.Text(i18n.t(lang, "sidebar_alerts"), size="xs", c="dimmed"),
                                dmc.Badge(
                                    str(alert_count),
                                    color="red" if alert_count else "gray",
                                    size="xs",
                                    variant="outline",
                                ),
                            ],
                            justify="space-between",
                            wrap="nowrap",
                        ),
                    ),
                ],
                gap="sm",
                p="md",
            )
        ],
        className=shell_cls,
    )
