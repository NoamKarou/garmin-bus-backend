#!/usr/bin/env python3
"""Regenerate the Hebrew bitmap fonts bundled with the watch app.

Connect IQ bakes font sizes into the bitmap, so each product needs a font set
matching its own ``Graphics.FONT_*`` pixel sizes (see the Connect IQ Device
Reference). The base ``resources`` folder targets 390x390 products; the
``resources-<product>`` folders override the same resource ids for products
whose fonts are a different size.

Run from the repo root or from ``frontend/``:

    python frontend/tools/gen_hebrew_fonts.py
    python frontend/tools/gen_hebrew_fonts.py --font "C:/path/to/Other.ttf"

Sizes below are the FONT_TINY / FONT_SMALL / FONT_MEDIUM pixel sizes for each
product. Re-check them with the Device Reference if you add a product.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_bitmap_font import build  # noqa: E402

FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_FONT_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\Heebo-Regular.ttf"),
    r"C:\Windows\Fonts\Heebo-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]

# resource folder -> {output name: pixel size}
FONT_SETS = {
    # vivoactive5 / venu3s (390x390)
    "resources": {"tiny": 41, "small": 48, "medium": 54},
    # venu3 (454x454)
    "resources-venu3": {"tiny": 45, "small": 50, "medium": 58},
    # vivoactive4 (260x260)
    "resources-vivoactive4": {"tiny": 27, "small": 30, "medium": 35},
    # vivoactive4s (218x218)
    "resources-vivoactive4s": {"tiny": 23, "small": 26, "medium": 30},
}


def find_font(explicit: str | None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            sys.exit(f"font not found: {explicit}")
        return explicit
    for path in DEFAULT_FONT_PATHS:
        if os.path.exists(path):
            return path
    sys.exit(
        "No Hebrew source font found. Pass one with --font, for example:\n"
        "  python frontend/tools/gen_hebrew_fonts.py "
        '--font "C:/Windows/Fonts/arial.ttf"'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", help="source TTF/OTF with Hebrew glyphs")
    args = parser.parse_args()

    font_path = find_font(args.font)
    print(f"source font: {font_path}")

    for folder, sizes in FONT_SETS.items():
        out_dir = os.path.join(FRONTEND_DIR, folder, "fonts")
        print(f"{folder}:")
        for name, size in sizes.items():
            prefix = os.path.join(out_dir, f"hebrew_{name}")
            build(font_path, size, prefix)
            print(f"  hebrew_{name}: {size}px")


if __name__ == "__main__":
    main()
