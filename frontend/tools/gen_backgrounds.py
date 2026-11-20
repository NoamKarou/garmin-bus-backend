"""Generate the per-screen-size background bitmaps.

`resources/drawables/background.png` is the source artwork. Connect IQ cannot
scale bitmaps at draw time on every supported device, and the family spans
several round screen sizes, so this script writes a resized copy into a
screen-size resource qualifier folder for each supported resolution.

Re-run after replacing the source artwork:

    python tools/gen_backgrounds.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "resources" / "drawables" / "background.png"

# Round screen sizes of the supported products:
#   venu3s, vivoactive5 -> 390; venu3 -> 454; vivoactive4 -> 260; vivoactive4s -> 218
SIZES = (390, 454, 260, 218)

DRAWABLES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<resources>
    <drawables>
        <bitmap id="Background" filename="background.png"/>
    </drawables>
</resources>
"""


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    for size in SIZES:
        folder = ROOT / f"resources-round-{size}x{size}" / "drawables"
        folder.mkdir(parents=True, exist_ok=True)
        resized = image.resize((size, size), Image.LANCZOS)
        resized.save(folder / "background.png")
        (folder / "drawables.xml").write_text(DRAWABLES_XML, encoding="utf-8")
        print(f"wrote {folder.relative_to(ROOT)}/background.png ({size}x{size})")


if __name__ == "__main__":
    main()
