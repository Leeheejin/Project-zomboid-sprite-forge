"""Recreate the vanilla wooden table (carpentry_01_29) -- the non-metal reference.

The fourth reference, and the one that exercises everything metal did not: warm
saturated wood paint, planks with drawn seams, thin legs that must not float, a
large top face for the top grade, and vanilla's painted floor shadow (flat black
at alpha 51 -- measured), which the build adds with ``--ground-shadow 1``.

Read off the reference with tools/show_sprite.py and pzforge spec:

* the top diamond is 121 px wide -> 0.95 tiles square;
* the tabletop's side band is 4-5 px -> slab about 0.055 m thick;
* legs are ~7 px wide posts -> 0.075 m square;
* paint: spec inverts the dominant #806038 to albedo (0.583, 0.316, 0.107) on a
  south face -- the planks vary around that, they do not span the whole palette.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/wood_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "wood_table_cells"
GRAIN_PATH = ROOT / "build" / "wood_grain.png"

TOP_SIZE = 0.95
TOP_THICK = 0.055
#: Height of the top surface. Standard table height, then nudged until the top
#: diamond's screen position matched the reference.
TOP_HEIGHT = 0.79
LEG = 0.075
PLANKS = 5


def make_grain() -> Path:
    """The wood grain map: long thin streaks running along the plank axis.

    Generated with the streaks along V (the only direction the generator draws),
    then written with ``grain_axis="u"`` so they run along U -- which the BOX
    projection puts along world X, the planks' long axis. The stroke layer is
    what makes it read as grain: stretched noise alone is blotches, not fibre.
    """
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import material_spec, write_surface_map

    # The wood preset carries the streak-dominated grammar this file used to
    # define inline (fibre strokes over a whisper of drift), now boldened a
    # size class so the grain survives play-distance shrink.
    spec = material_spec("wood", seed=7)
    # Measured with a stripe texture: under BOX projection the image's Y axis
    # lands along world X on the top face, so the generator's native vertical
    # streaks (grain_axis="v") already run along the planks. The transposed map
    # put the grain *across* them, which read as mottle.
    return write_surface_map(GRAIN_PATH, 512, 512, spec, grain_axis="v")


def warm(p):
    """Pull a wood paint toward vanilla's hue: the rendered sprite measured
    3.4 deg yellower and 0.04 less saturated than the reference, so the green
    span narrows (hue toward red) and blue drops (saturation up)."""
    r, g, b = p
    b2 = 0.88 * b
    return (r, b2 + 0.87 * (g - b), b2)


def build_table() -> list[bpy.types.Object]:
    # Plank paints vary around the spec albedo, alternating so the seams read even
    # before the finishing pass draws them. Wood is saturated -- the metal habit
    # of desaturating toward grey is exactly wrong here.
    # Scaled 0.72 from the spec inversion: the spec reports the *brightest*
    # common shade, but the vanilla table's median sits well below it -- painting
    # at the bright end rendered the whole table a full value step too light.
    plank_paints = [
        (0.356, 0.193, 0.066), (0.405, 0.223, 0.075), (0.370, 0.200, 0.066),
        (0.419, 0.232, 0.080), (0.382, 0.208, 0.070),
    ]
    # Grain rides the BOX projection in object space, so each plank samples a
    # different band of the same map for free. Dark and light paint stops sit
    # +-28% around each plank's own paint -- wood grain swings further than
    # painted metal wear does.
    # Wide paint range on purpose: +-28% compressed to a 0.09 render spread where
    # vanilla's planks run 0.22 -- their grain swings from near-black-brown to
    # light tan. The ramp positions steepen the map's midtones the same way.
    # The wood class supplies the whole grammar this file used to spell out:
    # the measured hue correction (the old local warm()), the 0.40-1.60 swing,
    # BOX at 1.1 and the 0.22-0.78 ramp. Only the plank paints are table's own.
    plank_mats = [
        F.forge_material(f"table_plank_{k}", "wood", p, texture_path=GRAIN_PATH)
        for k, p in enumerate(plank_paints)
    ]
    leg_mat = F.forge_material("table_leg", "wood", (0.218, 0.119, 0.041))
    apron_mat = F.forge_material("table_apron", "wood", (0.188, 0.101, 0.036))
    dark_mat = F.forge_material("table_dark", "wood", (0.160, 0.110, 0.060))
    seam_mat = F.forge_material("table_seam", "wood", (0.105, 0.072, 0.042))
    broken_mat = F.forge_material("table_plank_broken", "wood", plank_paints[1],
                                  texture_path=GRAIN_PATH, swing=(0.34, 1.36))

    parts = []

    def box(name, centre, size, material):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = size
        obj.data.materials.append(material)
        parts.append(obj)
        return obj

    # Planks run along +X, which reads as up-and-right in this projection -- the
    # same orientation the crate ribs needed.
    plank_w = TOP_SIZE / PLANKS
    slab_z = TOP_HEIGHT - TOP_THICK / 2
    # A dark backing board under the planks: the seams between them open onto it,
    # so every gap reads as the drawn dark line vanilla separates planks with --
    # not as an antialiased sliver of whatever lies below the table.
    # Low enough that even the sagged broken piece stays above it: at -0.008 the
    # backing's top sat higher than the dropped piece and swallowed it whole --
    # the mystery flat patch was the backing showing through.
    box("seam_backing", (0, 0, slab_z - 0.022),
        (TOP_SIZE - 0.05, TOP_SIZE - 0.05, TOP_THICK), seam_mat)
    # The under-slab shadow strip: a thin dark band hugging the slab's underside,
    # so the junction where the top meets legs and apron reads at vanilla's 0.75
    # of the slab side -- the 'sitting under its own shadow' cue.
    box("slab_shadow", (0, 0, TOP_HEIGHT - TOP_THICK - 0.011),
        (TOP_SIZE * 0.99, TOP_SIZE * 0.99, 0.022), seam_mat)
    #: Where plank 1 is snapped: the split sits left of centre, like the
    #: reference's broken board.
    CRACK_X = -0.18
    for k in range(PLANKS):
        y = (k - (PLANKS - 1) / 2) * plank_w
        jitter = (0.002, -0.001, 0.0015, -0.002, 0.001)[k]
        if k == 1:
            # The broken plank: two pieces around an angled gap, the short end
            # sagged and twisted so the crack opens as a wedge onto the dark
            # backing -- the story beat every vanilla table carries somewhere.
            xa0, xa1 = -TOP_SIZE / 2, CRACK_X - 0.020
            # In-plane twist only: any out-of-plane tilt drops the piece's top
            # face out of the ramp's top band and it renders as a flat patch one
            # whole light step darker -- the toon ramp quantises small tilts into
            # big tone jumps. The piece's darkness is painted instead (x0.85),
            # the way vanilla darkens its displaced board deliberately.
            piece = box(f"plank_{k}_broken", ((xa0 + xa1) / 2, y,
                                              slab_z + jitter - 0.008),
                        (xa1 - xa0, plank_w - 0.014, TOP_THICK), broken_mat)
            piece.rotation_euler = (0.0, 0.0, 0.050)
            xb0, xb1 = CRACK_X + 0.020, TOP_SIZE / 2
            box(f"plank_{k}", ((xb0 + xb1) / 2, y, slab_z + jitter),
                (xb1 - xb0, plank_w - 0.014, TOP_THICK), plank_mats[k])
            continue
        box(f"plank_{k}", (0, y, slab_z + jitter),
            (TOP_SIZE, plank_w - 0.014, TOP_THICK), plank_mats[k])

    # Nail heads near the plank ends, on the top surface.
    for k in range(PLANKS):
        y = (k - (PLANKS - 1) / 2) * plank_w
        for sx in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=10, radius=0.011, depth=0.012,
                location=(sx * (TOP_SIZE / 2 - 0.055), y, TOP_HEIGHT + 0.004))
            nail = bpy.context.active_object
            nail.name = f"nail_{k}_{sx}"
            nail.data.materials.append(dark_mat)
            parts.append(nail)

    # Legs, inset from the corners.
    inset = TOP_SIZE / 2 - 0.085
    leg_h = TOP_HEIGHT - TOP_THICK
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"leg_{sx}_{sy}", (sx * inset, sy * inset, leg_h / 2),
                (LEG, LEG, leg_h), leg_mat)

    # Apron rails under the slab, connecting the legs.
    drop = 0.10
    rail_z = leg_h - drop / 2
    span = inset * 2 - LEG
    for sy in (-1, 1):
        box(f"apron_x_{sy}", (0, sy * inset, rail_z), (span, 0.03, drop), apron_mat)
    for sx in (-1, 1):
        box(f"apron_y_{sx}", (sx * inset, 0, rail_z), (0.03, span, drop), apron_mat)

    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_grain()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgewoodtable_01"
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
    # The reference sits 4 px screen-left of the cell centre; screen-left is -X-Y.
    subject.location = (-0.031, -0.031, 0.0)
    for part in build_table():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
