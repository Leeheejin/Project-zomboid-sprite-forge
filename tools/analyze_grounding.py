"""Measure how vanilla sprites darken toward the ground.

Renders of an object standing on a plane do not reproduce this. Measured directly, a
ground plane at a realistic albedo changes a sprite's base by under one luminance unit
-- the light it blocks and the light it bounces cancel almost exactly. Vanilla's
grounding is therefore painted, not simulated, and the only way to match it is to
measure the curve and apply it.

For every sprite, each scanline's mean luminance is divided by that sprite's own
median, which removes albedo and leaves the shading profile. The curve is then binned
by height above the bottom of the cell -- the row where the tile's floor sits.

Run with:
    uv run --python 3.12 --with pillow python tools/analyze_grounding.py
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")
OUT = Path(__file__).resolve().parents[1] / "reference"
CELL_H = 256
#: Rows above the cell bottom, in 2x pixels. The floor diamond spans the bottom 64.
BINS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 24), (24, 32), (32, 48),
        (48, 64), (64, 96), (96, 128), (128, 192)]


def median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else 0.0


def profile(cell: Image.Image) -> dict[int, float] | None:
    px = cell.load()
    w, h = cell.size
    rows: dict[int, tuple[float, int]] = {}
    everything: list[float] = []
    for y in range(h):
        total = count = 0.0
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 200:
                continue
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            total += lum
            count += 1
            everything.append(lum)
        if count >= 6:
            rows[h - 1 - y] = (total / count, int(count))
    if len(everything) < 600 or len(rows) < 12:
        return None
    mid = median(everything)
    if mid < 12:
        return None
    return {height: value / mid for height, (value, _n) in rows.items()}


def main(sample: int = 700) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, CELL_H) and e.w > 40 and e.h > 50]
    items = random.Random(53).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    buckets: dict[tuple[int, int], list[float]] = {b: [] for b in BINS}
    used = 0
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
        cell.paste(cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
        prof = profile(cell)
        if prof is None:
            continue
        used += 1
        for lo, hi in BINS:
            vals = [v for height, v in prof.items() if lo <= height < hi]
            if vals:
                buckets[(lo, hi)].append(sum(vals) / len(vals))

    print(f"{used} vanilla sprites\n")
    print(f"{'rows above cell bottom':<24} {'ratio to sprite median':>22} {'n':>6}")
    curve = {}
    for b in BINS:
        vals = buckets[b]
        if not vals:
            continue
        ratio = median(vals)
        curve[b[0]] = round(ratio, 4)
        bar = "#" * int(round(ratio * 30))
        print(f"{str(b[0]) + '-' + str(b[1]):<24} {ratio:22.3f} {len(vals):6d}  {bar}")

    path = OUT / "grounding_curve.json"
    path.write_text(json.dumps({"sprites": used, "cell_height": CELL_H,
                                "bins": [list(b) for b in BINS],
                                "ratio_by_row": curve}, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
