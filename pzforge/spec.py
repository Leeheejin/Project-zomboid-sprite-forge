"""The build-to spec, derived from every vanilla sprite rather than a sample.

Two things a modeller needs that aggregate style scores cannot give:

* **Size.** How wide and how tall is a vanilla object of this kind, in tiles.
* **Colour.** What the thing is actually painted. A palette entry is a *rendered*
  colour though -- albedo times lighting -- so feeding it straight into a material
  makes the model too bright. :func:`albedo_for` inverts the rig's own measured
  response so a measured colour can be turned into the base colour that reproduces it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "reference"
SPEC_PATH = REFERENCE / "spec.json"
CALIBRATION_PATH = REFERENCE / "lighting_calibration.json"

#: Fallback matching the shipped calibration, measured at albedo 0.5.
FALLBACK_RESPONSE = {
    "albedo": 0.5, "sun_strength": 1.32, "ambient_strength": 0.102,
    "key_per_unit": {"S": 0.1016, "E": 0.04987, "top": 0.113},
    "ambient_per_unit": {"S": 0.49897, "E": 0.49894, "top": 0.49897},
}

FACES = ("S", "E", "top")


def srgb_to_linear(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def linear_to_srgb(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def load_spec(path: Path | None = None) -> dict:
    path = path or SPEC_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- run tools/build_corpus.py then tools/derive_spec.py")
    return json.loads(path.read_text())


def load_response(path: Path | None = None) -> dict:
    path = path or CALIBRATION_PATH
    if not path.exists():
        return FALLBACK_RESPONSE
    data = json.loads(path.read_text())
    solved = data.get("solved", {})
    return {"albedo": data.get("albedo", 0.5),
            "sun_strength": solved.get("sun_strength", 1.32),
            "ambient_strength": solved.get("ambient_strength", 0.102),
            "key_per_unit": solved.get("key_per_unit", FALLBACK_RESPONSE["key_per_unit"]),
            "ambient_per_unit": solved.get("ambient_per_unit",
                                           FALLBACK_RESPONSE["ambient_per_unit"])}


def face_gain(face: str, response: dict | None = None) -> float:
    """Linear radiance a surface of albedo 1.0 shows on this face under the rig."""
    r = response or load_response()
    key = r["key_per_unit"].get(face, r["key_per_unit"]["S"])
    ambient = r["ambient_per_unit"].get(face, r["ambient_per_unit"]["S"])
    lit = r["sun_strength"] * key + r["ambient_strength"] * ambient
    return lit / r["albedo"]


def albedo_for(rgb: tuple[int, int, int], face: str = "S",
               response: dict | None = None) -> tuple[float, float, float]:
    """Base colour that renders as ``rgb`` on the given face.

    Values above 1.0 mean the target simply cannot be reached on that face -- the
    colour is brighter than a perfectly white surface would render there.
    """
    gain = face_gain(face, response)
    return tuple(min(1.0, srgb_to_linear(c / 255.0) / gain) for c in rgb)


def rendered_from_albedo(albedo: tuple[float, float, float], face: str = "S",
                         response: dict | None = None) -> tuple[int, int, int]:
    gain = face_gain(face, response)
    return tuple(round(linear_to_srgb(c * gain) * 255) for c in albedo)


@dataclass
class Entry:
    key: str
    scope: str
    data: dict

    @property
    def palette(self) -> list[dict]:
        return self.data.get("palette", [])

    def size_summary(self) -> str | None:
        if "width_tiles" not in self.data:
            return None
        w, h = self.data["width_tiles"], self.data["height_tiles"]
        return (f"{w['p50']:.3f} tiles wide (p10-p90 {w['p10']:.3f}-{w['p90']:.3f}), "
                f"{h['p50']:.3f} tall (p10-p90 {h['p10']:.3f}-{h['p90']:.3f})")


CORPUS_PATH = REFERENCE / "corpus.json"

#: A palette entry has to cover at least this much of the sprite to be treated as its
#: paint rather than an incidental shadow or highlight pixel.
PAINT_MIN_SHARE = 0.05


def paint_colour(palette: list[dict], face: str = "S",
                 response: dict | None = None
                 ) -> tuple[tuple[int, int, int], tuple[float, float, float]] | None:
    """The surface's paint, and the base colour that reproduces it on ``face``.

    A palette is a histogram of *rendered* colours, so one paint shows up several
    times -- brightest on the lit face, darker on the others. Reading the whole
    spread as a range of albedos counts the lighting twice and produces a model far
    too dark. The brightest shade that still covers a meaningful part of the sprite
    is the one lying on the lit face, so that is the one to invert.
    """
    candidates = [c for c in palette if c["share"] >= PAINT_MIN_SHARE] or palette[:1]
    if not candidates:
        return None
    brightest = max(candidates, key=lambda c: max(c["rgb"]))
    rgb = tuple(brightest["rgb"])
    return rgb, albedo_for(rgb, face, response)


def sprite_entry(name: str, path: Path | None = None) -> Entry:
    """One specific vanilla sprite, for when a recreation copies exactly that tile."""
    path = path or CORPUS_PATH
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run tools/build_corpus.py")
    corpus = json.loads(path.read_text())
    raw = corpus.get(name)
    if raw is None:
        raise KeyError(f"{name!r} is not in the corpus")

    total = sum(count for _packed, count in raw["palette"]) or 1
    ox, oy, w, h = raw["box"]
    data = {
        "sprites": 1,
        "median_value": {"p10": raw["value"][0], "p50": raw["value"][1],
                         "p90": raw["value"][2]},
        "value_spread": {"p10": 0.0, "p50": round(raw["value"][2] - raw["value"][0], 4),
                         "p90": 0.0},
        "median_saturation": {"p10": raw["sat"][0], "p50": raw["sat"][1],
                              "p90": raw["sat"][2]},
        "palette": [{"hex": f"#{packed:06x}",
                     "rgb": [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255],
                     "share": round(count / total, 4)}
                    for packed, count in raw["palette"]],
    }
    if raw.get("cell") == [128, 256] and not raw.get("floor"):
        width = w / 90.50966799187808
        height = ((256 - oy) - 32) / 78.38367176906169
        for key, value in (("width_tiles", width), ("height_tiles", height)):
            data[key] = {"p10": round(value, 4), "p50": round(value, 4),
                         "p90": round(value, 4)}
    return Entry(name, "sprite", data)


def lookup(spec: dict, query: str) -> list[Entry]:
    """Find spec entries by object name, family or category, case-insensitively."""
    needle = query.lower()
    exact, partial = [], []
    for scope in ("objects", "families", "categories"):
        for key, data in spec.get(scope, {}).items():
            low = key.lower()
            if low == needle:
                exact.append(Entry(key, scope, data))
            elif needle in low:
                partial.append(Entry(key, scope, data))
    return exact or partial
