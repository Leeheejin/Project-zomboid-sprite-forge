"""Derive PZ's light direction by comparing walls whose Facing is known.

Vanilla tile definitions tag every wall with ``Facing = N/S/E/W``. Averaging the
luminance of each facing group tells us, in isometric screen space, which way the
key light points — far more reliable than averaging whole sprites.

Run with:  uv run --python 3.12 --with pillow python tools/analyze_lighting.py
"""
from __future__ import annotations

import collections
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack
from pzforge.tiledef import TileDefinitions

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media")
OUT = Path(__file__).resolve().parents[1] / "reference"


def load_sprite_index() -> dict[str, tuple]:
    index = {}
    for name in ("Tiles2x.pack", "Tiles2x.floor.pack"):
        pack = TexturePack.read(PZ / "texturepacks" / name)
        for page in pack.pages:
            sheet = None
            for e in page.entries:
                index[e.name] = (page, e)
            del sheet
    return index


def cell_image(page, e, cache: dict) -> Image.Image:
    key = id(page)
    if key not in cache:
        cache[key] = Image.open(io.BytesIO(page.png)).convert("RGBA")
    crop = cache[key].crop((e.x, e.y, e.x + e.w, e.y + e.h))
    cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
    cell.paste(crop, (e.ox, e.oy))
    return cell


def main() -> None:
    tdefs = TileDefinitions.read(PZ / "newtiledefinitions.tiles")
    index = load_sprite_index()
    cache: dict = {}

    groups = collections.defaultdict(list)
    for ts in tdefs.tilesets:
        if "wall" not in ts.name.lower():
            continue
        for i, tile in enumerate(ts.tiles):
            facing = tile.props.get("Facing")
            if not facing or "doorframe" in ts.name.lower():
                continue
            hit = index.get(f"{ts.name}_{i}")
            if hit:
                groups[facing].append(hit)

    print("wall sprites found per facing:",
          {k: len(v) for k, v in sorted(groups.items())})

    result = {}
    for facing, items in sorted(groups.items()):
        lum_sum = px_count = 0
        for page, e in items[:600]:
            g = cell_image(page, e, cache).convert("LA")
            for v, a in g.get_flattened_data() if hasattr(g, "get_flattened_data") else g.getdata():
                if a > 200:
                    lum_sum += v
                    px_count += 1
        if px_count:
            result[facing] = {"sprites": len(items[:600]),
                              "mean_luminance": round(lum_sum / px_count, 2)}

    print("\n== mean luminance of wall faces, by facing ==")
    for facing, r in sorted(result.items(), key=lambda kv: -kv[1]["mean_luminance"]):
        print(f"   {facing}: {r['mean_luminance']:6.2f}   (n={r['sprites']})")

    if {"S", "W"} <= result.keys():
        d = result["S"]["mean_luminance"] - result["W"]["mean_luminance"]
        print(f"\n   S minus W = {d:+.2f}  -> "
              f"{'south' if d > 0 else 'west'}-facing wall is the lit side")

    path = OUT / "lighting_by_facing.json"
    path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
