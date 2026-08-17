"""Recreate the vanilla Red Comfy Couch (furniture_seating_indoor_01_0/1).

The fifth reference, and the first to exercise two never-run pipeline paths at
once: a **2x1 multi-tile footprint** (two cells, SpriteGridPos in the tiledefs)
and **fabric** -- a texture grammar unlike metal or wood: soft low-contrast
wrinkles, rounded bevelled forms the toon ramp bands over, saturated upholstery
paint straight from the spec inversion ((1.0, 0.316, 0.107) on a south face).

Read off the composed reference:

* the couch spans ~1.84 m along world X (the two-tile axis), 0.82 m deep;
* backrest on the +Y side, seat facing -Y -- that is what Facing=S means here;
* boxy build: slab base, two seat cushions, straight backrest, block armrests,
  small dark feet. Rounded edges come from bevel modifiers, not sculpting.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/sofa.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "sofa_cells"
FABRIC_PATH = ROOT / "build" / "sofa_fabric.png"

LENGTH = 1.62       # along world X, spanning both tiles
DEPTH = 0.74
BASE_H = 0.30
SEAT_H = 0.20
ARM_H = 0.68
ARM_W = 0.155
BACK_H = 0.85
BACK_T = 0.20
FOOT_H = 0.07
#: The couch is centred between the two tile centres (0,0) and (1,0).
CX = 0.62


def make_fabric() -> Path:
    """Upholstery: soft large wrinkles, no metal streaks, gentle contrast."""
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import SurfaceSpec, write_surface_map

    # Read at 6x, the upholstery is soft mottle -- broad tonal blotches with no
    # directional streaks at all; the earlier stroke layer read as wood grain.
    # Nearly flat: vanilla upholstery is solid paint with only a whisper of
    # tonal drift -- any visible blotch pattern reads as wood figure.
    from pzforge.texture import material_spec
    spec = material_spec("fabric", seed=19)
    return write_surface_map(FABRIC_PATH, 768, 768, spec)


def bevel(obj, width=0.11, segments=6):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    try:
        bpy.ops.object.shade_auto_smooth(angle=0.9)
    except Exception:
        bpy.ops.object.shade_smooth()


def stuffed(obj, strength=0.028):
    """Organic displacement: hand-formed bulges instead of perfect bevel arcs.

    Mathematically exact silhouettes are the single strongest 'polygon render'
    tell. A subdivision plus low-amplitude clouds displacement wobbles every
    edge and dome the way stuffing does."""
    sub = obj.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 2
    tex = bpy.data.textures.get("PZ_Stuffing")
    if tex is None:
        tex = bpy.data.textures.new("PZ_Stuffing", "CLOUDS")
        tex.noise_scale = 0.55
    disp = obj.modifiers.new("stuff", "DISPLACE")
    disp.texture = tex
    disp.strength = strength
    disp.texture_coords = "GLOBAL"


def build_sofa() -> list[bpy.types.Object]:
    # Scaled 0.88 from the spec inversion: the shared ramp's top level (1.43xS)
    # is calibrated on metal, but vanilla lights fabric tops at barely 1.04xS --
    # matte cloth has no sheen -- so the paint absorbs the difference. G and B
    # sit low to hold the upholstery's 0.71 saturation.
    # Measured against the reference cell: vanilla's median lands at RGB
    # (189, 83, 54) -- a *bright* saturated red. The earlier 0.88 downscale was
    # the wrong lever; R goes back to full paint and only G stays restrained.
    # Vanilla upholstery is nearly flat (whole-sprite spread 0.094): a wide
    # dark-to-light paint swing turned the mottle into varnished wood. The swing
    # narrows to a whisper and the red stays saturated throughout.
    # Painterly hue ramp: shadow paint rotates toward deep crimson, highlight
    # toward orange -- same-hue value ramps are what read as plastic CG. The
    # texture map (near-flat mottle) drives between the two.
    # Paint back to a narrow same-hue band: the temperature rotation lives in the
    # soft ramp's shading stops (where the painter puts it), not in the texture
    # map -- map-driven hue swing rendered as marbled corrosion.
    # Play-distance bolding: the 8% whisper swing vanished entirely once the
    # sprite shrank on screen. The swing widens to ~15% at CONSTANT hue (each
    # channel scales by the same factor) -- the old marbled-corrosion failure
    # came from rotating hue across the map, not from value range itself.
    # The fabric class carries the cloth grammar (soft ramp, 0.02-0.98 range,
    # BOX at 2.0, ~15% same-hue swing); the upholstery paints are the couch's.
    body_mat = F.forge_material("sofa_body", "fabric",
                                (1.000, 0.205, 0.082),
                                texture_path=str(FABRIC_PATH))
    cushion_mat = F.forge_material("sofa_cushion", "fabric",
                                   (1.000, 0.228, 0.092),
                                   texture_path=str(FABRIC_PATH),
                                   swing=(0.875, 1.0))
    # The feet are wood -- a different class on the same object, exactly the
    # composition the two-stage workflow exists for.
    foot_mat = F.forge_material("sofa_foot", "wood", (0.140, 0.095, 0.062))
    # Deep crevice shadow: fabric's wide global spread (signature 0.347) comes
    # from form -- bright domed tops against near-black creases where cushions
    # meet. The map stays smooth; the darkness is geometry.
    crease_mat = F.forge_material("sofa_crease", "fabric", (0.300, 0.068, 0.030))

    parts = []

    def box(name, centre, size, material, soft=True):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = size
        obj.data.materials.append(material)
        if soft:
            bevel(obj)
            stuffed(obj)
        parts.append(obj)
        return obj

    # Base slab with the front skirt.
    box("base", (CX, -0.02, FOOT_H + BASE_H / 2),
        (LENGTH, DEPTH - 0.06, BASE_H), body_mat)

    # One long seat cushion, read straight off the reference -- the two sunken
    # pads of v1 were an invention.
    seat_len = LENGTH - 2 * ARM_W - 0.06
    seat_z = FOOT_H + BASE_H + SEAT_H / 2 - 0.03
    box("seat", (CX, -0.09, seat_z),
        (seat_len, DEPTH - BACK_T - 0.16, SEAT_H), cushion_mat)

    # Piping: the sewn welt along cushion edges, a thin brighter roll -- one of
    # the three painted features that make vanilla read as upholstery.
    pipe_mat = F.forge_material("sofa_pipe", "fabric",
                                texture_path=str(FABRIC_PATH),
                                dark=(0.980, 0.225, 0.090),
                                light=(1.000, 0.245, 0.100),
                                texture_scale=1.3)
    box("pipe_seat", (CX, -0.09 - (DEPTH - BACK_T - 0.16) / 2 + 0.02,
                      seat_z + SEAT_H / 2 - 0.005),
        (seat_len + 0.01, 0.022, 0.018), pipe_mat, soft=True)

    # Crease shadows: behind the seat at the backrest junction, and under the
    # seat's front lip.
    box("crease_back", (CX, DEPTH / 2 - BACK_T - 0.028, seat_z - 0.02),
        (seat_len + 0.02, 0.035, SEAT_H - 0.02), crease_mat, soft=False)
    box("crease_front", (CX, -0.09 - (DEPTH - BACK_T - 0.16) / 2 + 0.03,
                         seat_z - SEAT_H / 2 - 0.008),
        (seat_len + 0.02, 0.06, 0.03), crease_mat, soft=False)

    # Backrest: one tall slab leaning back ~8 degrees, rounded top. Its lean is
    # what keeps the big front face from reading as a flat wall.
    back = box("back", (CX, DEPTH / 2 - BACK_T / 2 - 0.01,
                        FOOT_H + (BACK_H - FOOT_H) / 2 + 0.06),
               (LENGTH - 2 * ARM_W + 0.04, BACK_T, BACK_H - FOOT_H - 0.06),
               body_mat)
    back.rotation_euler = (-0.20, 0.0, 0.0)

    # Armrests: full-depth rounded slabs at both ends.
    for k, sx in enumerate((-1, 1)):
        box(f"arm_{k}", (CX + sx * (LENGTH / 2 - ARM_W / 2), -0.02,
                         FOOT_H + (ARM_H - FOOT_H) / 2),
            (ARM_W, DEPTH - 0.04, ARM_H - FOOT_H), body_mat)

    # Chunky dark feet.
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"foot_{sx}_{sy}",
                (CX + sx * (LENGTH / 2 - 0.11), sy * (DEPTH / 2 - 0.11), FOOT_H / 2),
                (0.09, 0.09, FOOT_H), foot_mat, soft=False)

    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_fabric()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgesofa_01"
    props.output_dir = str(OUT)
    props.footprint_x = 2
    props.footprint_y = 1
    props.facings = "4"
    props.show_guide = False
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 512
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_sofa():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
