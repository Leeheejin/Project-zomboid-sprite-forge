"""Index *every* vanilla tile sprite, not a sample of them.

Everything measured so far came from a few hundred random sprites, which is enough to
calibrate a camera and a light but not enough to answer "what does a vanilla barrel
look like". This walks the whole shipped corpus -- both texture packs, joined against
the tile definitions so each sprite carries its tileset, category and properties --
and records its measurements.

The result (``reference/corpus.json``) is what the per-category spec is derived from,
and it is what makes it possible to look up the palette an actual vanilla object was
painted with instead of inventing one.

Run with:
    uv run --python 3.12 --with pillow --with numpy python tools/build_corpus.py
"""
from __future__ import annotations

import colorsys
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack
from pzforge.tiledef import TileDefinitions

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media")
OUT = Path(__file__).resolve().parents[1] / "reference"

PACKS = ("Tiles2x.pack", "Tiles2x.floor.pack")
TILEDEFS = ("newtiledefinitions.tiles", "tiledefinitions_erosion.tiles",
            "tiledefinitions_overlays.tiles")

#: Trailing "_01", "_02" ... on a tileset name is a sheet index, not a different thing.
SHEET_SUFFIX = re.compile(r"_\d+$")
#: Colours are bucketed to 5 bits per channel before counting, so a palette entry
#: means "this shade", not "this exact pixel".
PALETTE_SHIFT = 3


def family(tileset: str) -> str:
    return SHEET_SUFFIX.sub("", tileset)


def category(tileset: str) -> str:
    """Coarse grouping: the first token of the tileset name."""
    return tileset.split("_", 1)[0] if "_" in tileset else tileset


def load_tile_index() -> dict[str, dict]:
    """sprite name -> {tileset, properties} for every defined tile."""
    index: dict[str, dict] = {}
    for name in TILEDEFS:
        path = PZ / name
        if not path.exists():
            continue
        for ts in TileDefinitions.read(path).tilesets:
            for i, tile in enumerate(ts.tiles):
                if tile.empty:
                    continue
                index[f"{ts.name}_{i}"] = {"tileset": ts.name, "props": tile.props}
    return index


def sprite_measurements(rgba: np.ndarray) -> dict | None:
    """Tone statistics and a colour histogram for one sprite, vectorised."""
    alpha = rgba[..., 3]
    solid = alpha > 200
    count = int(solid.sum())
    if count < 120:
        return None

    rgb = rgba[..., :3][solid].astype(np.float32) / 255.0
    mx = rgb.max(axis=1)
    mn = rgb.min(axis=1)
    delta = mx - mn
    value = mx
    saturation = np.where(mx > 0, delta / np.maximum(mx, 1e-6), 0.0)

    v = np.sort(value)
    s = np.sort(saturation)

    def q(arr, p):
        return float(arr[min(len(arr) - 1, int(round(p * (len(arr) - 1))))])

    # Hue of the coloured pixels only; near-greys have no meaningful hue.
    coloured = saturation > 0.05
    hue = float("nan")
    if coloured.sum() > 20:
        sub = rgb[coloured]
        hues = np.array([colorsys.rgb_to_hsv(*px)[0] for px in sub[::max(1, len(sub) // 400)]])
        hue = float(np.median(hues) * 360.0)

    quantised = (rgba[..., :3][solid] >> PALETTE_SHIFT) << PALETTE_SHIFT
    keys = (quantised[:, 0].astype(np.int32) << 16 |
            quantised[:, 1].astype(np.int32) << 8 | quantised[:, 2].astype(np.int32))
    uniq, counts = np.unique(keys, return_counts=True)
    order = np.argsort(-counts)[:12]

    return {
        "px": count,
        "value": [round(q(v, 0.25), 4), round(q(v, 0.5), 4), round(q(v, 0.75), 4)],
        "sat": [round(q(s, 0.25), 4), round(q(s, 0.5), 4), round(q(s, 0.75), 4)],
        "hue": None if hue != hue else round(hue, 1),
        "palette": [[int(uniq[i]), int(counts[i])] for i in order],
    }


def main() -> None:
    tiles = load_tile_index()
    print(f"tile definitions: {len(tiles)} named sprites")

    corpus: dict[str, dict] = {}
    for pack_name in PACKS:
        path = PZ / "texturepacks" / pack_name
        if not path.exists():
            continue
        pack = TexturePack.read(path)
        total = sum(len(p.entries) for p in pack.pages)
        print(f"\n{pack_name}: {len(pack.pages)} pages, {total} sprites")
        done = 0
        for page in pack.pages:
            atlas = np.asarray(Image.open(io.BytesIO(page.png)).convert("RGBA"))
            for e in page.entries:
                done += 1
                if done % 4000 == 0:
                    print(f"   {done}/{total}")
                if e.w < 6 or e.h < 6:
                    continue
                crop = atlas[e.y:e.y + e.h, e.x:e.x + e.w]
                stats = sprite_measurements(crop)
                if stats is None:
                    continue
                meta = tiles.get(e.name, {})
                tileset = meta.get("tileset") or e.name.rsplit("_", 1)[0]
                stats.update({
                    "tileset": tileset,
                    "family": family(tileset),
                    "category": category(tileset),
                    "cell": [e.ow, e.oh],
                    "box": [e.ox, e.oy, e.w, e.h],
                    "floor": pack_name.endswith(".floor.pack"),
                })
                if meta.get("props"):
                    keep = {k: v for k, v in meta["props"].items()
                            if k in ("CustomName", "GroupName", "Material", "Facing")}
                    if keep:
                        stats["props"] = keep
                corpus[e.name] = stats

    OUT.mkdir(exist_ok=True)
    path = OUT / "corpus.json"
    path.write_text(json.dumps(corpus, separators=(",", ":")))
    families = Counter(v["family"] for v in corpus.values())
    print(f"\nindexed {len(corpus)} sprites across {len(families)} families")
    print("largest families:")
    for name, n in families.most_common(12):
        print(f"   {name:<44} {n}")
    print(f"\nwrote {path}  ({path.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
