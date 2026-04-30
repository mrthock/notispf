#!/usr/bin/env python3
"""Regenerate icon assets from assets/icon.svg.

Outputs:
    assets/icon.png          — 512×512 master PNG
    assets/icon.ico          — multi-size Windows ICO (16–512 px)
    assets/png/icon_N.png    — individual PNGs at each size
    assets/icon.icns         — macOS ICNS (requires macOS for iconutil;
                               the .iconset folder is always written so you
                               can run iconutil manually on a Mac)

Requires:
    pip install cairosvg pillow
"""
import io
import shutil
import subprocess
import sys
import platform
from pathlib import Path

ROOT     = Path(__file__).parent.parent
SVG      = ROOT / "assets" / "icon.svg"
PNG      = ROOT / "assets" / "icon.png"
ICO      = ROOT / "assets" / "icon.ico"
ICNS     = ROOT / "assets" / "icon.icns"
ICONSET  = ROOT / "assets" / "icon.iconset"

ICO_SIZES = [16, 32, 48, 64, 128, 256, 512]

# macOS iconset spec: (filename, pixel_size)
ICONSET_SIZES = [
    ("icon_16x16.png",       16),
    ("icon_16x16@2x.png",    32),
    ("icon_32x32.png",       32),
    ("icon_32x32@2x.png",    64),
    ("icon_128x128.png",    128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png",    256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png",    512),
    ("icon_512x512@2x.png", 1024),
]


def render_svg(cairosvg, size: int) -> bytes:
    return cairosvg.svg2png(url=str(SVG), output_width=size, output_height=size)


def main():
    try:
        import cairosvg
    except ImportError:
        sys.exit("cairosvg not found — run: pip install cairosvg pillow")

    from PIL import Image

    print(f"Source: {SVG}")

    # ── Master 512-px PNG ────────────────────────────────────────────────────
    master_bytes = render_svg(cairosvg, 512)
    PNG.write_bytes(master_bytes)
    print(f"Written: {PNG}")

    master = Image.open(io.BytesIO(master_bytes)).convert("RGBA")

    def sized(px: int) -> Image.Image:
        if px == 512:
            return master
        return master.resize((px, px), Image.LANCZOS)

    # ── Individual PNGs ──────────────────────────────────────────────────────
    out_dir = ROOT / "assets" / "png"
    out_dir.mkdir(exist_ok=True)
    for s in ICO_SIZES:
        p = out_dir / f"icon_{s}.png"
        sized(s).save(p, format="PNG")
    print(f"Written: {out_dir}/icon_{{16..512}}.png")

    # ── Windows ICO ──────────────────────────────────────────────────────────
    frames = [sized(s) for s in ICO_SIZES]
    frames[0].save(
        ICO,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[1:],
    )
    print(f"Written: {ICO}  ({', '.join(str(s) for s in ICO_SIZES)} px)")

    # ── macOS ICNS ───────────────────────────────────────────────────────────
    # Always build the .iconset folder (works on any platform).
    # iconutil to convert it to .icns only runs on macOS.
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir()

    needed_px = sorted({px for _, px in ICONSET_SIZES})
    cache: dict[int, Image.Image] = {}
    for px in needed_px:
        if px == 1024:
            raw = render_svg(cairosvg, 1024)
            cache[1024] = Image.open(io.BytesIO(raw)).convert("RGBA")
        else:
            cache[px] = sized(px)

    for filename, px in ICONSET_SIZES:
        cache[px].save(ICONSET / filename, format="PNG")
    print(f"Written: {ICONSET}/  ({len(ICONSET_SIZES)} files)")

    if platform.system() == "Darwin":
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Written: {ICNS}")
        else:
            print(f"iconutil failed: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(
            f"Skipped {ICNS} — iconutil is macOS-only.\n"
            f"On your Mac, run:\n"
            f"  iconutil -c icns assets/icon.iconset -o assets/icon.icns"
        )


if __name__ == "__main__":
    main()
