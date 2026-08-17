"""Compare the tonal histogram of a recreation against its reference.

Percentiles and spreads say a sprite is flat without saying which tones are missing.
This bins both sprites' value channel and prints them side by side, so the answer is
"there are no pixels below 0.25" rather than "the spread is 0.06 too low".

Run with:
    uv run --python 3.12 --with pillow python tools/histogram_diff.py <vanilla> <mine.png>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pzforge.compare import vanilla_sprite

BINS = 16


def histogram(img: Image.Image) -> tuple[list[float], int]:
    counts = [0] * BINS
    total = 0
    for r, g, b, a in img.convert("RGBA").getdata():
        if a < 200:
            continue
        value = max(r, g, b) / 255.0
        counts[min(BINS - 1, int(value * BINS))] += 1
        total += 1
    return [c / total for c in counts] if total else counts, total


def main() -> None:
    reference, ref_total = histogram(vanilla_sprite(sys.argv[1]))
    mine, mine_total = histogram(Image.open(sys.argv[2]).convert("RGBA"))

    print(f"value histogram   vanilla {ref_total} px   mine {mine_total} px\n")
    print(f"{'value':<13}{'vanilla':>9}{'mine':>8}   {'vanilla':<22}{'mine'}")
    for i in range(BINS):
        lo, hi = i / BINS, (i + 1) / BINS
        bar_v = "#" * round(reference[i] * 100)
        bar_m = "#" * round(mine[i] * 100)
        print(f"{lo:.2f}-{hi:.2f}  {reference[i] * 100:8.1f}%{mine[i] * 100:7.1f}%   "
              f"{bar_v:<22}{bar_m}")

    print("\nlargest deficits (vanilla share minus mine):")
    gaps = sorted(((reference[i] - mine[i], i) for i in range(BINS)), reverse=True)
    for gap, i in gaps[:4]:
        print(f"   {i / BINS:.2f}-{(i + 1) / BINS:.2f}  {gap * 100:+.1f} points")
    print("largest excesses:")
    for gap, i in gaps[-3:]:
        print(f"   {i / BINS:.2f}-{(i + 1) / BINS:.2f}  {gap * 100:+.1f} points")


if __name__ == "__main__":
    main()
