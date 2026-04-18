"""CapitalPay logo next to powered-by and other brand mentions."""
from __future__ import annotations

import dash_mantine_components as dmc

LOGO_ASSET = "/assets/capitalpay-logo.png"


def capital_pay_logo(*, h: int = 20, w: int | None = None, **kwargs) -> dmc.Image:
    style = {"flexShrink": 0, **(kwargs.pop("style", None) or {})}
    radius = kwargs.pop("radius", "md")
    return dmc.Image(
        src=LOGO_ASSET,
        h=h,
        w=h if w is None else w,
        radius=radius,
        fit="contain",
        className="cpi-capitalpay-logo",
        style=style,
        **kwargs,
    )


def powered_by_capitalpay(lang: str, *, logo_h: int = 18, text_size: str = "xs") -> dmc.Group:
    from utils import i18n

    return dmc.Group(
        [
            capital_pay_logo(h=logo_h),
            dmc.Text(
                i18n.t(lang, "powered_by"),
                size=text_size,
                c="dimmed",
                style={"lineHeight": 1.3, "letterSpacing": "0.02em"},
            ),
        ],
        gap="xs",
        align="center",
        wrap="nowrap",
    )