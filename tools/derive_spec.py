"""Turn the indexed corpus into a spec a modeller can build to.

Aggregate bands answer "is this sprite plausibly a PZ tile". They do not answer "what
colour is a PZ metal drum", which is the question that actually decides whether a
recreation looks right -- and until now those colours were invented.

For every family, and for every named object, this derives:

* the tonal band its sprites occupy;
* the **palette** its sprites are actually painted with, as measured shares;
* how big it is, in tiles, so a model can be built to size rather than eyeballed.

Run with:
    uv run --python 3.12 --with pillow python tools/derive_spec.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REFERENCE = ROOT / "reference"
CELL_W, CELL_H = 128, 256
PX_PER_M = 78.38367176906169
#: A horizontal circle of diameter d spans d * this many pixels across the screen.
PX_PER_M_HORIZONTAL = 90.50966799187808
#: The tile centre sits this many pixels above the bottom of the cell.
FLOOR_ROW = 32

MIN_SPRITES = 6
PALETTE_SIZE = 10


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))]


def band(values: list[float]) -> dict:
    return {"p10": round(quantile(values, 0.10), 4),
            "p50": round(quantile(values, 0.50), 4),
            "p90": round(quantile(values, 0.90), 4)}


def dimensions(entry: dict) -> dict | None:
    """Footprint width and height above the floor, in tiles, from the trim box."""
    if entry.get("floor") or entry["cell"] != [CELL_W, CELL_H]:
        return None
    ox, oy, w, h = entry["box"]
    top_above_floor = (CELL_H - oy) - FLOOR_ROW
    return {"width_tiles": w / PX_PER_M_HORIZONTAL,
            "height_tiles": top_above_floor / PX_PER_M}


def summarise(entries: list[dict]) -> dict:
    palette: Counter = Counter()
    for e in entries:
        for packed, count in e["palette"]:
            palette[packed] += count
    total = sum(palette.values()) or 1

    hues = [e["hue"] for e in entries if e.get("hue") is not None]
    dims = [d for d in (dimensions(e) for e in entries) if d]

    spec = {
        "sprites": len(entries),
        "median_value": band([e["value"][1] for e in entries]),
        "value_spread": band([e["value"][2] - e["value"][0] for e in entries]),
        "median_saturation": band([e["sat"][1] for e in entries]),
        "palette": [{"hex": f"#{packed:06x}",
                     "rgb": [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255],
                     "share": round(count / total, 4)}
                    for packed, count in palette.most_common(PALETTE_SIZE)],
    }
    if hues:
        spec["hue"] = band(hues)
    if dims:
        spec["width_tiles"] = band([d["width_tiles"] for d in dims])
        spec["height_tiles"] = band([d["height_tiles"] for d in dims])
    return spec


def main() -> None:
    corpus_path = REFERENCE / "corpus.json"
    if not corpus_path.exists():
        raise SystemExit("run tools/build_corpus.py first")
    corpus = json.loads(corpus_path.read_text())

    by_family: dict[str, list[dict]] = defaultdict(list)
    by_category: dict[str, list[dict]] = defaultdict(list)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for entry in corpus.values():
        by_family[entry["family"]].append(entry)
        by_category[entry["category"]].append(entry)
        name = (entry.get("props") or {}).get("CustomName")
        if name:
            group = (entry.get("props") or {}).get("GroupName", "")
            by_name[f"{group} {name}".strip()].append(entry)

    spec = {
        "source": {"sprites": len(corpus), "cell": [CELL_W, CELL_H],
                   "px_per_metre_vertical": PX_PER_M,
                   "px_per_metre_horizontal": PX_PER_M_HORIZONTAL},
        "families": {k: summarise(v) for k, v in by_family.items()
                     if len(v) >= MIN_SPRITES},
        "categories": {k: summarise(v) for k, v in by_category.items()
                       if len(v) >= MIN_SPRITES},
        "objects": {k: summarise(v) for k, v in by_name.items() if len(v) >= 2},
    }

    path = REFERENCE / "spec.json"
    path.write_text(json.dumps(spec, indent=1))
    print(f"families: {len(spec['families'])}  categories: {len(spec['categories'])}  "
          f"named objects: {len(spec['objects'])}")

    for label in ("Metal Drum", "Blacksmith Anvil"):
        if label in spec["objects"]:
            s = spec["objects"][label]
            print(f"\n== {label} ({s['sprites']} sprites) ==")
            print(f"   value {s['median_value']['p50']:.3f}  "
                  f"spread {s['value_spread']['p50']:.3f}  "
                  f"sat {s['median_saturation']['p50']:.3f}")
            if "width_tiles" in s:
                print(f"   width {s['width_tiles']['p50']:.3f} tiles   "
                      f"height {s['height_tiles']['p50']:.3f} tiles")
            print("   palette:")
            for c in s["palette"][:8]:
                print(f"      {c['hex']}  rgb{tuple(c['rgb'])}  {c['share'] * 100:5.1f}%")
    print(f"\nwrote {path}  ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
