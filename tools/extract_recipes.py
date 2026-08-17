"""Measure per-archetype painting recipes from the shipped object sprites.

Samples full-size object sprites (128x256 cells, non-floor) from the families that
actually contain drawn objects -- crates, drums, furniture, fixtures, machines --
segments each one the way `pzforge refsheet` does, classifies every painted region
as line / fitting / face, and aggregates the medians into
``reference/element_recipes.json``. The finishing and tone-blocking passes read
that file instead of calibrated constants.

Run with:
    uv run --python 3.12 --with pillow python tools/extract_recipes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pzforge import recipe
from pzforge.preview import DEFAULT_GAME_MEDIA, SpriteSource

#: Families whose sprites are drawn objects rather than architecture or terrain.
FAMILY_PREFIXES = (
    "crafted", "industry", "constructedobjects", "carpentry", "camping",
    "fixtures", "furniture", "appliances", "shipping", "trash", "recreational",
)
#: Cap on sampled sprites; the medians are stable well below this.
MAX_SPRITES = 400


def main() -> None:
    corpus = json.loads((ROOT / "reference" / "corpus.json").read_text())
    names = sorted(
        name for name, meta in corpus.items()
        if meta["cell"] == [128, 256] and not meta["floor"]
        and 1500 <= meta["px"] <= 15000
        and meta["family"].startswith(FAMILY_PREFIXES))
    if len(names) > MAX_SPRITES:
        step = len(names) / MAX_SPRITES
        names = [names[int(k * step)] for k in range(MAX_SPRITES)]

    source = SpriteSource.from_packs([
        DEFAULT_GAME_MEDIA / "texturepacks" / "Tiles2x.pack",
    ])

    measured = []
    for k, name in enumerate(names):
        sprite = source.get(name)
        if sprite is None:
            continue
        if sprite.size != (128, 256):
            cell = sprite.crop((0, 0, 128, 256)) if sprite.size >= (128, 256) else None
            if cell is None:
                continue
            sprite = cell
        stats = recipe.measure_sprite(sprite)
        if stats is not None:
            measured.append(stats)
        if (k + 1) % 50 == 0:
            print(f"  {k + 1}/{len(names)} sprites read")

    recipes = recipe.aggregate(measured)
    out = ROOT / "reference" / "element_recipes.json"
    out.write_text(json.dumps(recipes, indent=1))
    print(f"\nwrote {out}")
    print(json.dumps(recipes, indent=1))


if __name__ == "__main__":
    main()
