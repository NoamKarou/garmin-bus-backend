#!/usr/bin/env python3
"""Generate a Connect IQ bitmap font (BMFont .fnt + .png atlas) from a TTF/OTF.

Connect IQ has no runtime font fallback: the built-in ``Graphics.FONT_*`` fonts
are pre-baked device bitmaps that do not contain Hebrew glyphs. Any text that
can contain Hebrew needs a custom font compiled into the app resources.

The resource compiler accepts BMFont's text format (``.fnt``) plus its PNG
atlas. This script produces both without the BMFont / Connect IQ Font Tool GUI.

Usage:
    python gen_bitmap_font.py --font path/to/Heebo-Regular.ttf --size 48 \\
        --out path/to/hebrew_small

Writes:
    <out>.fnt     BMFont text descriptor (Unicode charset)
    <out>_0.png   8-bit atlas, white antialiased glyphs on black

Notes:
    * Font sizes are baked into the bitmap, use the pixel size the device
      reference lists for the matching ``Graphics.FONT_*`` on that product.
    * ``--no-antialias`` produces a 1-bit atlas, which uses less runtime memory.
    * If you publish the app, check the source font's license: Heebo is SIL OFL
      and safe to embed, many Hebrew Microsoft/Designed fonts are not.

Requires Pillow (``pip install pillow``).
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("This script needs Pillow: pip install pillow")


# Characters that a mostly-Hebrew watch UI can realistically show. ASCII keeps
# mixed strings ("קו 480", English stop names) working inside the same font;
# the Hebrew block covers the alphabet plus maqaf/geresh/gershayim.
DEFAULT_CHARS = (
    [chr(c) for c in range(0x20, 0x7F)]          # ASCII printable
    + [chr(c) for c in range(0x05D0, 0x05EB)]    # Hebrew alef..tav
    + ["־", "׳", "״"]             # maqaf, geresh, gershayim
    + ["–", "—", "…",             # en/em dash, ellipsis
       "‘", "’", "“", "”"]   # curly quotes
)


def _render_glyph(font: ImageFont.FreeTypeFont, ch: str) -> Image.Image:
    """Render one character into a tight L-mode bitmap (white on black)."""
    bbox = font.getbbox(ch)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width <= 0 or height <= 0:
        return Image.new("L", (0, 0), 0)
    img = Image.new("L", (width, height), 0)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), ch, font=font, fill=255)
    return img


def _is_missing(img: Image.Image, notdef: Image.Image) -> bool:
    """True when the glyph rendered exactly like the font's .notdef box."""
    if img.size != notdef.size or img.size == (0, 0):
        return False
    return img.tobytes() == notdef.tobytes()


def _next_pow2(value: int, minimum: int = 64) -> int:
    size = minimum
    while size < value:
        size *= 2
    return size


def _layout(glyphs: list[dict], sheet_width: int) -> tuple[int, list[dict]]:
    """Place glyphs left-to-right, wrapping rows. Returns (height, glyphs)."""
    x = 0
    y = 0
    row_height = 0
    for glyph in glyphs:
        if glyph["width"] == 0 or glyph["height"] == 0:
            glyph["x"] = glyph["y"] = 0
            continue
        if x + glyph["width"] > sheet_width:
            x = 0
            y += row_height + 1
            row_height = 0
        glyph["x"] = x
        glyph["y"] = y
        x += glyph["width"] + 1
        row_height = max(row_height, glyph["height"])
    return y + row_height, glyphs


def build(
    font_path: str,
    size: int,
    out_prefix: str,
    chars: list[str] | None = None,
    antialias: bool = True,
) -> tuple[int, int]:
    chars = chars if chars is not None else DEFAULT_CHARS
    font = ImageFont.truetype(font_path, size)
    ascent, descent = font.getmetrics()
    # A code point Heebo has no glyph for renders as the .notdef box; any glyph
    # identical to it is missing from the font and is left out of the atlas.
    notdef = _render_glyph(font, chr(0xE000))

    glyphs: list[dict] = []
    skipped: list[str] = []
    for ch in chars:
        img = _render_glyph(font, ch)
        if _is_missing(img, notdef):
            skipped.append(ch)
            continue
        if not antialias and img.size != (0, 0):
            img = img.point(lambda v: 255 if v >= 128 else 0)
        glyphs.append({
            "id": ord(ch),
            "img": img,
            "width": img.width,
            "height": img.height,
            "xoffset": font.getbbox(ch)[0],
            "yoffset": 0,  # filled in below, after the baseline is known
            "advance": int(round(font.getlength(ch))),
        })

    # Vertical metrics. Pillow reports the font's full ascender/descender; the
    # bitmap font's baseline is placed so the tallest glyph has a small top
    # padding (Garmin's own Roboto fonts leave ~0.08 em above cap height).
    inked = [g for g in glyphs if g["height"] > 0]
    top_rel_min = min(font.getbbox(chr(g["id"]))[1] - ascent for g in inked)
    bottom_rel_max = max(font.getbbox(chr(g["id"]))[3] - ascent for g in inked)
    pad_top = max(1, int(round(size * 0.08)))
    base = -top_rel_min + pad_top
    line_height = base + max(0, bottom_rel_max + int(round(size * 0.02)))

    for glyph in glyphs:
        bbox = font.getbbox(chr(glyph["id"]))
        glyph["yoffset"] = base + (bbox[1] - ascent)

    sheet_width = 256
    height, glyphs = _layout(glyphs, sheet_width)
    if height > 512:
        sheet_width = 512
        height, glyphs = _layout(glyphs, sheet_width)
    sheet_height = _next_pow2(height, 64)

    sheet = Image.new("L", (sheet_width, sheet_height), 0)
    for glyph in glyphs:
        if glyph["height"] > 0 and glyph["width"] > 0:
            sheet.paste(glyph["img"], (glyph["x"], glyph["y"]))

    out_dir = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(out_dir, exist_ok=True)
    png_name = os.path.basename(out_prefix) + "_0.png"
    sheet.save(os.path.join(out_dir, png_name))

    face = os.path.splitext(os.path.basename(font_path))[0]
    lines = [
        f'info face="{face}" size=-{size} bold=0 italic=0 charset="" '
        f"unicode=1 stretchH=100 smooth={1 if antialias else 0} "
        f"aa={1 if antialias else 0} padding=0,0,0,0 spacing=1,1 outline=0",
        f"common lineHeight={line_height} base={base} scaleW={sheet_width} "
        f"scaleH={sheet_height} pages=1 packed=0 alphaChnl=1 redChnl=0 "
        f"greenChnl=0 blueChnl=0",
        f'page id=0 file="{png_name}"',
        f"chars count={len(glyphs)}",
    ]
    for glyph in glyphs:
        lines.append(
            f"char id={glyph['id']:<5d} x={glyph['x']:<5d} y={glyph['y']:<5d} "
            f"width={glyph['width']:<5d} height={glyph['height']:<5d} "
            f"xoffset={glyph['xoffset']:<5d} yoffset={glyph['yoffset']:<5d} "
            f"xadvance={glyph['advance']:<5d} page=0  chnl=15"
        )
    lines.append("kernings count=0")

    fnt_path = out_prefix + ".fnt"
    with open(fnt_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")

    if skipped:
        print(f"  skipped {len(skipped)} glyph(s) missing from {face}: "
              + " ".join(f"U+{ord(c):04X}" for c in skipped))
    return sheet_width, sheet_height


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", required=True, help="source TTF/OTF path")
    parser.add_argument("--size", type=int, required=True,
                        help="pixel size (matches a Graphics.FONT_* on the device)")
    parser.add_argument("--out", required=True,
                        help="output prefix, e.g. resources/fonts/hebrew_small")
    parser.add_argument("--no-antialias", action="store_true",
                        help="produce a 1-bit font (smaller at runtime)")
    args = parser.parse_args()

    width, height = build(
        args.font, args.size, args.out, antialias=not args.no_antialias
    )
    print(f"{args.out}.fnt  atlas {width}x{height}")


if __name__ == "__main__":
    main()
