"""Regenerate favicon.ico + capitalpay-logo.png from assets/cpi-mark.svg geometry.

The SVG is intentionally a handful of primitives (rounded rect + polygon + circle)
so we can render it with Pillow directly — no cairosvg / system deps required.

Run:
    python scripts/generate_branding.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# Palette — kept in lockstep with assets/cpi-mark.svg.
BG = (0x0B, 0x1F, 0x3B, 0xFF)      # deep navy
MARK = (0x1A, 0x6E, 0xE8, 0xFF)    # CapitalPay blue
DOT = (0xFC, 0xD1, 0x16, 0xFF)     # South Sudan yellow
TRANSPARENT = (0, 0, 0, 0)

# SVG coordinate system: 64x64 viewBox. Everything below is expressed in that
# space and scaled per-output size via `_scale`.
SVG_SIZE = 64
CORNER_RADIUS = 12
# The "M" mark path, flattened to vertices (all absolute) from:
#   M16 44V20h8l8 14 8-14h8v24h-7V30l-9 16-9-16v14z
M_POLY = [
    (16, 44), (16, 20), (24, 20), (32, 34), (40, 20), (48, 20),
    (48, 44), (41, 44), (41, 30), (32, 46), (23, 30), (23, 44),
]
DOT_CENTER = (48, 16)
DOT_RADIUS = 4

# Supersampling factor — render large, then LANCZOS-downscale for clean edges
# even at tiny favicon sizes. 8x is ~plenty for 16px outputs.
SSAA = 8


def _render_mark(out_px: int) -> Image.Image:
    """Rasterize the SVG at ``out_px`` × ``out_px`` using supersampling."""
    super_px = out_px * SSAA
    scale = super_px / SVG_SIZE
    img = Image.new("RGBA", (super_px, super_px), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    # Rounded rect background.
    draw.rounded_rectangle(
        (0, 0, super_px - 1, super_px - 1),
        radius=CORNER_RADIUS * scale,
        fill=BG,
    )

    # Scaled "M" polygon.
    scaled_poly = [(x * scale, y * scale) for (x, y) in M_POLY]
    draw.polygon(scaled_poly, fill=MARK)

    # Yellow accent circle.
    cx, cy = DOT_CENTER
    r = DOT_RADIUS
    draw.ellipse(
        (
            (cx - r) * scale, (cy - r) * scale,
            (cx + r) * scale, (cy + r) * scale,
        ),
        fill=DOT,
    )

    return img.resize((out_px, out_px), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    # In-app logo — 256 gives crisp rendering up through hero-size usages.
    logo_path = ASSETS / "capitalpay-logo.png"
    _render_mark(256).save(logo_path, format="PNG", optimize=True)
    print(f"wrote {logo_path.relative_to(ROOT)}")

    # Multi-resolution favicon. 16/32/48 cover every browser + Windows shell;
    # 64 future-proofs hi-dpi Chrome tab strips.
    ico_path = ASSETS / "favicon.ico"
    sizes = [16, 32, 48, 64]
    frames = [_render_mark(s) for s in sizes]
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
