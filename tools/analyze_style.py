"""Measure PZ's tile geometry and colour statistics straight from the shipped packs.

Run with:  uv run --python 3.12 --with pillow python tools/analyze_style.py
"""
from __future__ import annotations

import collections
import colorsys
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


def sprites(pack_path: Path, limit: int | None = None, seed: int = 7):
    """Yield (name, PIL.Image) for sprites, re-expanded to their untrimmed cell."""
    pack = TexturePack.read(pack_path)
    items = [(p, e) for p in pack.pages for e in p.entries]
    if limit and len(items) > limit:
        items = random.Random(seed).sample(items, limit)
    cache: dict[int, Image.Image] = {}
    for page, e in items:
        key = id(page)
        if key not in cache:
            cache[key] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        sheet = cache[key]
        crop = sheet.crop((e.x, e.y, e.x + e.w, e.y + e.h))
        cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
        cell.paste(crop, (e.ox, e.oy))
        yield e.name, cell, e


def geometry() -> dict:
    """Where does the floor diamond sit inside a 128x256 cell?"""
    pack = TexturePack.read(PZ / "Tiles2x.floor.pack")
    boxes = collections.Counter()
    for page in pack.pages:
        for e in page.entries:
            if (e.ow, e.oh) == (128, 256):
                boxes[(e.ox, e.oy, e.w, e.h)] += 1
    top = boxes.most_common(6)
    print("== floor sprite trim boxes in a 128x256 cell (ox, oy, w, h) x count ==")
    for box, n in top:
        print(f"   {box}  x{n}")
    (ox, oy, w, h), _ = top[0]
    print(f"\n   -> diamond {w}x{h} px, ratio {w / h:.3f}, "
          f"bottom edge at y={oy + h} of {256}")
    return {"cell": [128, 256], "diamond": [w, h], "diamond_origin": [ox, oy]}


def colours(sample: int = 400) -> dict:
    """Value/saturation envelope + dominant palette of vanilla wall & object tiles."""
    lum_hist = [0] * 256
    sat_hist = [0] * 101
    hue_hist = [0] * 360
    palette = collections.Counter()
    total = 0
    for _name, cell, _e in sprites(PZ / "Tiles2x.pack", limit=sample):
        small = cell.resize((32, 64), Image.Resampling.BILINEAR)
        for r, g, b, a in small.getdata():
            if a < 128:
                continue
            total += 1
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            lum_hist[int(v * 255)] += 1
            sat_hist[int(s * 100)] += 1
            if s > 0.08:
                hue_hist[int(h * 359)] += 1
            palette[(r >> 4 << 4, g >> 4 << 4, b >> 4 << 4)] += 1

    def pct(hist, q, scale):
        target = sum(hist) * q
        run = 0
        for i, n in enumerate(hist):
            run += n
            if run >= target:
                return i / scale
        return len(hist) / scale

    stats = {
        "opaque_samples": total,
        "value": {f"p{int(q*100)}": round(pct(lum_hist, q, 255), 4)
                  for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)},
        "saturation": {f"p{int(q*100)}": round(pct(sat_hist, q, 100), 4)
                       for q in (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)},
        "dominant_hues_deg": [h for h, _ in collections.Counter(
            {i: n for i, n in enumerate(hue_hist)}).most_common(8)],
        "top_colours": [{"rgb": list(c), "share": round(n / max(total, 1), 4)}
                        for c, n in palette.most_common(24)],
    }
    print("\n== value (brightness) percentiles ==")
    print("   ", stats["value"])
    print("== saturation percentiles ==")
    print("   ", stats["saturation"])
    print("== dominant hues (deg) ==")
    print("   ", stats["dominant_hues_deg"])
    print("== top quantised colours ==")
    for c in stats["top_colours"][:10]:
        print(f"    {tuple(c['rgb'])}  {c['share']*100:.2f}%")
    return stats


def lighting(sample: int = 250) -> dict:
    """Which side of a tile is lit? Compares mean luminance of left vs right half."""
    left = right = top = bottom = 0.0
    n = 0
    for _name, cell, _e in sprites(PZ / "Tiles2x.pack", limit=sample, seed=11):
        g = cell.convert("LA").resize((32, 64), Image.Resampling.BILINEAR)
        px = list(g.getdata())

        def mean(idxs):
            vals = [px[i][0] for i in idxs if px[i][1] > 128]
            return sum(vals) / len(vals) if vals else None

        lv = mean([y * 32 + x for y in range(64) for x in range(16)])
        rv = mean([y * 32 + x for y in range(64) for x in range(16, 32)])
        tv = mean([y * 32 + x for y in range(32) for x in range(32)])
        bv = mean([y * 32 + x for y in range(32, 64) for x in range(32)])
        if None in (lv, rv, tv, bv):
            continue
        left += lv; right += rv; top += tv; bottom += bv
        n += 1
    res = {"samples": n, "mean_left": round(left / n, 1), "mean_right": round(right / n, 1),
           "mean_top": round(top / n, 1), "mean_bottom": round(bottom / n, 1)}
    res["left_minus_right"] = round(res["mean_left"] - res["mean_right"], 1)
    res["top_minus_bottom"] = round(res["mean_top"] - res["mean_bottom"], 1)
    print("\n== lighting bias ==")
    print("   ", res)
    return res


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    profile = {"geometry": geometry(), "colour": colours(), "lighting": lighting()}
    (OUT / "vanilla_profile.json").write_text(json.dumps(profile, indent=2))
    print(f"\nwrote {OUT / 'vanilla_profile.json'}")
