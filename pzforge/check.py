"""Score a rendered cell against the range vanilla sprites actually occupy.

The point is to catch a style problem before it ships, without needing a vanilla
sprite of the same object to compare against. Each statistic is placed as a
percentile within the vanilla distribution measured over ~480 sprites, so the
feedback is "your contrast sits at the 30th percentile of vanilla art" rather than
an arbitrary pass or fail.

Being *outside* the p10-p90 band is what deserves attention; sitting anywhere inside
it means the sprite would not stand out on a vanilla street.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .style import load_profile, measure

#: Statistics that have a vanilla band to compare against, and how to read them.
TRACKED = {
    "median_value": "overall brightness",
    "value_spread": "internal contrast",
    "median_saturation": "colour intensity",
}

ANCHORS = ("p10", "p25", "p50", "p75", "p90")


@dataclass
class Score:
    statistic: str
    label: str
    value: float
    percentile: float
    band: tuple[float, float]

    @property
    def inside(self) -> bool:
        return self.band[0] <= self.value <= self.band[1]

    @property
    def verdict(self) -> str:
        if self.inside:
            return "ok"
        return "below vanilla" if self.value < self.band[0] else "above vanilla"


def percentile_of(value: float, anchors: dict[str, float]) -> float:
    """Where ``value`` falls in a distribution given only its percentile anchors."""
    points = [(int(k[1:]), anchors[k]) for k in ANCHORS if k in anchors]
    points.sort(key=lambda p: p[1])
    if value <= points[0][1]:
        return float(points[0][0])
    if value >= points[-1][1]:
        return float(points[-1][0])
    for (p_lo, v_lo), (p_hi, v_hi) in zip(points, points[1:]):
        if v_lo <= value <= v_hi:
            span = v_hi - v_lo
            t = 0.0 if span < 1e-9 else (value - v_lo) / span
            return p_lo + t * (p_hi - p_lo)
    return 50.0


def score(img: Image.Image, profile: dict | None = None) -> list[Score]:
    profile = profile or load_profile()
    stats = measure(img)
    if stats is None:
        return []
    out = []
    for key, label in TRACKED.items():
        anchors = profile.get(key)
        if not anchors:
            continue
        value = stats[key]
        out.append(Score(key, label, value, percentile_of(value, anchors),
                         (anchors["p10"], anchors["p90"])))
    return out


def render_report(name: str, scores: list[Score]) -> str:
    lines = [f"{name}"]
    for s in scores:
        bar_pos = int(round(s.percentile / 100 * 20))
        bar = "".join("|" if i == bar_pos else
                      ("-" if 2 <= i <= 18 else " ") for i in range(21))
        lines.append(f"   {s.label:<18} {s.value:6.3f}  p{s.percentile:<4.0f} "
                     f"[{bar}]  {s.verdict}")
    return "\n".join(lines)
