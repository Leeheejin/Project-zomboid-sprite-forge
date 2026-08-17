"""Extract the property sets vanilla actually uses, per tile category.

Guessing tile properties is how custom tiles end up walk-throughable or unscrappable,
so the presets shipped with the tool are derived from how often each property really
occurs in that category. Properties present on most tiles of a category become the
preset's ``core``; the rest are reported as ``common`` so a modder can opt in.

The modal *whole set* is a poor basis -- vanilla furniture alone has 486 distinct
property sets across 710 tiles -- so frequency per property is used instead.

Run with:  python tools/extract_presets.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.tiledef import TileDefinitions

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media")
OUT = Path(__file__).resolve().parents[1] / "reference"

CATEGORIES = {
    "wall": ("walls_",),
    "floor": ("floors_", "carpet"),
    "furniture": ("furniture_",),
    "fence": ("fencing_", "fences_"),
    "door": ("fixtures_doors", "doors_"),
    "window": ("fixtures_windows", "windows_"),
    "appliance": ("appliances_",),
    "vegetation": ("vegetation_", "trees_"),
    "counter": ("counters_", "location_shop"),
}


#: Per-object rather than per-category -- a preset must not bake these in.
PER_OBJECT_KEYS = {"Facing", "CustomName", "GroupName", "SpriteGridPos", "BedType",
                   "Surface", "container", "ContainerCapacity",
                   # references to specific other sprites -- meaningless on a new tile
                   "SnowTile", "BurntTile", "GlassRemovedOffset", "SmashedTileOffset",
                   "OpenTileOffset", "WindowShape"}

#: A property on at least this share of a category's tiles is treated as core.
CORE_THRESHOLD = 0.65


def main() -> None:
    tdefs = TileDefinitions.read(PZ / "newtiledefinitions.tiles")
    totals: collections.Counter = collections.Counter()
    key_count: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    value_count: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter)

    for ts in tdefs.tilesets:
        low = ts.name.lower()
        cat = next((c for c, prefixes in CATEGORIES.items()
                    if any(p in low for p in prefixes)), None)
        if cat is None:
            continue
        for tile in ts.tiles:
            if tile.empty:
                continue
            totals[cat] += 1
            for k, v in tile.props.items():
                if k in PER_OBJECT_KEYS:
                    continue
                key_count[cat][k] += 1
                value_count[(cat, k)][v] += 1

    presets = {}
    for cat in sorted(totals):
        total = totals[cat]
        core, common = {}, []
        for key, n in key_count[cat].most_common():
            share = n / total
            value = value_count[(cat, key)].most_common(1)[0][0]
            if share >= CORE_THRESHOLD:
                core[key] = value
            elif share >= 0.15 and len(common) < 10:
                common.append({"key": key, "value": value, "share": round(share, 3)})
        presets[cat] = {"tiles_sampled": total, "core": core, "common": common}
        if cat == "wall":
            # The 4-sprite wall core set (read off walls_exterior_house_01_0..3):
            # per-sprite roles the frequency stats cannot express. The build
            # assigns these cyclically by sprite index; corner pieces reference
            # their straight walls exactly as vanilla's CornerWestWall/
            # CornerNorthWall entries do.
            presets[cat]["sequence"] = [
                {"WallW": ""},
                {"WallN": ""},
                {"WallNW": "", "CornerWestWall": "{sprite:0}",
                 "CornerNorthWall": "{sprite:1}"},
                {"WallSE": ""},
            ]

        print(f"\n== {cat}  ({total} vanilla tiles) ==")
        print("   core:")
        for k, v in core.items():
            print(f"      {k} = {v!r}    ({key_count[cat][k]/total*100:.0f}%)")
        print("   common (opt in with --prop):")
        for c in common[:6]:
            print(f"      {c['key']}={c['value']!r:<18} {c['share']*100:5.1f}%")

    path = OUT / "tile_presets.json"
    path.write_text(json.dumps(presets, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
