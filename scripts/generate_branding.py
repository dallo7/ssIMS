"""Regenerate favicon.ico + capitalpay-logo.png from the CapitalPay logo source.

Source of truth is ``assets/capitalpay-logo-source.png`` — the brand-provided
artwork. We resample it to a standardised in-app logo size and a multi-size
ICO for the browser tab favicon.

Run:
    python scripts/generate_branding.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "capitalpay-logo-source.png"

# In-app logo size. 256 gives crisp rendering through hero-size usages while
# keeping the asset well under 50 KB.
LOGO_PX = 256
# Multi-resolution favicon. 16/32/48 cover every browser + Windows shell;
# 64 future-proofs hi-dpi Chrome tab strips.
FAVICON_SIZES = [16, 32, 48, 64]


def _load_source() -> Image.Image:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Missing brand source image: {SOURCE.relative_to(ROOT)}. "
            "Drop the CapitalPay logo PNG there before running this script."
        )
    return Image.open(SOURCE).convert("RGBA")


def _resize(src: Image.Image, px: int) -> Image.Image:
    """LANCZOS-downscale ``src`` to a square ``px`` × ``px`` canvas."""
    # Square-crop to avoid stretching when the source is non-square. Logos
    # should already be square, but guard against future updates.
    w, h = src.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = src.crop((left, top, left + side, top + side))
    return cropped.resize((px, px), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    src = _load_source()

    logo_path = ASSETS / "capitalpay-logo.png"
    _resize(src, LOGO_PX).save(logo_path, format="PNG", optimize=True)
    print(f"wrote {logo_path.relative_to(ROOT)}")

    ico_path = ASSETS / "favicon.ico"
    frames = [_resize(src, s) for s in FAVICON_SIZES]
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in FAVICON_SIZES],
        append_images=frames[1:],
    )
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
