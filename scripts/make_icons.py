#!/usr/bin/env python3
"""
Generate notispf icon assets for all platforms.

Usage:
    pip install pillow
    python scripts/make_icons.py

Outputs:
    assets/icon.png   — 1024×1024 source PNG (used by Linux AppImage)
    assets/icon.ico   — multi-resolution Windows icon
    assets/icon.icns  — macOS icon bundle (macOS only; sips + iconutil required)

Commit all generated files.  CI re-generates icon.icns on the macOS runner
from icon.png using sips/iconutil, so you only need macOS for local preview.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)

BG     = (30, 30, 30, 255)    # app background dark
BORDER = (0, 204, 204, 255)   # cyan
FG     = (0, 204, 204, 255)   # cyan text
GRAY   = (102, 102, 102, 255) # subtitle


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def draw_icon(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r    = size // 8
    bw   = max(2, size // 64)

    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)
    draw.rounded_rectangle(
        [bw, bw, size - 1 - bw, size - 1 - bw],
        radius=r - bw, outline=BORDER, width=bw,
    )

    font_big   = _font(size * 9 // 20)
    font_small = _font(size // 10)

    bb = draw.textbbox((0, 0), "nf", font=font_big)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text(
        ((size - tw) // 2 - bb[0], size // 2 - th // 2 - size // 16 - bb[1]),
        "nf", font=font_big, fill=FG,
    )

    bb2 = draw.textbbox((0, 0), "notispf", font=font_small)
    draw.text(
        ((size - (bb2[2] - bb2[0])) // 2 - bb2[0], size * 11 // 16 - bb2[1]),
        "notispf", font=font_small, fill=GRAY,
    )

    return img


# PNG
draw_icon(1024).save(ASSETS / "icon.png")
print("wrote assets/icon.png")

# ICO — pass the large image with sizes= and Pillow downsamples each size
draw_icon(1024).save(
    ASSETS / "icon.ico",
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("wrote assets/icon.ico")

# ICNS (macOS only)
if sys.platform == "darwin":
    icns_map = [
        (16,   "icon_16x16"),
        (32,   "icon_16x16@2x"),
        (32,   "icon_32x32"),
        (64,   "icon_32x32@2x"),
        (128,  "icon_128x128"),
        (256,  "icon_128x128@2x"),
        (256,  "icon_256x256"),
        (512,  "icon_256x256@2x"),
        (512,  "icon_512x512"),
        (1024, "icon_512x512@2x"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "notispf.iconset"
        iconset.mkdir()
        for sz, name in icns_map:
            draw_icon(sz).save(iconset / f"{name}.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ASSETS / "icon.icns")],
            check=True,
        )
    print("wrote assets/icon.icns")
else:
    print("skipped icon.icns (macOS only) — CI generates it on the macOS runner")
