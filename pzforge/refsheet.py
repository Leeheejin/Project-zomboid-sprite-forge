"""Decompose a reference sprite into the features a modeller has to rebuild.

Every structural mistake in the recreation work so far -- fat bright rings where the
original has thin dark grooves, a missing rim, ribs run along the wrong axis -- was
caught by zooming the reference and reading it by eye. Nothing in the toolchain did
that reading. This module does:

* **regions** -- the sprite's paint, segmented. Median-cut quantisation over the
  opaque pixels, then connected components, gives the distinct painted areas: body,
  lid, dark linework, straps. Each region reports its share, its mean rendered
  colour, and that colour inverted through the rig's lighting response for each
  candidate face -- the material list, measured instead of eyeballed.
* **edges** -- where the painter drew lines: pixels whose 3x3 value range exceeds
  the drawn-edge threshold, overlaid on the sprite so groove positions, seams and
  panel borders can be read off directly.
* the zoomed sprite itself, because no summary replaces looking.

Output is one PNG sheet plus a printed table.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .spec import albedo_for
from .style import PAINT_EDGE_T

#: Ignore fragments smaller than this: they are antialiasing, not painted regions.
MIN_REGION_PX = 24


@dataclass
class Region:
    index: int
    pixels: list[int]
    mean_rgb: tuple[int, int, int]

    @property
    def size(self) -> int:
        return len(self.pixels)

    @property
    def hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(*self.mean_rgb)


def _opaque_mask(img: Image.Image) -> list[bool]:
    return [p[3] > 200 for p in img.getdata()]


def segment(img: Image.Image, colours: int = 6) -> list[Region]:
    """Painted regions: quantise to ``colours`` clusters, then split spatially."""
    img = img.convert("RGBA")
    w, h = img.size
    opaque = _opaque_mask(img)
    rgba = list(img.getdata())

    # Fill transparent pixels with the sprite's own mean so they cannot claim a
    # quantisation cluster of their own.
    ins = [p[:3] for i, p in enumerate(rgba) if opaque[i]]
    if not ins:
        return []
    mean = tuple(sum(c[k] for c in ins) // len(ins) for k in range(3))
    flat = Image.new("RGB", (w, h), mean)
    flat.putdata([p[:3] if opaque[i] else mean for i, p in enumerate(rgba)])
    quantised = flat.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=0)
    labels = list(quantised.getdata())

    seen = [False] * (w * h)
    regions: list[Region] = []
    for start in range(w * h):
        if seen[start] or not opaque[start]:
            continue
        label = labels[start]
        queue = deque([start])
        seen[start] = True
        pixels = []
        while queue:
            i = queue.popleft()
            pixels.append(i)
            x, y = i % w, i // w
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    j = yy * w + xx
                    if not seen[j] and opaque[j] and labels[j] == label:
                        seen[j] = True
                        queue.append(j)
        if len(pixels) < MIN_REGION_PX:
            continue
        rs = sum(rgba[i][0] for i in pixels) // len(pixels)
        gs = sum(rgba[i][1] for i in pixels) // len(pixels)
        bs = sum(rgba[i][2] for i in pixels) // len(pixels)
        regions.append(Region(len(regions), pixels, (rs, gs, bs)))

    regions.sort(key=lambda r: -r.size)
    for k, region in enumerate(regions):
        region.index = k
    return regions


def edge_mask(img: Image.Image) -> list[bool]:
    """Pixels sitting on a drawn line: 3x3 value range above the edge threshold."""
    img = img.convert("RGBA")
    w, h = img.size
    px = list(img.getdata())
    value = [max(p[:3]) / 255.0 if p[3] > 200 else None for p in px]
    out = [False] * (w * h)
    for i, v in enumerate(value):
        if v is None:
            continue
        x, y = i % w, i // w
        lo = hi = v
        for dy in (-1, 0, 1):
            yy = y + dy
            if not 0 <= yy < h:
                continue
            for dx in (-1, 0, 1):
                xx = x + dx
                if 0 <= xx < w:
                    n = value[yy * w + xx]
                    if n is not None:
                        lo = min(lo, n)
                        hi = max(hi, n)
        out[i] = (hi - lo) > PAINT_EDGE_T
    return out


def _panel(img: Image.Image, scale: int) -> Image.Image:
    return img.resize((img.width * scale, img.height * scale),
                      Image.Resampling.NEAREST)


def build_sheet(sprite: Image.Image, regions: list[Region], edges: list[bool],
                scale: int = 4, max_regions: int = 8) -> Image.Image:
    sprite = sprite.convert("RGBA")
    w, h = sprite.size
    px = list(sprite.getdata())

    # Panel 2: drawn lines in red over a dimmed sprite.
    edge_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    edge_img.putdata([
        (232, 64, 64, 255) if edges[i]
        else ((p[0] // 3 + 20, p[1] // 3 + 20, p[2] // 3 + 20, 255) if p[3] > 0
              else (0, 0, 0, 0))
        for i, p in enumerate(px)])

    # Panel 3: regions painted with their own mean colour.
    region_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rpx = [(40, 40, 44, 255) if p[3] > 0 else (0, 0, 0, 0) for p in px]
    for region in regions[:max_regions]:
        for i in region.pixels:
            rpx[i] = (*region.mean_rgb, 255)
    region_img.putdata(rpx)

    panels = [_panel(p, scale) for p in (sprite, edge_img, region_img)]
    pad = 8
    legend_h = 16 * min(len(regions), max_regions) + 16
    sheet = Image.new("RGBA",
                      (sum(p.width for p in panels) + pad * 4,
                       panels[0].height + legend_h + pad * 3),
                      (24, 26, 30, 255))
    x = pad
    for p in panels:
        sheet.alpha_composite(p, (x, pad))
        x += p.width + pad

    draw = ImageDraw.Draw(sheet)
    y = panels[0].height + pad * 2
    total = sum(r.size for r in regions) or 1
    for region in regions[:max_regions]:
        draw.rectangle([pad, y + 2, pad + 12, y + 14], fill=(*region.mean_rgb, 255))
        draw.text((pad + 18, y + 2),
                  f"R{region.index}  {region.size}px "
                  f"({region.size / total * 100:.0f}%)  {region.hex}",
                  fill=(220, 220, 224, 255))
        y += 16
    return sheet


def report(regions: list[Region], edges: list[bool], opaque_count: int,
           max_regions: int = 8) -> str:
    lines = [f"{'region':<8}{'px':>7}{'share':>8}  {'rendered':<9} "
             f"{'albedo if facing S':<23}{'if E':<23}{'if top'}"]
    total = sum(r.size for r in regions) or 1
    for region in regions[:max_regions]:
        albedos = {face: albedo_for(region.mean_rgb, face) for face in ("S", "E", "top")}
        cells = "".join(
            f"({a[0]:.2f},{a[1]:.2f},{a[2]:.2f})".ljust(23)
            for a in (albedos["S"], albedos["E"], albedos["top"]))
        lines.append(f"R{region.index:<7}{region.size:>7}"
                     f"{region.size / total * 100:>7.1f}%  {region.hex:<9} {cells}")
    edge_share = sum(edges) / max(opaque_count, 1)
    lines.append(f"\ndrawn-line pixels: {sum(edges)} ({edge_share * 100:.1f}% of opaque)"
                 " -- red in the middle panel; grooves, seams and panel borders")
    lines.append("albedo columns assume the region lies on that face; pick the column"
                 " matching where the region sits on the model")
    return "\n".join(lines)
