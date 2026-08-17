"""Per-archetype painting recipes, measured from the vanilla corpus.

The style passes long matched whole-sprite statistics, and the finishing pass knew
*where* to treat elements but its amplitudes were calibrated, not measured. What was
still missing numerically is the painter's decision grammar: how many tones an
element is blocked in with, how thick a drawn line is and how dark against the face
it crosses, how strongly a small fitting drifts from its lit corner to its shaded
one. This module measures exactly that, per element archetype, from the game's own
object sprites.

An *archetype* is a shape class of painted region, found by segmenting each sprite
(median-cut quantisation + connected components, the same reading `refsheet` gives a
human) and classifying every region:

* ``line``   -- thin and long: grooves, seams, panel borders, outlines
* ``fitting``-- small compact regions: bolts, notches, handles, bungs, latches
* ``face``   -- everything large: body panels, lids, doors

Per archetype the corpus yields medians for tone economy (`tones_90`: how many
0.04-wide value bins cover 90% of the region), internal spread, lit-to-shaded drift
across the region, line thickness and darkness, and the bright-accent energy beside
lines. ``tools/extract_recipes.py`` writes the result to
``reference/element_recipes.json``; :func:`load` serves it to the style passes with
the pre-measurement calibration as fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .refsheet import segment

RECIPES_PATH = (Path(__file__).resolve().parents[1] / "reference"
                / "element_recipes.json")

#: Value-bin width for tone counting. Coarser than 8-bit steps on purpose: blocking
#: tones are what a painter lays in, not what dithering leaves behind.
TONE_BIN = 0.04
#: A region is a line when it is at most this thick and at least this long.
LINE_MAX_THICKNESS = 2.6
LINE_MIN_LENGTH = 8
#: Regions at or below this many pixels count as fittings, above as faces.
FITTING_MAX_PX = 400

#: Pre-measurement calibration, kept as the fallback so builds work without the
#: extraction having run. Values mirror the finishing pass's original constants.
FALLBACK = {
    "sampled_sprites": 0,
    "line": {"thickness_px": 1.8, "value_ratio_vs_body": 0.55,
             "accent_amount": 0.040},
    "fitting": {"tones_90": 3, "spread": 0.10, "grad_x": 0.06, "grad_y": 0.06,
                "value_ratio_vs_body": 0.75},
    "face": {"tones_90": 6, "spread": 0.12, "grad_x": 0.04, "grad_y": 0.02},
    "window_tones": {"window_px": 12, "median": 3, "p25": 2, "p75": 5},
}

#: Caveat pinned by the first extraction run: region-level ``tones_90`` and the
#: grad fields are near-tautological, because segmentation splits by tone -- a
#: region is one tone cluster by construction. The numbers that carry real
#: information are the line statistics (thickness, darkness, accent energy) and
#: ``window_tones``, which is measured without any segmentation at all.


def _value(p) -> float:
    return max(p[0], p[1], p[2]) / 255.0


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    return vals[len(vals) // 2]


def tones_90(values: list[float]) -> int:
    """How many TONE_BIN-wide bins cover 90% of the pixels: the blocking economy."""
    if not values:
        return 0
    bins: dict[int, int] = {}
    for v in values:
        b = int(v / TONE_BIN)
        bins[b] = bins.get(b, 0) + 1
    counts = sorted(bins.values(), reverse=True)
    need = 0.9 * len(values)
    got, n = 0, 0
    for c in counts:
        got += c
        n += 1
        if got >= need:
            break
    return n


def local_tones(img: Image.Image, window: int = 12, step: int = 6) -> list[int]:
    """Tone economy of every mostly-opaque window: the sprite's local cleanliness.

    Region-level tone counts are tautological under tone-based segmentation, so
    the economy is measured window-wise instead: vanilla objects run a median of
    3 tones per 12 px window where a styled render runs 4+ -- that one extra tone
    per window *is* the measured difference between clean and busy.
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = list(img.getdata())
    out = []
    for y0 in range(0, h - window, step):
        for x0 in range(0, w - window, step):
            vals = []
            for y in range(y0, y0 + window):
                base = y * w
                for x in range(x0, x0 + window):
                    p = px[base + x]
                    if p[3] > 200:
                        vals.append(_value(p))
            if len(vals) >= window * window * 0.8:
                out.append(tones_90(vals))
    return out


def measure_sprite(img: Image.Image, colours: int = 6) -> dict | None:
    """One sprite's regions, classified and measured. Returns per-archetype lists."""
    img = img.convert("RGBA")
    w, h = img.size
    px = list(img.getdata())
    regions = segment(img, colours=colours)
    if not regions:
        return None
    body_v = _value_mean(px, regions[0].pixels)
    if body_v < 1e-3:
        return None

    out = {"line": [], "fitting": [], "face": []}
    in_region = {}
    for r in regions:
        for i in r.pixels:
            in_region[i] = r.index

    for r in regions:
        xs = [i % w for i in r.pixels]
        ys = [i // w for i in r.pixels]
        bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        length = max(bw, bh)
        thickness = r.size / length
        values = [_value(px[i]) for i in r.pixels]
        v_mean = sum(values) / len(values)
        values.sort()
        spread = values[int(0.9 * (len(values) - 1))] - values[int(0.1 * (len(values) - 1))]

        entry = {
            "tones": tones_90(values),
            "spread": spread,
            "ratio": v_mean / body_v,
        }

        if thickness <= LINE_MAX_THICKNESS and length >= LINE_MIN_LENGTH:
            entry["thickness"] = thickness
            entry["accent"] = _accent_energy(px, r.pixels, in_region, r.index, w, h)
            out["line"].append(entry)
            continue

        # lit-to-shaded drift across the region, as a fraction of its own mean
        mid_x = (min(xs) + max(xs)) / 2
        mid_y = (min(ys) + max(ys)) / 2
        lx = [v for i, v in zip(r.pixels, (_value(px[i]) for i in r.pixels))
              if i % w < mid_x]
        rx = [_value(px[i]) for i in r.pixels if i % w > mid_x]
        ty = [_value(px[i]) for i in r.pixels if i // w < mid_y]
        by = [_value(px[i]) for i in r.pixels if i // w > mid_y]
        if lx and rx:
            entry["grad_x"] = (sum(lx) / len(lx) - sum(rx) / len(rx)) / v_mean
        if ty and by:
            entry["grad_y"] = (sum(ty) / len(ty) - sum(by) / len(by)) / v_mean

        out["fitting" if r.size <= FITTING_MAX_PX else "face"].append(entry)
    out["windows"] = local_tones(img)
    return out


def _value_mean(px, pixels) -> float:
    return sum(_value(px[i]) for i in pixels) / max(len(pixels), 1)


def _accent_energy(px, pixels, in_region, own_index, w, h) -> float | None:
    """Bright-accent energy beside a line: how far its border neighbours sit above
    the median border level. This is the painted 1 px lip that gives linework its
    relief; measuring its median magnitude anchors the finishing amplitudes."""
    neighbours = []
    own = set(pixels)
    for i in own:
        x, y = i % w, i // w
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            xx, yy = x + dx, y + dy
            if not (0 <= xx < w and 0 <= yy < h):
                continue
            j = yy * w + xx
            if j in own or px[j][3] < 200:
                continue
            neighbours.append(_value(px[j]))
    if len(neighbours) < 8:
        return None
    neighbours.sort()
    base = neighbours[len(neighbours) // 2]
    bright = [v - base for v in neighbours if v > base]
    return _median(bright)


def aggregate(per_sprite: list[dict]) -> dict:
    """Median every archetype statistic across the sampled sprites."""

    def collect(kind: str, key: str) -> list[float]:
        out = []
        for s in per_sprite:
            for entry in s[kind]:
                v = entry.get(key)
                if v is not None:
                    out.append(v)
        return out

    recipes = {"sampled_sprites": len(per_sprite)}
    recipes["line"] = {
        "thickness_px": _median(collect("line", "thickness")),
        "value_ratio_vs_body": _median(collect("line", "ratio")),
        "accent_amount": _median(collect("line", "accent")),
        "regions": len(collect("line", "ratio")),
    }
    for kind in ("fitting", "face"):
        recipes[kind] = {
            "tones_90": round(_median(collect(kind, "tones")) or 0),
            "spread": _median(collect(kind, "spread")),
            "grad_x": _median(collect(kind, "grad_x")),
            "grad_y": _median(collect(kind, "grad_y")),
            "regions": len(collect(kind, "tones")),
        }
    recipes["fitting"]["value_ratio_vs_body"] = _median(collect("fitting", "ratio"))

    windows = sorted(t for s in per_sprite for t in s.get("windows", []))
    if windows:
        recipes["window_tones"] = {
            "window_px": 12,
            "median": windows[len(windows) // 2],
            "p25": windows[len(windows) // 4],
            "p75": windows[3 * len(windows) // 4],
            "windows": len(windows),
        }
    return recipes


def load(path: Path | None = None) -> dict:
    path = path or RECIPES_PATH
    if path.exists():
        measured = json.loads(path.read_text())
        # Backfill anything a partial extraction left out.
        out = json.loads(json.dumps(FALLBACK))
        for kind, entry in measured.items():
            if isinstance(entry, dict):
                out.setdefault(kind, {}).update(
                    {k: v for k, v in entry.items() if v is not None})
            else:
                out[kind] = entry
        return out
    return FALLBACK
