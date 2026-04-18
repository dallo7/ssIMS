"""Design system for the Smart-Shop / CapitalPay inventory app.

Palette: navy shell + CapitalPay plum/ember accents.
Typography: Inter (UI) + Noto Naskh Arabic fallback for RTL/Arabic content.
Rhythm: 8-point spacing grid matching industry SaaS/ERP dashboards.
"""
from __future__ import annotations

from copy import deepcopy

# Mantine expects 10 shades (light -> dark)
CPI_BLUE = [
    "#E8F1FF",
    "#D0E4FF",
    "#A8CFFF",
    "#7AB8FF",
    "#4A9BFF",
    "#1A6EE8",
    "#155AC0",
    "#0F4696",
    "#0A326D",
    "#061F47",
]

CPI_NAVY = [
    "#E9ECEF",
    "#CED4DA",
    "#ADB5BD",
    "#868E96",
    "#495057",
    "#343A40",
    "#212529",
    "#152238",
    "#0F1A2E",
    "#0B1424",
]

SS_RED = "#CE1126"
SS_GREEN = "#078930"
SS_GOLD = "#FCD116"

# CapitalPay-inspired warmth (plum -> ember); pairs with navy shell.
BRAND_WARM = [
    "#fdf2f6",
    "#f8e0eb",
    "#efc4d4",
    "#d996b0",
    "#b85d7e",
    "#943d5c",
    "#7a2f4d",
    "#61263e",
    "#4a1c30",
    "#301322",
]

# --- Times New Roman serif stack (branding choice).
# RTL/Arabic falls back to Noto Naskh Arabic automatically.
UI_FONT_STACK = (
    "'Times New Roman', Times, 'Noto Serif', 'Nimbus Roman', "
    "'Noto Naskh Arabic', Georgia, serif"
)

MONO_FONT_STACK = (
    "'JetBrains Mono', ui-monospace, 'Cascadia Mono', 'SF Mono', "
    "'Segoe UI Mono', Consolas, 'Liberation Mono', monospace"
)

# Layered shadows — subtle but present, mimicking Linear / Vercel / Stripe.
_SHADOW_XS = "0 1px 2px rgba(16, 24, 40, 0.05)"
_SHADOW_SM = "0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.04)"
_SHADOW_MD = "0 4px 8px -2px rgba(16, 24, 40, 0.08), 0 2px 4px -2px rgba(16, 24, 40, 0.04)"
_SHADOW_LG = "0 12px 20px -4px rgba(16, 24, 40, 0.10), 0 4px 8px -2px rgba(16, 24, 40, 0.05)"
_SHADOW_XL = "0 20px 28px -8px rgba(16, 24, 40, 0.14), 0 8px 12px -4px rgba(16, 24, 40, 0.06)"


def merge_theme(color_scheme: str = "dark", *, direction: str = "ltr") -> dict:
    """Build a Mantine theme object tuned for a professional dashboard feel."""
    base = {
        "primaryColor": "cpi",
        "fontFamily": UI_FONT_STACK,
        "fontFamilyMonospace": MONO_FONT_STACK,
        "headings": {
            "fontFamily": UI_FONT_STACK,
            "fontWeight": "600",
            "sizes": {
                "h1": {"fontSize": "1.75rem", "lineHeight": "1.25", "fontWeight": "700"},
                "h2": {"fontSize": "1.375rem", "lineHeight": "1.3", "fontWeight": "650"},
                "h3": {"fontSize": "1.125rem", "lineHeight": "1.35", "fontWeight": "600"},
                "h4": {"fontSize": "1rem", "lineHeight": "1.4", "fontWeight": "600"},
                "h5": {"fontSize": "0.875rem", "lineHeight": "1.45", "fontWeight": "600"},
                "h6": {"fontSize": "0.8125rem", "lineHeight": "1.5", "fontWeight": "600"},
            },
        },
        "dir": direction,
        # 14 px base, Inter-tuned sizes. These also drive Mantine's Text/Input sizes.
        "fontSizes": {
            "xs": "0.75rem",     # 12 px
            "sm": "0.8125rem",   # 13 px
            "md": "0.875rem",    # 14 px  <- effective base
            "lg": "1rem",        # 16 px
            "xl": "1.125rem",    # 18 px
        },
        "lineHeights": {
            "xs": "1.5",
            "sm": "1.55",
            "md": "1.55",
            "lg": "1.5",
            "xl": "1.45",
        },
        # 8-point rhythm: 4 / 8 / 12 / 16 / 24 / 32 / 48
        "spacing": {
            "xs": "0.5rem",      # 8
            "sm": "0.75rem",     # 12
            "md": "1rem",        # 16
            "lg": "1.5rem",      # 24
            "xl": "2rem",        # 32
        },
        "radius": {
            "xs": "4px",
            "sm": "6px",
            "md": "8px",
            "lg": "12px",
            "xl": "16px",
        },
        "defaultRadius": "md",
        "shadows": {
            "xs": _SHADOW_XS,
            "sm": _SHADOW_SM,
            "md": _SHADOW_MD,
            "lg": _SHADOW_LG,
            "xl": _SHADOW_XL,
        },
        "cursorType": "pointer",
        "focusRing": "auto",
        "components": {
            "Card": {
                "defaultProps": {
                    "shadow": "sm",
                    "radius": "md",
                    "padding": "lg",
                    "withBorder": True,
                },
                "styles": {
                    "root": {
                        "border": "1px solid var(--mantine-color-gray-3)",
                        "transition": "box-shadow 160ms ease, border-color 160ms ease, transform 160ms ease",
                    }
                },
            },
            "Paper": {
                "defaultProps": {"radius": "md", "shadow": "xs", "withBorder": False},
            },
            "Button": {
                "defaultProps": {"radius": "md", "fw": 550, "size": "sm"},
                "styles": {
                    "root": {
                        "letterSpacing": "0.005em",
                        "transition": "background-color 140ms ease, color 140ms ease, border-color 140ms ease, box-shadow 140ms ease",
                    }
                },
            },
            "ActionIcon": {
                "defaultProps": {"radius": "md"},
            },
            "Modal": {
                "defaultProps": {"radius": "md", "padding": "lg", "shadow": "xl", "centered": True},
            },
            "Drawer": {
                "defaultProps": {"radius": "md", "padding": "lg", "shadow": "xl"},
            },
            "Menu": {
                "defaultProps": {"shadow": "md", "radius": "md"},
            },
            "Popover": {
                "defaultProps": {"shadow": "md", "radius": "md"},
            },
            "Tooltip": {
                "defaultProps": {"radius": "sm", "withArrow": True, "openDelay": 200},
            },
            "TextInput": {"defaultProps": {"radius": "md", "size": "md"}},
            "PasswordInput": {"defaultProps": {"radius": "md", "size": "md"}},
            "NumberInput": {"defaultProps": {"radius": "md", "size": "md"}},
            "Select": {"defaultProps": {"radius": "md", "size": "md"}},
            "MultiSelect": {"defaultProps": {"radius": "md", "size": "md"}},
            "Textarea": {"defaultProps": {"radius": "md", "size": "md", "minRows": 2}},
            "Checkbox": {"defaultProps": {"radius": "sm", "size": "sm"}},
            "Switch": {"defaultProps": {"size": "sm"}},
            "Alert": {"defaultProps": {"radius": "md", "variant": "light"}},
            "Badge": {
                "defaultProps": {"radius": "sm", "size": "sm"},
                "styles": {"root": {"textTransform": "none", "fontWeight": 550}},
            },
            "Tabs": {
                "defaultProps": {"color": "cpi", "radius": "md"},
            },
            "NavLink": {
                "styles": {
                    "root": {
                        "borderRadius": "var(--mantine-radius-md)",
                        "transition": "background-color 120ms ease, color 120ms ease",
                    }
                },
            },
            "Divider": {
                "styles": {"root": {"borderColor": "var(--mantine-color-gray-3)"}},
            },
            "Table": {
                "styles": {
                    "table": {
                        "fontSize": "var(--mantine-font-size-sm)",
                        "fontVariantNumeric": "tabular-nums",
                    },
                    "th": {
                        "fontSize": "var(--mantine-font-size-xs)",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.04em",
                        "fontWeight": 600,
                        "color": "var(--mantine-color-dimmed)",
                    },
                },
            },
            "Title": {
                "styles": {
                    "root": {
                        "letterSpacing": "-0.012em",
                    }
                },
            },
        },
        "colors": {
            "cpi": CPI_BLUE,
            "navy": CPI_NAVY,
            "brand": BRAND_WARM,
        },
        "other": {
            "cpiAccent": CPI_BLUE[5],
            "cpiNavy": CPI_NAVY[8],
            "ssRed": SS_RED,
            "ssGreen": SS_GREEN,
            "ssGold": SS_GOLD,
        },
    }
    t = deepcopy(base)
    t["colorScheme"] = color_scheme
    return t


CPI_THEME = merge_theme("dark", direction="ltr")
