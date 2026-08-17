"""Row-by-row and column-by-column diff of a recreation against its reference.

Aggregate scores hide *where* a sprite is wrong. This prints, for every scanline, how
far the silhouette edges are off and how far the mean luminance is off, so the fix can
be aimed instead of guessed.

Run with:
    uv run --python 3.12 --with pillow python tools/profile_diff.py <vanilla> <mine.png>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.compare import vanilla_sprite


def scan(img: Image.Image, axis: str):
    """Per-row (or per-column) first/last opaque index and mean luminance."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    n = h if axis == "row" else w
    m = w if axis == "row" else h
    out = []
    for i in range(n):
        lo = hi = None
        total = count = 0.0
        for j in range(m):
            x, y = (j, i) if axis == "row" else (i, j)
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            lo = j if lo is None else lo
            hi = j
            total += 0.2126 * r + 0.7152 * g + 0.0722 * b
            count += 1
        out.append((lo, hi, total / count if count else None, int(count)))
    return out


def show(label: str, a: list, b: list, start: int, end: int, step: int) -> None:
    print(f"\n== {label} ==")
    print(f"{'idx':>4} | {'van lo..hi':>12} {'mine lo..hi':>12} {'d_lo':>5} {'d_hi':>5} "
          f"| {'van lum':>8} {'mine lum':>9} {'delta':>7} | {'van n':>6} {'mine n':>6}")
    worst_lum = []
    for i in range(start, end, step):
        va, vb, vl, vn = a[i]
        ma, mb, ml, mn = b[i]
        if vl is None and ml is None:
            continue
        d_lo = "" if va is None or ma is None else f"{ma - va:+d}"
        d_hi = "" if vb is None or mb is None else f"{mb - vb:+d}"
        d_lum = "" if vl is None or ml is None else f"{ml - vl:+.1f}"
        if vl is not None and ml is not None:
            worst_lum.append((abs(ml - vl), i, ml - vl))
        print(f"{i:>4} | {str(va) + '..' + str(vb):>12} {str(ma) + '..' + str(mb):>12} "
              f"{d_lo:>5} {d_hi:>5} | "
              f"{('%.1f' % vl) if vl else '-':>8} {('%.1f' % ml) if ml else '-':>9} "
              f"{d_lum:>7} | {vn:>6} {mn:>6}")
    if worst_lum:
        worst_lum.sort(reverse=True)
        print(f"   largest luminance deltas: " +
              ", ".join(f"{label[:3]} {i}: {d:+.0f}" for _, i, d in worst_lum[:6]))


def main() -> None:
    vanilla = vanilla_sprite(sys.argv[1])
    mine = Image.open(sys.argv[2]).convert("RGBA")

    vb, mb = vanilla.getbbox(), mine.getbbox()
    print(f"vanilla box {vb}  mine box {mb}")
    print(f"box delta (l,t,r,b) {tuple(m - v for v, m in zip(vb, mb))}")

    rows_v, rows_m = scan(vanilla, "row"), scan(mine, "row")
    cols_v, cols_m = scan(vanilla, "col"), scan(mine, "col")

    top = min(vb[1], mb[1])
    bottom = max(vb[3], mb[3])
    show("rows (top to bottom)", rows_v, rows_m, top, bottom, 4)

    left = min(vb[0], mb[0])
    right = max(vb[2], mb[2])
    show("columns (left to right)", cols_v, cols_m, left, right, 4)

    # Total opaque area per side, a blunt check on whether the shape is too fat.
    def area(rows):
        return sum(r[3] for r in rows)
    print(f"\nopaque pixels: vanilla {area(rows_v)}  mine {area(rows_m)}  "
          f"({area(rows_m) / area(rows_v) * 100 - 100:+.1f}%)")


if __name__ == "__main__":
    main()
