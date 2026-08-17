"""Compare a rendered floor plane against vanilla floor sprites, pixel by pixel.

Answers whether the rig's 1px horizontal difference is a real offset or just a
different alpha threshold, by profiling both sprites' alpha the same way.

Run with:  uv run --python 3.12 --with pillow python tools/compare_floor.py <render.png>
"""
from __future__ import annotations

import collections
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")


def bbox_at(img: Image.Image, threshold: int) -> tuple[int, int, int, int]:
    w, h = img.size
    px = img.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > threshold:
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def row_profile(img: Image.Image, row_from_bottom: int) -> str:
    w, h = img.size
    px = img.load()
    y = h - 1 - row_from_bottom
    alphas = [px[x, y][3] for x in range(w)]
    first = next((i for i, a in enumerate(alphas) if a), None)
    last = next((i for i in range(w - 1, -1, -1) if alphas[i]), None)
    return (f"row {row_from_bottom:>3} from bottom: opaque x {first}..{last}   "
            f"edges a[{first}]={alphas[first] if first is not None else '-'} "
            f"a[{last}]={alphas[last] if last is not None else '-'}")


def vanilla_floor() -> Image.Image:
    """The most common vanilla floor sprite shape: trim box (0, 192, 126, 64)."""
    pack = TexturePack.read(PZ / "Tiles2x.floor.pack")
    for page in pack.pages:
        for e in page.entries:
            if (e.ox, e.oy, e.w, e.h) == (0, 192, 126, 64) and (e.ow, e.oh) == (128, 256):
                atlas = Image.open(io.BytesIO(page.png)).convert("RGBA")
                cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
                cell.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
                print(f"vanilla sample: {e.name}")
                return cell
    raise SystemExit("no vanilla floor sprite with the expected trim box")


def report(label: str, img: Image.Image) -> None:
    print(f"\n== {label} ==")
    for t in (0, 8, 64, 127):
        print(f"   bbox at alpha>{t:<4} {bbox_at(img, t)}")
    for row in (0, 1, 31, 62, 63):
        print("   " + row_profile(img, row))
    counts = collections.Counter(p[3] for p in img.getdata() if p[3])
    print(f"   distinct non-zero alpha values: {len(counts)} "
          f"(fully opaque pixels: {counts.get(255, 0)})")


if __name__ == "__main__":
    report("vanilla floor tile", vanilla_floor())
    if len(sys.argv) > 1:
        report(f"rendered {Path(sys.argv[1]).name}",
               Image.open(sys.argv[1]).convert("RGBA"))
