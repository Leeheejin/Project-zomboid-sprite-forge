"""Recreate the vanilla cork floor (floors_interior_tilesandwood_01_6).

A third reference, and the one that exercises the *floor* path rather than the object
path: the rig shifts the frame one pixel left for floor tiles and not for objects, and
the style pass skips the grounding curve, because a floor sprite lives entirely inside
the rows that curve darkens.

The tile is four quadrants of slightly different tan over a fine grain. Quadrant
colours come from the sprite's own palette, inverted through the rig's *top* face
response since a floor faces the sky:

    pzforge spec floors_interior_tilesandwood_01_6 --sprite --face top

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/wood_floor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "wood_floor_cells"
TEXTURE_PATH = ROOT / "build" / "wood_floor_surface.png"

#: Top-face albedos for the palette's four dominant shades, in the order the sprite
#: lays them out: darker at the near and far quadrants, lighter at the sides.
QUADRANTS = {
    (-1, -1): (0.615, 0.346, 0.195),   # #886850, 21.2% of the sprite
    (1, -1): (0.785, 0.469, 0.244),    # #987858, 17.1%
    (-1, 1): (0.697, 0.469, 0.244),    # #907858, 12.3%
    (1, 1): (0.785, 0.540, 0.244),     # #988058, 17.5%
}


def surface_texture() -> Path:
    from pzforge.texture import SurfaceSpec, write_surface_map

    # The reference's internal spread is only 0.051, so the grain is fine and shallow:
    # small octaves, no vertical bias, and a soft curve rather than hard patches.
    spec = SurfaceSpec(octaves=[(48, 1.00), (24, 0.70), (12, 0.45), (6, 0.28)],
                       vertical_stretch=1.0, contrast=1.0, seed=41)
    return write_surface_map(TEXTURE_PATH, 512, 512, spec)


def quadrant_material(name: str, colour) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.75
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.06

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(TEXTURE_PATH), check_existing=True)
    tex.image.colorspace_settings.name = "Non-Color"
    tex.extension = "REPEAT"

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[0].color = (*[c * 0.86 for c in colour], 1.0)
    ramp.color_ramp.elements[1].color = (*[min(1.0, c * 1.10) for c in colour], 1.0)
    links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def build_floor() -> list[bpy.types.Object]:
    parts = []
    for (sx, sy), colour in QUADRANTS.items():
        bpy.ops.mesh.primitive_plane_add(size=0.5, location=(sx * 0.25, sy * 0.25, 0.0))
        obj = bpy.context.active_object
        obj.name = f"floor_{sx}_{sy}"
        obj.data.materials.append(
            quadrant_material(f"floor_mat_{sx}_{sy}", colour))
        parts.append(obj)
    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    surface_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgewoodfloor_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "1"
    props.show_guide = False
    # The two settings that make this a floor rather than an object.
    props.alignment = "FLOOR"
    props.ground_occlusion = False

    F.build_rig(bpy.context)
    scene.cycles.samples = 256
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_floor():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
