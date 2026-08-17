"""Separate paint from light, restyle the light, recompose -- the painter's order.

Every earlier pass corrected a *finished picture*: the beauty render arrives with
paint and light already multiplied together, so treatments could only push pixel
statistics around without knowing what was paint and what was illumination. That is
why element colours drifted toward averages and the light never read as a light
source.

The rig now renders a light pass beside every beauty cell (``*_L.png``: the whole
subject in white diffuse, so the frame holds the rig's light field alone -- key,
ambient, bounce, occlusion, and the measured cool-key/warm-shadow chroma). With
paint and light separated, the build can do what the vanilla painter does:

1. **Recover the paint.** ``albedo = beauty / light`` per channel in linear space.
   Specular sheen divides into the paint, which is right for this style -- vanilla
   paints its highlights.
2. **Flatten the paint per element.** Paint is flat; a painter mixes a colour and
   fills the shape with it. Each element's albedo is pulled toward its own few
   paint tones, keeping the light untouched.
3. **Quantise the light per element.** The painter renders light in blocked steps,
   not gradients. The light field's luminance is clustered into the element's
   measured tone budget while its *chromaticity is kept*, so the cool key and warm
   shadow tint every step the way the light source dictates.
4. **Recompose**: ``paint x stylised light``, back to sRGB.

The result is an image whose every colour is "this paint under this much of this
light" -- never an average -- with texture and accents left to the later passes.
"""

from __future__ import annotations

from PIL import Image

from .finish import _element_tone_budget

#: How far each element's albedo is pulled toward its paint tones.
PAINT_FLATTEN = 0.75
#: Paint tones per element: painters block a fitting in one or two paints, a face
#: in a few. Light steps come on top of these, so they stay below the element's
#: full window budget.
PAINT_TONES_FITTING = 2
PAINT_TONES_FACE = 3
FITTING_MAX_PX = 400


def _linear(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _srgb(v: float) -> float:
    if v <= 0.0031308:
        return 12.92 * v
    return 1.055 * (v ** (1 / 2.4)) - 0.055


_L8 = [_linear(i / 255.0) for i in range(256)]


def _kmeans1d(values: list[float], k: int, iters: int = 8) -> list[float]:
    svals = sorted(values)
    centres = [svals[int((j + 0.5) / k * (len(svals) - 1))] for j in range(k)]
    for _ in range(iters):
        sums = [0.0] * k
        ns = [0] * k
        for v in values:
            best = min(range(k), key=lambda j: abs(v - centres[j]))
            sums[best] += v
            ns[best] += 1
        new = [sums[j] / ns[j] if ns[j] else centres[j] for j in range(k)]
        if all(abs(a - b) < 1e-4 for a, b in zip(new, centres)):
            return new
        centres = new
    return centres


def relight(beauty: Image.Image, light: Image.Image,
            labels: list[str | None], recipes: dict,
            paint_flatten: float = PAINT_FLATTEN,
            light_steps: float = 1.0) -> Image.Image:
    """Recompose the sprite as flat paint under stepped light, per element.

    ``paint_flatten`` is how far albedo is pulled toward its element's paint
    tones; ``light_steps`` is how far the light luminance is pulled toward its
    quantised steps. Either at 0 disables that half.
    """
    beauty = beauty.convert("RGBA")
    light = light.convert("RGBA")
    if light.size != beauty.size:
        raise ValueError(f"pass mismatch: beauty {beauty.size}, light {light.size}")
    w, h = beauty.size
    if len(labels) != w * h:
        raise ValueError(f"label map is {len(labels)} px, image is {w * h}")

    bpx = list(beauty.getdata())
    lpx = list(light.getdata())
    wt = recipes.get("window_tones", {})
    window_median = wt.get("median", 3)
    window_px = wt.get("window_px", 12)

    # -- separate ----------------------------------------------------------
    n = w * h
    albedo = [None] * n          # linear rgb paint
    lum = [None] * n             # linear light luminance
    chroma = [None] * n          # light chromaticity, preserved through styling
    for i in range(n):
        if bpx[i][3] == 0 or labels[i] is None:
            continue
        lr, lg, lb = (_L8[lpx[i][0]], _L8[lpx[i][1]], _L8[lpx[i][2]])
        y = 0.2126 * lr + 0.7152 * lg + 0.0722 * lb
        if y < 1e-4:
            continue
        albedo[i] = (min(4.0, _L8[bpx[i][0]] / max(lr, 1e-4)),
                     min(4.0, _L8[bpx[i][1]] / max(lg, 1e-4)),
                     min(4.0, _L8[bpx[i][2]] / max(lb, 1e-4)))
        lum[i] = y
        chroma[i] = (lr / y, lg / y, lb / y)

    members: dict[str, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab is not None and albedo[i] is not None:
            members.setdefault(lab, []).append(i)

    # -- restyle per element ------------------------------------------------
    paint = list(albedo)
    styled_lum = list(lum)
    for lab, idxs in members.items():
        # paint tones: cluster albedo luminance, snap rgb toward cluster mean rgb
        if paint_flatten > 0:
            k = (PAINT_TONES_FITTING if len(idxs) <= FITTING_MAX_PX
                 else PAINT_TONES_FACE)
            alums = [0.2126 * albedo[i][0] + 0.7152 * albedo[i][1]
                     + 0.0722 * albedo[i][2] for i in idxs]
            if max(alums) - min(alums) > 1e-4:
                centres = _kmeans1d(alums, k)
                sums = {j: [0.0, 0.0, 0.0, 0] for j in range(len(centres))}
                assign = []
                for i, al in zip(idxs, alums):
                    j = min(range(len(centres)), key=lambda c: abs(al - centres[c]))
                    assign.append(j)
                    s = sums[j]
                    s[0] += albedo[i][0]
                    s[1] += albedo[i][1]
                    s[2] += albedo[i][2]
                    s[3] += 1
                tone_rgb = {j: ((s[0] / s[3], s[1] / s[3], s[2] / s[3])
                            if s[3] else None) for j, s in sums.items()}
                for i, j in zip(idxs, assign):
                    target = tone_rgb[j]
                    if target is None:
                        continue
                    a = albedo[i]
                    paint[i] = tuple(c + (t - c) * paint_flatten
                                     for c, t in zip(a, target))
        # light steps: cluster the light luminance into the element's budget
        if light_steps > 0:
            budget = _element_tone_budget(len(idxs), window_median, window_px)
            lums = [lum[i] for i in idxs]
            if max(lums) - min(lums) > 1e-4:
                centres = _kmeans1d(lums, budget)
                for i, y in zip(idxs, lums):
                    target = min(centres, key=lambda c: abs(y - c))
                    styled_lum[i] = y + (target - y) * light_steps

    # -- recompose ----------------------------------------------------------
    out = []
    for i in range(n):
        if albedo[i] is None:
            out.append(bpx[i])
            continue
        cy = styled_lum[i]
        cr, cg, cb = chroma[i]
        pr, pg, pb = paint[i]
        out.append((
            min(255, round(_srgb(min(1.0, pr * cr * cy)) * 255)),
            min(255, round(_srgb(min(1.0, pg * cg * cy)) * 255)),
            min(255, round(_srgb(min(1.0, pb * cb * cy)) * 255)),
            bpx[i][3]))
    result = Image.new("RGBA", (w, h))
    result.putdata(out)
    return result
