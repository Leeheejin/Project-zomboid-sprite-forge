"""Measure how much local detail vanilla sprites carry.

The tone statistics in analyze_sprite_stats.py are blind to structure: a smooth
gradient and a sprite covered in painted seams, bolts and streaks can share the same
median value, spread and saturation. That is how a featureless barrel scored "inside
the vanilla band" on every axis while looking nothing like the tile it copied.

Two structural measures fix that:

* **detail energy** -- mean absolute luminance step between neighbouring opaque
  pixels. High for hand-painted wear, low for a clean procedural surface.
* **dark contour share** -- fraction of opaque pixels that are much darker than the
  sprite's median. PZ tiles outline forms with dark seams and recesses, and a render
  without them reads as soft even when its overall contrast matches.

Run with:
    uv run --python 3.12 --with pillow python tools/analyze_detail.py
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


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[idx]


def structure_stats(cell: Image.Image) -> dict | None:
    """Detail energy and dark-contour share for one sprite."""
    img = cell.convert("RGBA")
    w, h = img.size
    px = img.load()

    lum: list[float | None] = []
    opaque: list[float] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 200:
                lum.append(None)
                continue
            v = 0.2126 * r + 0.7152 * g + 0.0722 * b
            lum.append(v)
            opaque.append(v)
    if len(opaque) < 400:
        return None

    steps = []
    for y in range(h):
        row = y * w
        for x in range(w):
            here = lum[row + x]
            if here is None:
                continue
            # Only compare against neighbours that are also opaque, so the silhouette
            # edge does not masquerade as interior detail.
            for j in (row + x + 1, row + x + w):
                if j < len(lum) and lum[j] is not None:
                    steps.append(abs(here - lum[j]))
    if not steps:
        return None

    median_lum = quantile(opaque, 0.5)
    dark_cut = median_lum * 0.65
    return {
        "detail_energy": sum(steps) / len(steps) / 255.0,
        "detail_p90": quantile(steps, 0.90) / 255.0,
        "dark_contour_share": sum(1 for v in opaque if v < dark_cut) / len(opaque),
    }


def main(sample: int = 400) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 40 and e.h > 60]
    items = random.Random(31).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    collected: dict[str, list[float]] = {}
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        stats = structure_stats(cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h)))
        if stats is None:
            continue
        for key, value in stats.items():
            collected.setdefault(key, []).append(value)

    profile = {"sprites_sampled": len(collected.get("detail_energy", []))}
    print(f"sampled {profile['sprites_sampled']} vanilla sprites\n")
    print(f"{'statistic':<20} {'p10':>7} {'p25':>7} {'p50':>7} {'p75':>7} {'p90':>7}")
    for key, values in collected.items():
        row = {f"p{int(q * 100)}": round(quantile(values, q), 4)
               for q in (0.10, 0.25, 0.50, 0.75, 0.90)}
        profile[key] = row
        print(f"{key:<20} " + " ".join(f"{row[f'p{int(q*100)}']:7.4f}"
                                       for q in (0.10, 0.25, 0.50, 0.75, 0.90)))

    path = OUT / "detail_stats.json"
    path.write_text(json.dumps(profile, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
