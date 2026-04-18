"""Regenerate the in-app logo and the browser favicon from brand source PNGs.

Two independent sources, two independent outputs:

* ``assets/capitalpay-logo-source.png``  →  ``assets/capitalpay-logo.png``
    The CapitalPay "cp" gradient mark used inside the app (login card,
    sidebar header, etc). Glyph-centred square crop driven by a brightness
    threshold on the white "cp" letterforms.

* ``assets/favicon-source.png``  →  ``assets/favicon.ico``
    The brand mark intended for the browser tab. Detects the brand
    silhouette by trimming any uniform background colour around the edges,
    then makes the result a square so favicons render cleanly at every size.

If ``favicon-source.png`` is missing, the favicon falls back to the same
``capitalpay-logo-source.png`` pipeline so older repos keep working.

Run:
    python scripts/generate_branding.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LOGO_SOURCE = ASSETS / "capitalpay-logo-source.png"
FAVICON_SOURCE = ASSETS / "favicon-source.png"

LOGO_PX = 256
FAVICON_SIZES = [16, 32, 48, 64]

# CapitalPay "cp" glyph detection — the mark is pure white on the gradient.
GLYPH_THRESHOLD = 200
GLYPH_MARGIN_PCT = 0.06

# Favicon background-trim tolerance (per-channel, 0–255). Anything within this
# distance of the corner colour is treated as background and trimmed.
BG_TOLERANCE = 24
# Padding added around the trimmed brand mark, expressed as a fraction of the
# square side. Small so the mark dominates the favicon.
FAVICON_MARGIN_PCT = 0.04


def _load(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing brand source image: {path.relative_to(ROOT)}."
        )
    return Image.open(path).convert("RGBA")


def _square_crop_on_glyph(src: Image.Image) -> Image.Image:
    """Crop ``src`` to a square centred on the bright "cp" glyph."""
    arr = np.array(src)
    h, w = arr.shape[:2]
    lum = arr[:, :, :3].mean(axis=2)
    mask = lum > GLYPH_THRESHOLD

    if not mask.any():
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        return src.crop((left, top, left + side, top + side))

    ys, xs = np.where(mask)
    gx0, gy0 = int(xs.min()), int(ys.min())
    gx1, gy1 = int(xs.max()) + 1, int(ys.max()) + 1
    cx, cy = (gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0
    glyph_side = max(gx1 - gx0, gy1 - gy0)
    side = int(round(glyph_side * (1.0 + 2.0 * GLYPH_MARGIN_PCT)))
    side = min(side, w, h)
    half = side / 2.0
    left = max(0, min(int(round(cx - half)), w - side))
    top = max(0, min(int(round(cy - half)), h - side))
    return src.crop((left, top, left + side, top + side))


def _square_crop_on_brand_mark(src: Image.Image) -> Image.Image:
    """Trim the uniform background colour, then square-pad the brand mark.

    Designed for the favicon source where the brand sits inside a flat dark
    (or solid) field. We:
      1. Sample the four corners to estimate the background colour.
      2. Mask out pixels within ``BG_TOLERANCE`` of that colour AND alpha 0.
      3. Compute the bounding box of what remains and centre it on a square
         transparent canvas with a small margin.
    """
    arr = np.array(src).astype(np.int16)
    h, w = arr.shape[:2]

    # Background colour = median of the four corner pixels (RGB only). Medians
    # ignore single stray noise pixels in any one corner.
    corners = np.stack([
        arr[0, 0, :3], arr[0, w - 1, :3],
        arr[h - 1, 0, :3], arr[h - 1, w - 1, :3],
    ])
    bg_rgb = np.median(corners, axis=0)

    diff = np.abs(arr[:, :, :3] - bg_rgb).max(axis=2)
    is_bg = diff <= BG_TOLERANCE
    is_transparent = arr[:, :, 3] == 0
    mask = ~(is_bg | is_transparent)

    if not mask.any():
        # Pathological — fall back to a centre square crop.
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        return src.crop((left, top, left + side, top + side))

    ys, xs = np.where(mask)
    bx0, by0 = int(xs.min()), int(ys.min())
    bx1, by1 = int(xs.max()) + 1, int(ys.max()) + 1
    bw, bh = bx1 - bx0, by1 - by0

    side = int(round(max(bw, bh) * (1.0 + 2.0 * FAVICON_MARGIN_PCT)))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    crop = src.crop((bx0, by0, bx1, by1))
    paste_x = (side - bw) // 2
    paste_y = (side - bh) // 2
    canvas.paste(crop, (paste_x, paste_y), crop)
    return canvas


def _resample(sq: Image.Image, px: int) -> Image.Image:
    return sq.resize((px, px), Image.LANCZOS)


def _write_logo() -> None:
    src = _load(LOGO_SOURCE)
    sq = _square_crop_on_glyph(src)
    out = ASSETS / "capitalpay-logo.png"
    _resample(sq, LOGO_PX).save(out, format="PNG", optimize=True)
    print(f"wrote {out.relative_to(ROOT)} (from {LOGO_SOURCE.name}, crop {sq.size[0]}×{sq.size[1]})")


def _write_favicon() -> None:
    if FAVICON_SOURCE.exists():
        src = _load(FAVICON_SOURCE)
        sq = _square_crop_on_brand_mark(src)
        source_label = FAVICON_SOURCE.name
    else:
        src = _load(LOGO_SOURCE)
        sq = _square_crop_on_glyph(src)
        source_label = LOGO_SOURCE.name

    out = ASSETS / "favicon.ico"
    frames = [_resample(sq, s) for s in FAVICON_SIZES]
    frames[0].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in FAVICON_SIZES],
        append_images=frames[1:],
    )
    print(f"wrote {out.relative_to(ROOT)} (from {source_label}, crop {sq.size[0]}×{sq.size[1]})")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    _write_logo()
    _write_favicon()


if __name__ == "__main__":
    main()
