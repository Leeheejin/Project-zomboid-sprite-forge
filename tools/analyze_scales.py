"""At which scale is a recreation missing its contrast?

``value_spread`` is a single number, so it cannot say whether a sprite is missing
per-pixel grain or large tonal patches -- and the two need completely different
fixes. This blurs the sprite progressively and reports the spread that survives at
each scale, which separates them.

A spread that matches at coarse scales but falls short at fine ones means missing
grain. One that falls short everywhere, including heavily blurred, means missing
large-scale variation: panels, dirt patches, tonal blocking.

Run with:
    uv run --python 3.12 --with pillow --with numpy python tools/analyze_scales.py <vanilla> [mine.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pzforge.compare import vanilla_sprite

RADII = (0, 1, 2, 4, 8)


def value_and_mask(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(img.convert("RGBA")).astype(np.float32)
    value = rgba[..., :3].max(axis=2) / 255.0
    mask = rgba[..., 3] > 200
    return value, mask


def box_blur(value: np.ndarray, mask: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a (2r+1) window, counting opaque pixels only."""
    if radius == 0:
        return value
    weighted = np.where(mask, value, 0.0)
    weight = mask.astype(np.float32)
    acc_v = np.zeros_like(weighted)
    acc_w = np.zeros_like(weight)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            acc_v += np.roll(np.roll(weighted, dy, axis=0), dx, axis=1)
            acc_w += np.roll(np.roll(weight, dy, axis=0), dx, axis=1)
    return np.where(acc_w > 0, acc_v / np.maximum(acc_w, 1e-6), value)


def spreads(img: Image.Image) -> dict[int, float]:
    value, mask = value_and_mask(img)
    out = {}
    for radius in RADII:
        blurred = box_blur(value, mask, radius)[mask]
        if blurred.size < 50:
            continue
        out[radius] = float(np.percentile(blurred, 75) - np.percentile(blurred, 25))
    return out


def corpus_profile(sample: int = 320) -> None:
    """Octave profile across many vanilla sprites, so the target is a band not a guess."""
    import io
    import json
    import random

    from pzforge.packfile import TexturePack

    pz = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
              r"\texturepacks\Tiles2x.pack")
    pack = TexturePack.read(pz)
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 40 and e.h > 60]
    items = random.Random(67).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    rows: dict[str, list[float]] = {}
    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        got = spreads(cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h)))
        if len(got) < len(RADII):
            continue
        for a, b in zip(RADII, RADII[1:]):
            rows.setdefault(f"{a}->{b}", []).append(got[a] - got[b])
        rows.setdefault("coarse", []).append(got[RADII[-1]])

    profile = {}
    print(f"octave contributions across {len(rows.get('coarse', []))} vanilla sprites\n")
    print(f"{'octave':<12}{'p25':>9}{'p50':>9}{'p75':>9}")
    for key, values in rows.items():
        arr = np.array(values)
        band = {"p25": round(float(np.percentile(arr, 25)), 4),
                "p50": round(float(np.percentile(arr, 50)), 4),
                "p75": round(float(np.percentile(arr, 75)), 4)}
        profile[key] = band
        print(f"{key:<12}{band['p25']:9.4f}{band['p50']:9.4f}{band['p75']:9.4f}")

    path = ROOT / "reference" / "scale_profile.json"
    path.write_text(json.dumps({"radii": list(RADII), "octaves": profile}, indent=1))
    print(f"\nwrote {path}")


def main() -> None:
    if sys.argv[1] == "--corpus":
        corpus_profile()
        return
    reference = spreads(vanilla_sprite(sys.argv[1]))
    mine = spreads(Image.open(sys.argv[2]).convert("RGBA")) if len(sys.argv) > 2 else None

    print(f"interquartile spread of value, after blurring at each radius\n")
    header = f"{'blur radius':<14}{'vanilla':>9}"
    if mine:
        header += f"{'mine':>9}{'shortfall':>11}"
    print(header)
    for radius in RADII:
        if radius not in reference:
            continue
        row = f"{('none' if radius == 0 else f'{radius} px'):<14}{reference[radius]:9.4f}"
        if mine:
            gap = mine[radius] - reference[radius]
            row += f"{mine[radius]:9.4f}{gap:+11.4f}"
        print(row)

    if mine:
        # What each octave contributes, as spread lost when blurring one step further.
        print(f"\n{'octave':<14}{'vanilla':>9}{'mine':>9}{'shortfall':>11}")
        for a, b in zip(RADII, RADII[1:]):
            va = reference[a] - reference[b]
            ma = mine[a] - mine[b]
            print(f"{f'{a}->{b} px':<14}{va:9.4f}{ma:9.4f}{ma - va:+11.4f}")
        print(f"{'8 px and up':<14}{reference[RADII[-1]]:9.4f}{mine[RADII[-1]]:9.4f}"
              f"{mine[RADII[-1]] - reference[RADII[-1]]:+11.4f}")


if __name__ == "__main__":
    main()
