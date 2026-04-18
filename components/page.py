"""Reusable page chrome: hero title panel + consistent vertical rhythm.

The hero is the first block on every page. Callers typically pass just
``title`` (and optional ``help``), but the component also supports an
``eyebrow`` (uppercase section category), ``subtitle`` (short context line)
and an ``actions`` slot on the right of the title row — all optional, so
existing pages remain unchanged.
"""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash_iconify import DashIconify


def page_header(
    title: str,
    *,
    help: str | None = None,
    eyebrow: str | None = None,
    subtitle: str | None = None,
    actions: Any | None = None,
) -> dmc.Paper:
    """Primary page title in hero panel.

    Args:
        title: Main H3 heading, e.g. ``"Inventory"``.
        help: Optional tooltip text shown on a ``?`` icon at the right of the
            title row. Kept for backwards compatibility with existing callers.
        eyebrow: Optional uppercase category label above the title
            (e.g. ``"Operations"``).
        subtitle: Optional single-line description shown below the title in
            dimmed text (max 72ch for readability).
        actions: Optional Dash component(s) rendered on the right side of the
            title row (buttons, menus, search boxes, …).
    """
    title_right: list = []
    if actions is not None:
        title_right.append(
            dmc.Box(actions, style={"flexShrink": 0, "display": "flex", "gap": "0.5rem"})
        )
    if help:
        title_right.append(
            dmc.Tooltip(
                multiline=True,
                maw=320,
                label=help,
                withArrow=True,
                position="bottom-end",
                transitionProps={"transition": "fade", "duration": 200},
                children=dmc.ActionIcon(
                    DashIconify(icon="tabler:help-circle", width=20),
                    variant="subtle",
                    color="gray",
                    size="md",
                    radius="xl",
                ),
            )
        )

    title_row = dmc.Group(
        [
            dmc.Title(title, order=2, style={"flex": 1, "minWidth": 0}),
            *(title_right if title_right else []),
        ],
        align="flex-start",
        gap="sm",
        wrap="nowrap",
    )

    stack_children: list = []
    if eyebrow:
        stack_children.append(
            dmc.Text(eyebrow, className="cpi-page-eyebrow", span=True)
        )
    stack_children.append(title_row)
    if subtitle:
        stack_children.append(
            dmc.Text(subtitle, className="cpi-page-subtitle", size="sm")
        )

    return dmc.Paper(
        className="cpi-page-hero",
        radius="md",
        withBorder=True,
        mb="lg",
        children=dmc.Stack(stack_children, gap=4),
    )
