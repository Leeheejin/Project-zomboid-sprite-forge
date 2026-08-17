"""HomeBrewing's moonshine still, built on the PZ Sprite Forge rig.

Form language copied from vanilla furniture rather than from a product render:
vanilla builds objects out of FLAT PLANES with hard edges, so every face reads as one
near-uniform colour block, and it carries detail in GEOMETRY (planks, posts, rails)
instead of in surface textures. Hence low-segment prisms, flat shading everywhere and
plain colours - no procedural wood grain or brickwork, which at 128x256 only turn into
stripes. Composition still follows the reference: stone furnace, copper boiler, arched
vapour pipe, thump barrel, catch jug, inside a single tile footprint.

Run:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b -P examples/hb_still.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "hb_still_cells"


def mat(name: str, colour, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*colour, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.05
    return m


# albedo roughly doubled against the rig's calibrated key/ambient (1.38 / 0.18)
COPPER = mat("hb_copper", (0.95, 0.345, 0.105), rough=0.95)
COPPER_LIGHT = mat("hb_copper_light", (1.00, 0.450, 0.135), rough=0.92)
WOOD = mat("hb_wood", (0.430, 0.318, 0.235), rough=0.95)
WOOD_DARK = mat("hb_wood_dark", (0.250, 0.175, 0.120), rough=0.95)
STONE = mat("hb_stone", (0.340, 0.312, 0.283), rough=0.97)
STONE_DARK = mat("hb_stone_dark", (0.215, 0.196, 0.178), rough=0.97)
IRON = mat("hb_iron", (0.115, 0.108, 0.100), rough=0.9)
TIN = mat("hb_tin", (0.62, 0.630, 0.640), rough=0.9)
HATCH = mat("hb_hatch", (0.075, 0.062, 0.052), rough=0.98)
FIRE = bpy.data.materials.new("hb_fire")
FIRE.use_nodes = True
_fb = FIRE.node_tree.nodes["Principled BSDF"]
_fb.inputs["Base Color"].default_value = (0.9, 0.35, 0.05, 1)
_fb.inputs["Emission Color"].default_value = (1.0, 0.45, 0.08, 1)
_fb.inputs["Emission Strength"].default_value = 2.5


def prism(name, r, depth, loc, material, sides=10, rot_z=0.0):
    """Low-segment prism, flat shaded: each facet becomes its own colour block."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=r, depth=depth, location=loc)
    o = bpy.context.object
    o.name = name
    o.rotation_euler = (0, 0, rot_z)
    o.data.materials.append(material)
    bpy.ops.object.shade_flat()
    return o


def box(name, centre, size, material, rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    o = bpy.context.object
    o.name = name
    o.scale = size
    o.rotation_euler = (0, 0, rot_z)
    o.data.materials.append(material)
    bpy.ops.object.shade_flat()
    return o


def ring(name, major, minor, loc, material, seg=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc,
                                     major_segments=seg, minor_segments=4)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_flat()
    return o


def build_still():
    parts = []
    bx, by = -0.14, -0.04          # boiler centre
    kx, ky = 0.28, 0.20            # barrel centre

    # --- stone furnace: an octagonal block, plus a darker plinth course ---
    parts.append(prism("hb_plinth", 0.315, 0.09, (bx, by, 0.045), STONE_DARK, sides=8,
                       rot_z=math.radians(22)))
    parts.append(prism("hb_furnace", 0.295, 0.24, (bx, by, 0.21), STONE, sides=8,
                       rot_z=math.radians(22)))
    parts.append(box("hb_mouth", (bx + 0.17, by - 0.20, 0.16), (0.13, 0.09, 0.10), IRON,
                     rot_z=math.radians(-8)))
    parts.append(box("hb_fire", (bx + 0.19, by - 0.22, 0.15), (0.09, 0.06, 0.06), FIRE,
                     rot_z=math.radians(-8)))

    # --- copper boiler: decagonal barrel, hard-edged like vanilla's planked forms ---
    parts.append(prism("hb_boiler", 0.235, 0.70, (bx, by, 0.68), COPPER, sides=10))
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.235, radius2=0.085,
                                    depth=0.16, location=(bx, by, 1.11))
    shoulder = bpy.context.object
    shoulder.name = "hb_shoulder"
    shoulder.data.materials.append(COPPER)
    bpy.ops.object.shade_flat()
    parts.append(shoulder)
    parts.append(prism("hb_neck", 0.085, 0.10, (bx, by, 1.24), COPPER_LIGHT, sides=8))
    parts.append(prism("hb_cap", 0.105, 0.045, (bx, by, 1.30), COPPER_LIGHT, sides=8))
    # a raised band, built as geometry the way vanilla builds rails
    parts.append(prism("hb_boiler_band", 0.245, 0.045, (bx, by, 0.86), COPPER_LIGHT, sides=10))

    # dark hatch with a bright rim
    parts.append(prism("hb_hatch", 0.070, 0.03, (bx + 0.10, by - 0.20, 0.74), HATCH, sides=8))
    parts.append(prism("hb_hatch_rim", 0.085, 0.015, (bx + 0.10, by - 0.20, 0.735), COPPER_LIGHT,
                       sides=8))

    # --- thump barrel: 10 staves as facets, iron hoops as thin rings ---
    parts.append(prism("hb_barrel", 0.205, 0.48, (kx, ky, 0.24), WOOD, sides=10,
                       rot_z=math.radians(8)))
    for z in (0.06, 0.24, 0.42):
        parts.append(ring("hb_hoop_%.2f" % z, 0.209, 0.011, (kx, ky, z), IRON, seg=10))
    parts.append(prism("hb_barrel_lid", 0.198, 0.035, (kx, ky, 0.495), WOOD_DARK, sides=10,
                       rot_z=math.radians(8)))

    # --- arched vapour pipe: octagonal tube, flat shaded ---
    curve = bpy.data.curves.new("hb_pipe", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.030
    curve.bevel_resolution = 1          # 8-sided tube instead of a smooth cylinder
    curve.resolution_u = 5              # fewer, longer straight segments along the arc
    curve.use_fill_caps = True
    sp = curve.splines.new("BEZIER")
    pts = [(bx + 0.03, by, 1.29), (bx + 0.20, by + 0.08, 1.45),
           (kx - 0.06, ky - 0.04, 1.05), (kx, ky, 0.50)]
    sp.bezier_points.add(len(pts) - 1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    pipe = bpy.data.objects.new("hb_pipe", curve)
    pipe.data.materials.append(COPPER_LIGHT)
    bpy.context.collection.objects.link(pipe)
    parts.append(pipe)

    # --- spout and catch jug ---
    parts.append(box("hb_spout", (kx - 0.09, ky - 0.26, 0.17), (0.055, 0.16, 0.045),
                     COPPER_LIGHT, rot_z=math.radians(18)))
    parts.append(prism("hb_jug", 0.072, 0.13, (kx - 0.14, ky - 0.36, 0.065), TIN, sides=8))
    parts.append(prism("hb_jug_neck", 0.034, 0.045, (kx - 0.14, ky - 0.36, 0.15), TIN, sides=6))
    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "hb_stills_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "1"
    props.show_guide = False

    F.build_rig(bpy.context)
    scene.cycles.samples = 256
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_still():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cells to {OUT}")


if __name__ == "__main__":
    main()
