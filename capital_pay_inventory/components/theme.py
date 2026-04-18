"""
Smart-Shop / CapitalPay inspired palette (navy / electric blue / white)
+ South Sudan flag accent references (#CE1126, #078930, #FCD116, #000000).
"""
from __future__ import annotations

from copy import deepcopy

# Mantine expects 10 shades (light → dark)
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


def merge_theme(color_scheme: str = "light") -> dict:
    base = {
        "primaryColor": "cpi",
        "fontFamily": "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
        "defaultRadius": "md",
        "components": {
            "Card": {"styles": {"root": {"border": "1px solid color-mix(in srgb, var(--mantine-color-gray-3), transparent 40%)"}}},
        },
        "colors": {
            "cpi": CPI_BLUE,
            "navy": CPI_NAVY,
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


CPI_THEME = merge_theme("light")
