"""Measure where each face lands on the toon ramp's input axis, under EEVEE.

The ramp's *output* levels come from the measured vanilla face luminances; its
*input* stop positions have to separate the faces as EEVEE's Shader-to-RGB
actually sees them under this rig. So: render a calibration cube whose material
captures raw shading (white diffuse -> Shader to RGB -> luminance -> emission,
no ramp), once facing the camera and once rotated 180 degrees, sample the flat
face levels, and print the midpoints to paste into TOON_STOPS.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P tools/calibrate_toon.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "toon_calibration"


def capture_material():
    mat = bpy.data.materials.new("PZ_ToonCal")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    diffuse.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    diffuse.inputs["Roughness"].default_value = 0.5
    capture = nodes.new("ShaderNodeShaderToRGB")
    lum = nodes.new("ShaderNodeRGBToBW")
    emission = nodes.new("ShaderNodeEmission")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(diffuse.outputs["BSDF"], capture.inputs["Shader"])
    links.new(capture.outputs["Color"], lum.inputs["Color"])
    links.new(lum.outputs["Val"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    return mat


def linear(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def face_levels(path: Path) -> list[tuple[float, int]]:
    """Distinct flat luminance clusters in the render, brightest first."""
    import struct
    import zlib

    data = path.read_bytes()
    # minimal PNG read via Blender's own loader instead: load as image
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    px = list(img.pixels)  # RGBA floats, sRGB-decoded? pixels are linear floats
    clusters: dict[int, int] = {}
    for i in range(0, len(px), 4):
        if px[i + 3] < 0.9:
            continue
        # Image.pixels returns the file decoded to linear for sRGB images.
        key = round(px[i] * 200)
        clusters[key] = clusters.get(key, 0) + 1
    bpy.data.images.remove(img)
    total = sum(clusters.values())
    out = [(k / 200.0, n) for k, n in sorted(clusters.items(), reverse=True)
           if n > total * 0.02]
    return out


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    F.register()
    scene = bpy.context.scene
    props = scene.pz_forge
    props.sheet_name = "tooncal"
    props.output_dir = str(OUT)
    props.show_guide = False
    props.toon_shading = True

    F.build_rig(bpy.context)
    F.apply_render_settings(bpy.context)

    bpy.ops.mesh.primitive_cube_add(size=0.8, location=(0, 0, 0.4))
    cube = bpy.context.active_object
    cube.data.materials.append(capture_material())
    cube.parent = bpy.data.objects[F.SUBJECT_NAME]

    subject = bpy.data.objects[F.SUBJECT_NAME]
    OUT.mkdir(parents=True, exist_ok=True)
    for rot, label in ((0, "SE"), (180, "NW")):
        subject.rotation_euler = (0.0, 0.0, math.radians(rot))
        scene.render.filepath = str(OUT / f"cal_{label}.png")
        bpy.ops.render.render(write_still=True)
        print(f"\n== rotation {rot} ({label} faces + top) ==")
        for level, count in face_levels(OUT / f"cal_{label}.png"):
            print(f"  captured luminance {level:.4f}  ({count} px)")

    # sun-off render: ambient-only capture, the input level W/N/shadow share
    sun = bpy.data.objects.get(F.SUN_NAME)
    if sun is not None:
        sun.data.energy = 0.0
    subject.rotation_euler = (0.0, 0.0, 0.0)
    scene.render.filepath = str(OUT / "cal_ambient.png")
    bpy.ops.render.render(write_still=True)
    print("\n== sun off (ambient only) ==")
    for level, count in face_levels(OUT / "cal_ambient.png"):
        print(f"  captured luminance {level:.4f}  ({count} px)")


if __name__ == "__main__":
    main()
