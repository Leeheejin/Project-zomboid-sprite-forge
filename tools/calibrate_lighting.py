"""Solve the rig's key/ambient balance so it reproduces vanilla's face contrast.

Vanilla wall sprites tagged with a Facing give hard targets: S=119.18, E=96.37,
W=76.35, N=63.71 (mean sRGB luminance, measured by tools/analyze_lighting.py).

Method
------
A grey cube is rendered and each visible face measured separately:

* **Face masks** come from dedicated emission renders -- one face white, the rest
  black -- so a face's pixels are identified exactly. Clustering the beauty render
  by luminance does not work: Cycles' per-pixel noise shatters a flat face into
  hundreds of tiny clusters and the masks come out wrong.
* **Light transport is linear**, so one key-only and one ambient-only render predict
  every combination as ``sun * k_face + ambient * a_face``. The strength search then
  runs in plain Python instead of thousands of renders.
* **The azimuth is swept** rather than taken from the closed-form solution. That
  solution assumes pure lambert shading, but Cycles bounces light off the lit faces
  onto the shaded one, lifting E and flattening the S/E contrast.

A cube is used rather than four planes: a plane shades identically from both sides,
so four planes report four identical values regardless of their orientation.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P tools/calibrate_lighting.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

TARGETS = F.VANILLA_TARGETS
TARGET_SE = TARGETS["S"] / TARGETS["E"]
TARGET_NS = TARGETS["N"] / TARGETS["S"]
ALBEDO = 0.5

#: Outward normals of the cube faces we can see from the rig's south-east camera.
VISIBLE_FACES = {"S": (0.0, -1.0, 0.0), "E": (1.0, 0.0, 0.0), "top": (0.0, 0.0, 1.0)}
#: Coarse-to-fine around the azimuth solved analytically from the vanilla wall
#: luminances (28.2 degrees east of south), which the render sweep confirms.
AZIMUTH_SWEEP = (20, 23, 25, 26, 27, 28, 29, 31, 34)


def srgb_to_linear(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def srgb(linear: float) -> float:
    """Linear radiance -> the 0-255 sRGB value the vanilla measurements are in."""
    v = max(0.0, min(1.0, linear))
    encoded = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return encoded * 255.0


def render_to(path: str) -> str:
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def luminances(path: str) -> list[float | None]:
    """Linear luminance per pixel, None where the pixel is not opaque.

    ``Image.pixels`` hands back the file's buffer as-is, so for an 8-bit PNG those
    floats are *already sRGB encoded*. Treating them as linear makes brightness look
    non-linear in light strength -- which is exactly what a superposition check
    catches -- so each channel is decoded before being weighted.
    """
    img = bpy.data.images.load(path, check_existing=False)
    px = list(img.pixels)
    bpy.data.images.remove(img)
    out: list[float | None] = []
    for i in range(0, len(px), 4):
        if px[i + 3] <= 0.95:
            out.append(None)
            continue
        out.append(0.2126 * srgb_to_linear(px[i])
                   + 0.7152 * srgb_to_linear(px[i + 1])
                   + 0.0722 * srgb_to_linear(px[i + 2]))
    return out


def emission(name: str, value: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs[0].default_value = (value, value, value, 1.0)
    emit.inputs[1].default_value = 1.0
    links.new(emit.outputs[0], out.inputs[0])
    return mat


def diffuse(name: str, albedo: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (albedo, albedo, albedo, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    return mat


def build_cube(materials: list) -> bpy.types.Object:
    """A unit cube standing on the tile, one material slot per face."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
    cube = bpy.context.active_object
    for mat in materials:
        cube.data.materials.append(mat)
    for poly in cube.data.polygons:
        n = poly.normal
        best, best_dot = 0, -2.0
        for i, (_face, normal) in enumerate(VISIBLE_FACES.items()):
            dot = sum(a * b for a, b in zip(n, normal))
            if dot > best_dot:
                best, best_dot = i, dot
        # Slot 3 is the catch-all for faces the camera cannot see.
        poly.material_index = best if best_dot > 0.9 else 3
    return cube


def face_masks(cube, tmp: str) -> dict[str, list[int]]:
    """Identify each visible face's pixels with a noise-free emission render."""
    white, black = emission("mask_white", 1.0), emission("mask_black", 0.0)
    masks = {}
    for i, face in enumerate(VISIBLE_FACES):
        for slot_index, slot in enumerate(cube.material_slots):
            slot.material = white if slot_index == i else black
        lum = luminances(render_to(os.path.join(tmp, f"mask_{face}.png")))
        masks[face] = [j for j, v in enumerate(lum) if v is not None and v > 0.5]
    return masks


def mean_of(lum: list[float | None], idxs: list[int]) -> float:
    vals = [lum[i] for i in idxs if lum[i] is not None]
    return sum(vals) / len(vals) if vals else float("nan")


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="pzforge_cal_")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.pz_forge.output_dir = tmp
    F.build_rig(bpy.context)
    scene.cycles.samples = 256
    scene.cycles.use_denoising = False  # a denoiser would bias the face averages

    grey = diffuse("PZ_Calibration", ALBEDO)
    cube = build_cube([grey, grey, grey, grey])

    masks = face_masks(cube, tmp)
    for slot in cube.material_slots:
        slot.material = grey

    expected_top = 128 * 64 // 2
    print("face masks: " + ", ".join(f"{f}={len(m)}px" for f, m in masks.items()))
    print(f"   (the top face is a full tile diamond, so {expected_top}px is correct; "
          f"S and E should be equal)\n")

    sun = bpy.data.objects[F.SUN_NAME]
    background = scene.world.node_tree.nodes["Background"]

    print(f"targets: S/E = {TARGET_SE:.4f}   N/S = {TARGET_NS:.4f}   "
          f"absolute S = {TARGETS['S']:.1f}\n")
    print(f"{'azimuth':>8} {'key S':>8} {'key E':>8} {'kS/kE':>7} "
          f"{'sun':>7} {'ambient':>8} {'S':>6} {'E':>6} {'N':>6} "
          f"{'S/E':>7} {'N/S':>7} {'error':>7}")

    best = None
    for azimuth_deg in AZIMUTH_SWEEP:
        F.LIGHT_AZIMUTH_FROM_SOUTH = math.radians(azimuth_deg)
        sun.rotation_euler = F.sun_rotation()

        sun.data.energy = 1.0
        background.inputs[1].default_value = 0.0
        lum = luminances(render_to(os.path.join(tmp, f"key{azimuth_deg}.png")))
        k = {face: mean_of(lum, idxs) for face, idxs in masks.items()}

        sun.data.energy = 0.0
        background.inputs[1].default_value = 1.0
        lum = luminances(render_to(os.path.join(tmp, f"amb{azimuth_deg}.png")))
        a = {face: mean_of(lum, idxs) for face, idxs in masks.items()}

        # A face turned away from the key receives the ambient term only, and under a
        # uniform world every vertical face receives the same amount of it.
        a_vertical = (a["S"] + a["E"]) / 2

        local = None
        for i in range(1, 201):
            sun_strength = i * 3.0 / 200
            for j in range(1, 201):
                ambient = j * 0.4 / 200
                s_v = srgb(sun_strength * k["S"] + ambient * a_vertical)
                e_v = srgb(sun_strength * k["E"] + ambient * a_vertical)
                n_v = srgb(ambient * a_vertical)
                if s_v <= 0 or e_v <= 0:
                    continue
                err = (abs(s_v / e_v - TARGET_SE) / TARGET_SE
                       + abs(n_v / s_v - TARGET_NS) / TARGET_NS
                       + abs(s_v - TARGETS["S"]) / TARGETS["S"])
                if local is None or err < local["error"]:
                    local = {"azimuth_deg": azimuth_deg,
                             "sun_strength": round(sun_strength, 4),
                             "ambient_strength": round(ambient, 4),
                             "S": round(s_v, 1), "E": round(e_v, 1), "N": round(n_v, 1),
                             "S/E": round(s_v / e_v, 4), "N/S": round(n_v / s_v, 4),
                             "error": round(err, 5),
                             "key_per_unit": {f: round(v, 5) for f, v in k.items()},
                             "ambient_per_unit": {f: round(v, 5) for f, v in a.items()}}

        print(f"{azimuth_deg:8d} {k['S']:8.5f} {k['E']:8.5f} {k['S'] / k['E']:7.3f} "
              f"{local['sun_strength']:7.3f} {local['ambient_strength']:8.4f} "
              f"{local['S']:6.1f} {local['E']:6.1f} {local['N']:6.1f} "
              f"{local['S/E']:7.4f} {local['N/S']:7.4f} {local['error']:7.4f}")
        if best is None or local["error"] < best["error"]:
            best = local

    print(f"\nsolved: azimuth={best['azimuth_deg']} deg east of south, "
          f"sun={best['sun_strength']}, ambient={best['ambient_strength']}")
    print(f"   S={best['S']} (vanilla {TARGETS['S']:.1f})   "
          f"E={best['E']} (vanilla {TARGETS['E']:.1f})   "
          f"N={best['N']} (vanilla {TARGETS['N']:.1f})")

    # --- confirm by rendering at the solved values -------------------------
    F.LIGHT_AZIMUTH_FROM_SOUTH = math.radians(best["azimuth_deg"])
    sun.rotation_euler = F.sun_rotation()
    sun.data.energy = best["sun_strength"]
    background.inputs[1].default_value = best["ambient_strength"]
    lum = luminances(render_to(os.path.join(tmp, "solved.png")))
    got = {face: srgb(mean_of(lum, idxs)) for face, idxs in masks.items()}
    drift = max(abs(got["S"] - best["S"]), abs(got["E"] - best["E"]))
    print(f"\nverification render: S={got['S']:.1f} E={got['E']:.1f} "
          f"S/E={got['S'] / got['E']:.4f}   (drift from prediction {drift:.2f})")
    if drift > 1.5:
        print("   WARNING: prediction and render disagree -- superposition broke down")

    out = ROOT / "reference" / "lighting_calibration.json"
    out.write_text(json.dumps({
        "albedo": ALBEDO,
        "targets": {"S": TARGETS["S"], "E": TARGETS["E"], "N": TARGETS["N"],
                    "S/E": round(TARGET_SE, 4), "N/S": round(TARGET_NS, 4)},
        "face_mask_pixels": {f: len(m) for f, m in masks.items()},
        "solved": best,
        "verified": {f: round(v, 1) for f, v in got.items()},
        "verification_drift": round(drift, 3),
    }, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
