"""Regenerate favicon.ico + capitalpay-logo.png from the CapitalPay logo source.

Source of truth is ``assets/capitalpay-logo-source.png`` — the brand-provided
artwork. The source is a (270×247) gradient plate with a white "cp" glyph
inside; we programmatically:

1. Detect the glyph bbox via a brightness threshold on the RGB plane.
2. Expand that bbox to a SQUARE centred on the glyph's geometric centre
   (keeps the "cp" perfectly centred in the output).
3. Add a small margin so the glyph has breathing room at favicon sizes.
4. Resample to the target pixel sizes with LANCZOS.

This makes small favicons (16/32 px) look crisp and aligned instead of a tiny
glyph floating in a sea of gradient.

Run:
    python scripts/generate_branding.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "capitalpay-logo-source.png"

# In-app logo size. 256 gives crisp rendering through hero-size usages.
LOGO_PX = 256
# Multi-resolution favicon. 16/32/48 cover every browser + Windows shell;
# 64 future-proofs hi-dpi Chrome tab strips.
FAVICON_SIZES = [16, 32, 48, 64]

# Brightness threshold used to pick out the white glyph from the gradient.
# The "cp" mark in the current brand file is pure white; anything 200+ across
# the RGB plane is glyph.
GLYPH_THRESHOLD = 200
# Margin around the glyph, as a fraction of the square side. Kept small so the
# mark dominates the frame at 16/32 px favicons instead of drowning in gradient.
MARGIN_PCT = 0.06


def _load_source() -> Image.Image:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Missing brand source image: {SOURCE.relative_to(ROOT)}. "
            "Drop the CapitalPay logo PNG there before running this script."
        )
    return Image.open(SOURCE).convert("RGBA")


def _square_crop_on_glyph(src: Image.Image) -> Image.Image:
    """Crop ``src`` to a square centred on the detected glyph.

    Falls back to a plain centre-square if no glyph pixels are detected.
    """
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

    # Centre of the glyph.
    cx = (gx0 + gx1) / 2.0
    cy = (gy0 + gy1) / 2.0

    # Base side: the larger of glyph width/height, grown by MARGIN_PCT.
    glyph_side = max(gx1 - gx0, gy1 - gy0)
    side = int(round(glyph_side * (1.0 + 2.0 * MARGIN_PCT)))

    # Don't exceed the source canvas — if we do, shrink to fit.
    side = min(side, w, h)

    half = side / 2.0
    left = int(round(cx - half))
    top = int(round(cy - half))

    # Clamp into the canvas.
    left = max(0, min(left, w - side))
    top = max(0, min(top, h - side))

    return src.crop((left, top, left + side, top + side))


def _resample(sq: Image.Image, px: int) -> Image.Image:
    return sq.resize((px, px), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    src = _load_source()
    sq = _square_crop_on_glyph(src)
    print(f"glyph-centred square crop: {sq.size[0]}×{sq.size[1]}")

    logo_path = ASSETS / "capitalpay-logo.png"
    _resample(sq, LOGO_PX).save(logo_path, format="PNG", optimize=True)
    print(f"wrote {logo_path.relative_to(ROOT)}")

    ico_path = ASSETS / "favicon.ico"
    frames = [_resample(sq, s) for s in FAVICON_SIZES]
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in FAVICON_SIZES],
        append_images=frames[1:],
    )
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
