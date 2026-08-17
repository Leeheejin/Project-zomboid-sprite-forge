"""Measure the colour of PZ's key light and ambient, instead of guessing them.

Within one sprite the albedo is roughly constant, so the chromaticity difference
between its brightest and darkest pixels is caused by the lighting, not the paint.
Taking that ratio per sprite and then the median across hundreds of sprites cancels
out what albedo variation remains.

A ratio above 1 in a channel means the lit side carries more of it than the shaded
side -- i.e. the key light is warmer or cooler than the ambient by that much.

Run with:
    uv run --python 3.12 --with pillow python tools/analyze_light_colour.py
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


def srgb_to_linear(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else float("nan")


def chromaticity(pixels: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Mean linear RGB normalised so the three channels sum to 3."""
    n = len(pixels)
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    total = (r + g + b) / 3
    return (r / total, g / total, b / total) if total > 1e-6 else (1.0, 1.0, 1.0)


def main(sample: int = 400) -> None:
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    items = [(p, e) for p in pack.pages for e in p.entries
             if (e.ow, e.oh) == (128, 256) and e.w > 40 and e.h > 60]
    items = random.Random(23).sample(items, min(sample, len(items)))

    cache: dict[int, Image.Image] = {}
    bright_chroma: list[tuple[float, float, float]] = []
    dark_chroma: list[tuple[float, float, float]] = []
    ratios: list[tuple[float, float, float]] = []

    for page, e in items:
        if id(page) not in cache:
            cache[id(page)] = Image.open(io.BytesIO(page.png)).convert("RGBA")
        crop = cache[id(page)].crop((e.x, e.y, e.x + e.w, e.y + e.h))

        pixels = []
        for r, g, b, a in crop.getdata():
            if a < 200:
                continue
            lin = (srgb_to_linear(r / 255), srgb_to_linear(g / 255), srgb_to_linear(b / 255))
            lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
            pixels.append((lum, lin))
        if len(pixels) < 500:
            continue
        pixels.sort(key=lambda p: p[0])
        cut = max(1, len(pixels) // 4)
        dark = [p[1] for p in pixels[:cut]]
        bright = [p[1] for p in pixels[-cut:]]
        # Skip near-black or blown regions, where quantisation dominates the hue.
        if pixels[cut][0] < 0.004 or pixels[-cut][0] > 0.95:
            continue

        cb, cd = chromaticity(bright), chromaticity(dark)
        bright_chroma.append(cb)
        dark_chroma.append(cd)
        ratios.append(tuple(b / d if d > 1e-6 else 1.0 for b, d in zip(cb, cd)))

    def summarise(label: str, rows: list[tuple[float, float, float]]) -> list[float]:
        values = [round(median([row[i] for row in rows]), 4) for i in range(3)]
        print(f"  {label:<28} R={values[0]:.4f}  G={values[1]:.4f}  B={values[2]:.4f}")
        return values

    print(f"analysed {len(ratios)} vanilla sprites\n")
    print("normalised chromaticity (R+G+B = 3):")
    bright = summarise("lit quartile", bright_chroma)
    dark = summarise("shaded quartile", dark_chroma)
    print()
    ratio = summarise("lit / shaded", ratios)

    warmer = "warmer (key is warm, ambient cool)" if ratio[0] > ratio[2] else \
             "cooler (key is cool, ambient warm)"
    print(f"\n  -> the lit side is {warmer}")
    print(f"     red/blue ratio on the lit side  : {bright[0] / bright[2]:.4f}")
    print(f"     red/blue ratio on the shaded side: {dark[0] / dark[2]:.4f}")

    result = {"sprites": len(ratios), "lit_chromaticity": bright,
              "shaded_chromaticity": dark, "lit_over_shaded": ratio}
    path = OUT / "light_colour.json"
    path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
