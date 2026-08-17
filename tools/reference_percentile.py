"""Where does a given vanilla sprite sit inside vanilla's own distributions?

Before spending another iteration chasing a reference, it is worth knowing whether
that reference is typical. A sprite in the 95th percentile of contrast cannot be
matched by a rig calibrated to the median without pulling every other sprite out of
range -- at which point the honest answer is to say so rather than keep tuning.

Run with:
    uv run --python 3.12 --with pillow python tools/reference_percentile.py <sprite> [mine.png]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pzforge.check import percentile_of
from pzforge.compare import edge_softness, light_balance, vanilla_sprite
from pzforge.style import measure

REFERENCE = ROOT / "reference"


def load(name: str) -> dict:
    path = REFERENCE / name
    return json.loads(path.read_text()) if path.exists() else {}


def stats_for(img: Image.Image) -> dict:
    base = measure(img) or {}
    base["left_over_right"] = light_balance(img).get("left_over_right", float("nan"))
    base["soft_edge_share"] = edge_softness(img)
    return base


def main() -> None:
    sprite_stats = load("sprite_stats.json")
    detail_stats = load("detail_stats.json")
    distributions = {
        "median_value": sprite_stats.get("median_value"),
        "value_spread": sprite_stats.get("value_spread"),
        "median_saturation": sprite_stats.get("median_saturation"),
        "left_over_right": sprite_stats.get("left_over_right"),
    }

    reference = vanilla_sprite(sys.argv[1])
    ref = stats_for(reference)
    mine = stats_for(Image.open(sys.argv[2]).convert("RGBA")) if len(sys.argv) > 2 else None

    print(f"how typical is {sys.argv[1]} for a vanilla sprite?\n")
    header = f"{'statistic':<20}{'reference':>10}{'pctile':>8}"
    if mine:
        header += f"{'mine':>10}{'pctile':>8}"
    print(header)
    for key, anchors in distributions.items():
        if not anchors or key not in ref:
            continue
        row = f"{key:<20}{ref[key]:10.3f}{percentile_of(ref[key], anchors):7.0f}%"
        if mine:
            row += f"{mine[key]:10.3f}{percentile_of(mine[key], anchors):7.0f}%"
        print(row)

    if detail_stats.get("detail_energy"):
        print(f"\n(detail energy band p10-p90: "
              f"{detail_stats['detail_energy']['p10']:.4f}-"
              f"{detail_stats['detail_energy']['p90']:.4f})")
    print(f"\nsoft edge share: reference {ref['soft_edge_share'] * 100:.1f}%"
          + (f", mine {mine['soft_edge_share'] * 100:.1f}%" if mine else "")
          + "   (vanilla median 8.5%)")


if __name__ == "__main__":
    main()
