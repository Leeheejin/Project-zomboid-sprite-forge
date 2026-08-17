"""Is vanilla tile art antialiased, or hard-edged?

Determines whether the rig should render with antialiasing or threshold the alpha
to match. Run with:
    uv run --python 3.12 --with pillow python tools/analyze_alpha.py
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


def survey(pack_name: str, sample: int = 300) -> dict:
    pack = TexturePack.read(PZ / pack_name)
    items = [(p, e) for p in pack.pages for e in p.entries if (e.ow, e.oh) == (128, 256)]
    items = random.Random(3).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    binary = 0
    partial_share = []
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        crop = cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h))
        alphas = [p[3] for p in crop.getdata()]
        nonzero = [a for a in alphas if a]
        if not nonzero:
            continue
        partial = sum(1 for a in nonzero if a < 250)
        share = partial / len(nonzero)
        partial_share.append(share)
        if share < 0.01:
            binary += 1

    partial_share.sort()
    n = len(partial_share)
    return {
        "pack": pack_name,
        "sprites": n,
        "fully_hard_edged": binary,
        "hard_edged_share": round(binary / n, 3) if n else 0,
        "partial_alpha_median": round(partial_share[n // 2], 4) if n else 0,
        "partial_alpha_p90": round(partial_share[int(n * 0.9)], 4) if n else 0,
    }


if __name__ == "__main__":
    results = [survey("Tiles2x.floor.pack"), survey("Tiles2x.pack")]
    for r in results:
        print(f"\n== {r['pack']} ({r['sprites']} sprites sampled) ==")
        print(f"   sprites with no soft edge at all : {r['fully_hard_edged']} "
              f"({r['hard_edged_share']*100:.0f}%)")
        print(f"   median share of edge pixels      : {r['partial_alpha_median']*100:.1f}%")
        print(f"   p90 share of edge pixels         : {r['partial_alpha_p90']*100:.1f}%")
    (OUT / "alpha_survey.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT / 'alpha_survey.json'}")
