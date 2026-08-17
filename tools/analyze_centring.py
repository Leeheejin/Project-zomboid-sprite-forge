"""Are vanilla object sprites centred on the tile, or offset from it?

The recreated drum sits 2 px left of the vanilla one. Either the rig's horizontal
alignment is wrong, or that sprite is drawn off-centre. Floor tiles already pin the
rig (its rendered floor plane trims to vanilla's exact box), so this asks the same
question of *object* sprites.

Asymmetric objects would swamp the answer, so only sprites whose silhouette closely
matches its own mirror image are counted.

Run with:
    uv run --python 3.12 --with pillow python tools/analyze_centring.py
"""
from __future__ import annotations

import io
import random
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")
CELL_W = 128
#: Where the rig puts the tile centre: vanilla's floor diamond spans columns 0..125,
#: so its centre is at continuous x = 63.0.
TILE_CENTRE = 63.0


def symmetry(mask: Image.Image) -> float:
    """Intersection-over-union of a silhouette with its own mirror, about its bbox."""
    box = mask.getbbox()
    if box is None:
        return 0.0
    crop = mask.crop(box)
    flipped = crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    a = [p > 128 for p in crop.getdata()]
    b = [p > 128 for p in flipped.getdata()]
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 0.0


def main(sample: int = 900, symmetry_floor: float = 0.94) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 30 and e.h > 40]
    items = random.Random(41).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    offsets: list[float] = []
    widths = Counter()
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
        cell.paste(cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
        alpha = cell.getchannel("A")
        if symmetry(alpha) < symmetry_floor:
            continue
        box = alpha.getbbox()
        # Continuous centre of the opaque span.
        centre = (box[0] + box[2]) / 2.0
        offsets.append(centre - TILE_CENTRE)
        widths[box[2] - box[0]] += 1

    if not offsets:
        raise SystemExit("no symmetric sprites found")
    offsets.sort()

    def q(p):
        return offsets[min(len(offsets) - 1, int(p * (len(offsets) - 1)))]

    mean = sum(offsets) / len(offsets)
    print(f"{len(offsets)} symmetric sprites (mirror IoU >= {symmetry_floor})\n")
    print(f"horizontal centre minus the tile centre ({TILE_CENTRE}):")
    print(f"   mean {mean:+.2f} px   median {q(0.5):+.2f} px")
    print(f"   p10 {q(0.10):+.2f}   p25 {q(0.25):+.2f}   "
          f"p75 {q(0.75):+.2f}   p90 {q(0.90):+.2f}")
    exact = sum(1 for o in offsets if abs(o) < 0.51)
    plus_two = sum(1 for o in offsets if abs(o - 2.0) < 0.51)
    plus_one = sum(1 for o in offsets if abs(o - 1.0) < 0.51)
    print(f"\n   within +-0.5px of the tile centre : {exact} "
          f"({exact / len(offsets) * 100:.0f}%)")
    print(f"   at +1.0px                         : {plus_one} "
          f"({plus_one / len(offsets) * 100:.0f}%)")
    print(f"   at +2.0px                         : {plus_two} "
          f"({plus_two / len(offsets) * 100:.0f}%)")
    print(f"\n   -> {'centred on the tile' if abs(mean) < 0.6 else 'systematically offset'}")


if __name__ == "__main__":
    main()
