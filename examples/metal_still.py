"""A metal moonshine still, composed entirely from the two-stage workflow.

No vanilla still exists to copy, so this recipe is the workflow's intended
"original object" path: the SHAPES follow vanilla's form language (flat-ish
planes, low-segment prisms, detail in geometry), and every material comes
from the measured metal class -- steel from the drum's paint family, iron
fittings from its dark-line band, and the copper boiler's PATINA accent
reusing the drum lid's measured green (crafted_01_32's own aged-copper lid)
through the class's accent-stop mechanism.

Composition, one tile: an iron firebox carrying a copper boiler with a domed
cap, a swan-neck arm arching into a small steel thump keg with a coil, and a
catch jug at the front.

Run:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/metal_still.py
Build:
    uv run --python 3.12 --with pillow python -m pzforge.cli build \
        build/metal_still_cells --mod-id ForgeStill --preset appliance \
        --out dist --stroke-amplitude 0.05 --grounding 1.7 --contour 1.5
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "metal_still_cells"
TEXTURE_PATH = ROOT / "build" / "still_surface.png"

#: Boiler proportions: fat enough to read as a pot, small enough that the
#: whole train (firebox, boiler, keg, jug) stays inside one tile.
BOILER_R = 0.26
BOILER_H = 0.50
FIREBOX = 0.62
FIREBOX_H = 0.34
KEG_R = 0.145
KEG_H = 0.52


def make_texture() -> Path:
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import material_spec, write_surface_map

    return write_surface_map(TEXTURE_PATH, 512, 256,
                             material_spec("metal", seed=23))


def still_materials() -> dict:
    """Stage 1. Steel and iron take the drum's measured family (steel hue
    correction included); copper keeps its own hue, with the drum lid's
    measured patina green as the accent stop in its darkest streaks."""
    patina = (0.281, 0.329, 0.285)  # crafted_01_32's lid paint, measured
    return {
        # Patina only in the DARKEST streaks (position 0.08): at the metal
        # class default 0.18 the bold wear map spread green patches over the
        # whole pot and it read as flaking paint, not aged copper.
        "copper": F.forge_material("still_copper", "metal",
                                   texture_path=TEXTURE_PATH,
                                   dark=(0.340, 0.130, 0.070),
                                   light=(0.720, 0.300, 0.140),
                                   accent=patina, accent_position=0.08,
                                   hue=lambda p: p),
        "copper_dark": F.forge_material("still_copper_dark", "metal",
                                        (0.240, 0.108, 0.062),
                                        hue=lambda p: p),
        "steel": F.forge_material("still_steel", "metal",
                                  texture_path=TEXTURE_PATH,
                                  dark=(0.262, 0.256, 0.248),
                                  light=(0.578, 0.558, 0.532),
                                  accent=(0.315, 0.272, 0.238)),
        "iron": F.forge_material("still_iron", "metal", (0.150, 0.152, 0.146)),
        "iron_dark": F.forge_material("still_hatch", "metal",
                                      (0.085, 0.082, 0.078)),
        "band": F.forge_material("still_band", "metal", (0.400, 0.365, 0.335)),
    }


def build_still(mats: dict | None = None) -> list[bpy.types.Object]:
    """Stage 2 -- the still's shape, material-agnostic like every recipe."""
    mats = mats or still_materials()
    parts = []

    def add(obj, name, material):
        obj.name = name
        obj.data.materials.append(material)
        parts.append(obj)
        return obj

    def cylinder(name, r, depth, loc, material, verts=48, smooth=True):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r,
                                            depth=depth, location=loc)
        obj = bpy.context.active_object
        if smooth:
            try:
                bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
            except (AttributeError, TypeError, RuntimeError):
                bpy.ops.object.shade_smooth()
        return add(obj, name, material)

    def box(name, centre, size, material):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
        obj = bpy.context.active_object
        obj.scale = size
        return add(obj, name, material)

    # Iron firebox, back-left of the tile, with a dark hatch mouth on the
    # south face (the drawn-feature band, like the drum's grooves).
    fx, fy = -0.10, 0.08
    box("firebox", (fx, fy, FIREBOX_H / 2), (FIREBOX, FIREBOX, FIREBOX_H),
        mats["iron"])
    box("firebox_mouth", (fx - 0.06, fy - FIREBOX / 2 - 0.006,
                          FIREBOX_H * 0.42),
        (0.24, 0.02, 0.17), mats["iron_dark"])

    # Copper boiler on top: pot, shoulder cone, domed cap, swan neck.
    boiler_z0 = FIREBOX_H
    cylinder("boiler", BOILER_R, BOILER_H, (fx, fy, boiler_z0 + BOILER_H / 2),
             mats["copper"])
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=BOILER_R,
                                    radius2=0.075, depth=0.16,
                                    location=(fx, fy,
                                              boiler_z0 + BOILER_H + 0.08))
    cone = bpy.context.active_object
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
    except (AttributeError, TypeError, RuntimeError):
        bpy.ops.object.shade_smooth()
    add(cone, "boiler_shoulder", mats["copper"])
    cylinder("boiler_neck", 0.058, 0.16,
             (fx, fy, boiler_z0 + BOILER_H + 0.22), mats["copper"])
    # Riveted belly band -- the drawn line that keeps the pot from reading
    # as one blank cylinder (the drum's groove lesson).
    bpy.ops.mesh.primitive_torus_add(major_radius=BOILER_R, minor_radius=0.008,
                                     major_segments=48, minor_segments=8,
                                     location=(fx, fy, boiler_z0 + 0.17))
    add(bpy.context.active_object, "boiler_band", mats["copper_dark"])

    # Lyne arm: vanilla's form language is simple geometry, so the vapour
    # path is a straight pipe sloping from the neck top down to the keg,
    # with an elbow ball at the bend. (A full torus up there read as a
    # carrying ring, not a pipe.)
    kx, ky = 0.285, -0.16
    neck_top = boiler_z0 + BOILER_H + 0.30
    keg_in = (kx, ky, KEG_H + 0.16)
    start = (fx, fy, neck_top)
    d = (keg_in[0] - start[0], keg_in[1] - start[1], keg_in[2] - start[2])
    length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=0.030, depth=length,
        location=((start[0] + keg_in[0]) / 2, (start[1] + keg_in[1]) / 2,
                  (start[2] + keg_in[2]) / 2))
    pipe = bpy.context.active_object
    pipe.rotation_euler = (0.0, math.acos(d[2] / length),
                           math.atan2(d[1], d[0]))
    add(pipe, "lyne_arm", mats["copper_dark"])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10,
                                         radius=0.042, location=start)
    add(bpy.context.active_object, "lyne_elbow", mats["copper_dark"])

    # Steel thump keg with hoops, front-right; the worm coil rings above it.
    cylinder("keg", KEG_R, KEG_H, (kx, ky, KEG_H / 2), mats["steel"])
    for i, z in enumerate((KEG_H * 0.22, KEG_H * 0.78)):
        bpy.ops.mesh.primitive_torus_add(major_radius=KEG_R, minor_radius=0.007,
                                         major_segments=32, minor_segments=8,
                                         location=(kx, ky, z))
        add(bpy.context.active_object, f"keg_hoop_{i}", mats["iron"])
    for i in range(3):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=KEG_R - 0.028, minor_radius=0.012,
            major_segments=24, minor_segments=8,
            location=(kx, ky, KEG_H + 0.03 + i * 0.035))
        add(bpy.context.active_object, f"coil_{i}", mats["copper_dark"])

    # Catch jug: a small banded tin at the keg's front spout.
    cylinder("jug", 0.062, 0.16, (kx - 0.05, ky - KEG_R - 0.09, 0.08),
             mats["band"], verts=24)

    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgestill_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "4"
    props.show_guide = False
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 512
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_still():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
