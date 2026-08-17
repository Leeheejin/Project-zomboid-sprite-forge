"""Measure vanilla tone statistics *per sprite*, not across the whole tileset.

The distinction matters. Pooling every pixel of every vanilla tile gives a value
range spanning near-black shadow to near-white plaster, and forcing one small brown
crate to cover that range stretches its 30-value spread across 250 -- which turns
8-bit quantisation steps into visible speckle and drains the colour out.

What a custom sprite should match is the range vanilla *individual sprites* occupy:
how dark a typical tile sits, how much contrast it carries, how saturated it is.

Run with:
    uv run --python 3.12 --with pillow python tools/analyze_sprite_stats.py
"""
from __future__ import annotations

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


def quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1,
              max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def sprite_stats(cell: Image.Image) -> dict | None:
    values, sats = [], []
    left_lum, right_lum = [], []
    box = cell.getbbox()
    if box is None:
        return None
    mid_x = (box[0] + box[2]) / 2
    px = cell.load()

    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            r, g, b, a = px[x, y]
            if a < 200:
                continue
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            values.append(v)
            sats.append(s)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            (left_lum if x < mid_x else right_lum).append(lum)

    if len(values) < 400 or not left_lum or not right_lum:
        return None
    values.sort()
    sats.sort()
    stats = {
        "median_value": quantile(values, 0.5),
        # Inter-quartile spread is a robust stand-in for contrast.
        "value_spread": quantile(values, 0.75) - quantile(values, 0.25),
        "median_saturation": quantile(sats, 0.5),
        "saturation_spread": quantile(sats, 0.75) - quantile(sats, 0.25),
    }
    # How much brighter the south-facing (screen left) side reads than the east side.
    # Symmetric objects only: an asymmetric sprite makes this meaningless, so it is
    # reported as a distribution over many sprites rather than trusted per sprite.
    mean_left = sum(left_lum) / len(left_lum)
    mean_right = sum(right_lum) / len(right_lum)
    stats["left_over_right"] = mean_left / mean_right if mean_right > 1 else 1.0
    return stats


def main(sample: int = 500) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 40 and e.h > 60]
    items = random.Random(17).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    collected: dict[str, list[float]] = {}
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        crop = cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h))
        stats = sprite_stats(crop)
        if stats is None:
            continue
        for key, value in stats.items():
            collected.setdefault(key, []).append(value)

    profile = {"sprites_sampled": len(collected.get("median_value", []))}
    print(f"sampled {profile['sprites_sampled']} vanilla sprites\n")
    print(f"{'statistic':<20} {'p10':>7} {'p25':>7} {'p50':>7} {'p75':>7} {'p90':>7}")
    for key, values in collected.items():
        values.sort()
        row = {f"p{int(q * 100)}": round(quantile(values, q), 4)
               for q in (0.10, 0.25, 0.50, 0.75, 0.90)}
        profile[key] = row
        print(f"{key:<20} " + " ".join(f"{row[f'p{int(q*100)}']:7.4f}"
                                       for q in (0.10, 0.25, 0.50, 0.75, 0.90)))

    path = OUT / "sprite_stats.json"
    path.write_text(json.dumps(profile, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
