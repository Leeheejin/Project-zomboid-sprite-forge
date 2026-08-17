"""How is a vanilla sprite's *interior* actually painted?

Every measurement so far described distributions -- brightness, contrast, spatial
frequency. None described technique. A path-traced render and a hand-painted sprite
can share every one of those statistics and still read completely differently,
because painting has structure the numbers above ignore:

* **flat fills** -- a painter blocks a face in with one tone, so large runs of pixels
  are *identical*, not merely similar;
* **crisp interior edges** -- faces meet at drawn lines, one or two pixels wide;
* **few distinct levels** -- shading happens in steps (banding), not smooth ramps.

A renderer produces the exact opposite signature: almost no perfectly flat runs, no
drawn lines, and continuous gradients everywhere.

This tool measures that signature. For every opaque pixel whose full 3x3
neighbourhood is opaque, take the local value range r = max - min over the window:

* ``flat``  r < 0.02   (a blocked-in fill)
* ``edge``  r > 0.15   (a painted boundary)
* ``mid``   otherwise  (smooth shading -- the renderer's tell)

plus ``levels_90``: how many 1/256 value bins cover 90% of the sprite's pixels
(posterisation), and ``anisotropy``: mean |dv/dx| over mean |dv/dy| (stroke
direction).

Run with:
    uv run --python 3.12 --with pillow --with numpy python tools/analyze_painting.py --corpus
    uv run --python 3.12 --with pillow --with numpy python tools/analyze_painting.py <name-or-png> ...
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pzforge.packfile import TexturePack

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")
OUT = ROOT / "reference"

FLAT_T = 0.02
EDGE_T = 0.15


def paint_stats(img: Image.Image) -> dict | None:
    rgba = np.asarray(img.convert("RGBA")).astype(np.float32)
    value = rgba[..., :3].max(axis=2) / 255.0
    opaque = rgba[..., 3] > 200

    # Interior = pixels whose whole 3x3 neighbourhood is opaque, so the silhouette
    # edge cannot masquerade as painted structure.
    interior = opaque.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            interior &= np.roll(np.roll(opaque, dy, axis=0), dx, axis=1)
    interior[0, :] = interior[-1, :] = False
    interior[:, 0] = interior[:, -1] = False
    n = int(interior.sum())
    if n < 400:
        return None

    # Local range over the 3x3 window.
    stack = [np.roll(np.roll(value, dy, axis=0), dx, axis=1)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    local = np.stack(stack)
    rng = local.max(axis=0) - local.min(axis=0)
    r = rng[interior]

    # Posterisation: 1/256 bins covering 90% of interior pixels.
    bins = np.bincount((value[interior] * 255).astype(np.int32), minlength=256)
    order = np.sort(bins)[::-1]
    cum = np.cumsum(order)
    levels_90 = int(np.searchsorted(cum, 0.90 * n) + 1)

    dx_e = np.abs(np.diff(value, axis=1))[interior[:, 1:]]
    dy_e = np.abs(np.diff(value, axis=0))[interior[1:, :]]

    return {
        "interior_px": n,
        "flat_share": float((r < FLAT_T).mean()),
        "mid_share": float(((r >= FLAT_T) & (r <= EDGE_T)).mean()),
        "edge_share": float((r > EDGE_T).mean()),
        "levels_90": levels_90,
        "anisotropy": float(dx_e.mean() / max(dy_e.mean(), 1e-6)),
    }


def vanilla_sprite(name: str) -> Image.Image:
    for pack_name in ("Tiles2x.pack", "Tiles2x.floor.pack"):
        pack = TexturePack.read(PZ / pack_name)
        for page in pack.pages:
            for e in page.entries:
                if e.name != name:
                    continue
                atlas = Image.open(io.BytesIO(page.png)).convert("RGBA")
                cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
                cell.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
                return cell
    raise SystemExit(f"{name!r} not found")


def corpus(sample: int = 320) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 40 and e.h > 60]
    items = random.Random(71).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    rows: dict[str, list[float]] = {}
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        stats = paint_stats(cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h)))
        if stats is None:
            continue
        for key, v in stats.items():
            if key != "interior_px":
                rows.setdefault(key, []).append(v)

    profile = {}
    count = len(rows.get("flat_share", []))
    print(f"painting signature across {count} vanilla sprites\n")
    print(f"{'statistic':<14}{'p10':>9}{'p25':>9}{'p50':>9}{'p75':>9}{'p90':>9}")
    for key, values in rows.items():
        arr = np.array(values)
        band = {f"p{q}": round(float(np.percentile(arr, q)), 4)
                for q in (10, 25, 50, 75, 90)}
        profile[key] = band
        print(f"{key:<14}" + "".join(f"{band[f'p{q}']:9.3f}" for q in (10, 25, 50, 75, 90)))

    path = OUT / "painting_profile.json"
    path.write_text(json.dumps({"sprites": count, "flat_t": FLAT_T, "edge_t": EDGE_T,
                                "bands": profile}, indent=1))
    print(f"\nwrote {path}")


def main() -> None:
    if sys.argv[1] == "--corpus":
        corpus()
        return
    print(f"{'target':<44}{'flat':>7}{'mid':>7}{'edge':>7}{'lv90':>6}{'aniso':>7}")
    for arg in sys.argv[1:]:
        img = (Image.open(arg).convert("RGBA") if arg.endswith(".png")
               else vanilla_sprite(arg))
        s = paint_stats(img)
        label = Path(arg).name if arg.endswith(".png") else arg
        print(f"{label:<44}{s['flat_share']:7.3f}{s['mid_share']:7.3f}"
              f"{s['edge_share']:7.3f}{s['levels_90']:6d}{s['anisotropy']:7.2f}")


if __name__ == "__main__":
    main()
