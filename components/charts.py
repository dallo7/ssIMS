"""Plotly design system — modern, branded defaults for every chart in the app.

Calling :func:`register_templates` on startup registers two Plotly templates
(``cpi_light`` and ``cpi_dark``) and sets ``cpi_dark`` as the global default
via ``plotly.io.templates.default``. Every chart created thereafter with
``plotly.express``, ``plotly.graph_objects``, or Dash ``dcc.Graph`` inherits:

* Brand colorway (navy blue, CapitalPay plum/ember, South-Sudan green/gold).
* Transparent paper & plot backgrounds so charts blend into surrounding cards.
* Clean gridlines (only y-axis, dashed, low-contrast) with no spines/zero-line.
* Times New Roman typography matching the rest of the UI.
* Unified hover mode, pill-shaped hoverlabel with brand-accented border.
* Generous padding, comfortable legend spacing, rounded bar corners.

To opt a specific figure into the light template (e.g. inside a PDF export
that is printed on white paper) use::

    import plotly.io as pio
    fig.update_layout(template="cpi_light")
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# Brand palette — re-used across the app. Matches components.theme.
CPI_COLORWAY = [
    "#1A6EE8",  # CPI blue (primary)
    "#7a2f4d",  # CapitalPay plum
    "#c45a2e",  # CapitalPay ember
    "#078930",  # SS green
    "#4A9BFF",  # light blue accent
    "#943d5c",  # dusty plum
    "#fcd116",  # SS gold
    "#6bb0ff",  # sky blue
    "#b85d7e",  # rose
    "#155AC0",  # deep blue
]

# Sequential / continuous palettes (for heatmaps, choropleths, density maps).
CPI_SEQUENTIAL = [
    [0.00, "#e8f1ff"],
    [0.25, "#7ab8ff"],
    [0.50, "#1a6ee8"],
    [0.75, "#155ac0"],
    [1.00, "#0a326d"],
]

CPI_DIVERGING = [
    [0.00, "#7a2f4d"],
    [0.25, "#b85d7e"],
    [0.50, "#f8e0eb"],
    [0.75, "#6bb0ff"],
    [1.00, "#1a6ee8"],
]

_FONT_FAMILY = (
    "'Times New Roman', Times, 'Noto Serif', 'Nimbus Roman', "
    "'Noto Naskh Arabic', Georgia, serif"
)


def _base_layout(
    *,
    text_color: str,
    muted_color: str,
    grid_color: str,
    hover_bg: str,
    hover_border: str,
) -> go.Layout:
    return go.Layout(
        font=dict(family=_FONT_FAMILY, size=13, color=text_color),
        colorway=CPI_COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title=dict(
            font=dict(family=_FONT_FAMILY, size=16, color=text_color),
            x=0.02,
            xanchor="left",
            y=0.96,
            pad=dict(t=4, b=8),
        ),
        margin=dict(t=56, r=24, b=48, l=56),
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            ticks="outside",
            tickcolor=muted_color,
            ticklen=4,
            tickfont=dict(color=muted_color, size=12),
            title=dict(font=dict(color=text_color, size=12)),
            automargin=True,
        ),
        yaxis=dict(
            gridcolor=grid_color,
            gridwidth=1,
            griddash="dot",
            showline=False,
            zeroline=False,
            ticks="",
            tickfont=dict(color=muted_color, size=12),
            title=dict(font=dict(color=text_color, size=12)),
            automargin=True,
        ),
        hoverlabel=dict(
            font=dict(family=_FONT_FAMILY, size=12, color="#f8fafc"),
            bgcolor=hover_bg,
            bordercolor=hover_border,
        ),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(family=_FONT_FAMILY, size=12, color=text_color),
            itemclick="toggleothers",
        ),
        separators=", ",
        dragmode=False,
    )


def _build_light_template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = _base_layout(
        text_color="#1e293b",
        muted_color="#64748b",
        grid_color="rgba(100, 116, 139, 0.18)",
        hover_bg="#0f172a",
        hover_border="rgba(26, 110, 232, 0.45)",
    )
    t.layout.colorscale = dict(
        sequential=CPI_SEQUENTIAL,
        sequentialminus=list(reversed(CPI_SEQUENTIAL)),
        diverging=CPI_DIVERGING,
    )
    # Modern trace defaults — rounded bars, clean scatter points.
    t.data.bar = [
        go.Bar(
            marker=dict(
                line=dict(width=0),
                cornerradius=6,
            ),
            textfont=dict(family=_FONT_FAMILY, size=11, color="#1e293b"),
        )
    ]
    t.data.scatter = [
        go.Scatter(
            line=dict(width=2.2, shape="spline", smoothing=0.6),
            marker=dict(size=6, line=dict(width=1.5, color="rgba(255,255,255,0.9)")),
        )
    ]
    t.data.pie = [
        go.Pie(
            hole=0.55,
            textinfo="label+percent",
            textfont=dict(family=_FONT_FAMILY, size=12),
            marker=dict(line=dict(color="#ffffff", width=2)),
        )
    ]
    t.data.heatmap = [go.Heatmap(colorscale=CPI_SEQUENTIAL, showscale=True)]
    t.data.choropleth = [go.Choropleth(colorscale=CPI_SEQUENTIAL, marker=dict(line=dict(color="#ffffff", width=0.5)))]
    t.data.choroplethmapbox = [go.Choroplethmapbox(colorscale=CPI_SEQUENTIAL)]
    return t


def _build_dark_template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = _base_layout(
        text_color="#e8eaef",
        muted_color="#a8b8d0",
        grid_color="rgba(130, 190, 255, 0.14)",
        hover_bg="#0b3a73",
        hover_border="rgba(130, 190, 255, 0.45)",
    )
    # Mapbox (for live maps in monitoring / delivery pages).
    t.layout.mapbox = dict(
        style="carto-darkmatter",
        bearing=0,
        pitch=0,
    )
    t.layout.geo = dict(
        bgcolor="rgba(0,0,0,0)",
        landcolor="#0b3a73",
        subunitcolor="rgba(130, 190, 255, 0.22)",
        countrycolor="rgba(130, 190, 255, 0.28)",
        showcountries=True,
        showland=True,
        framecolor="rgba(0,0,0,0)",
    )
    t.layout.colorscale = dict(
        sequential=CPI_SEQUENTIAL,
        sequentialminus=list(reversed(CPI_SEQUENTIAL)),
        diverging=CPI_DIVERGING,
    )
    t.data.bar = [
        go.Bar(
            marker=dict(
                line=dict(width=0),
                cornerradius=6,
            ),
            textfont=dict(family=_FONT_FAMILY, size=11, color="#e8eaef"),
        )
    ]
    t.data.scatter = [
        go.Scatter(
            line=dict(width=2.2, shape="spline", smoothing=0.6),
            marker=dict(size=6, line=dict(width=1.5, color="rgba(11, 58, 115, 0.9)")),
        )
    ]
    t.data.pie = [
        go.Pie(
            hole=0.55,
            textinfo="label+percent",
            textfont=dict(family=_FONT_FAMILY, size=12, color="#e8eaef"),
            marker=dict(line=dict(color="#0b3a73", width=2)),
        )
    ]
    t.data.heatmap = [go.Heatmap(colorscale=CPI_SEQUENTIAL, showscale=True)]
    t.data.choropleth = [
        go.Choropleth(
            colorscale=CPI_SEQUENTIAL,
            marker=dict(line=dict(color="rgba(11, 58, 115, 0.9)", width=0.5)),
        )
    ]
    t.data.choroplethmapbox = [go.Choroplethmapbox(colorscale=CPI_SEQUENTIAL)]
    return t


_REGISTERED = False


def register_templates(default: str = "cpi_dark") -> None:
    """Install the cpi_light/cpi_dark templates. Idempotent."""
    global _REGISTERED
    if _REGISTERED:
        pio.templates.default = default
        return
    pio.templates["cpi_light"] = _build_light_template()
    pio.templates["cpi_dark"] = _build_dark_template()
    pio.templates.default = default
    _REGISTERED = True


__all__ = [
    "CPI_COLORWAY",
    "CPI_SEQUENTIAL",
    "CPI_DIVERGING",
    "register_templates",
]
