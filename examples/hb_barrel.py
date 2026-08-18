"""HomeBrewing's wooden fermentation barrel -- the wood drum, put to work.

Composition through the two-stage workflow: the steel drum's geometry in the
wood class (stave shell, iron binding hoops, wooden rim and bung -- exactly
wood_drum's material set), plus the two parts a FERMENTER needs to read as
one: an iron spigot low on the front for drawing off, and the bung riding the
lid as the airlock. Rendered as the single S-facing sprite the mod's
`face SINGLE` entity uses.

Run:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/hb_barrel.py
Build (tileset id 2001 -- next free after the still's 2000):
    uv run --python 3.12 --with pillow python -m pzforge.cli build \
        build/hb_barrel_cells --mod-id HomeBrewingBarrel --preset appliance \
        --tileset-id 2001 --out dist \
        --stroke-amplitude 0.05 --grounding 2.0 --contour-top 0.77 --contour 1.8
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT / "examples"))

import pz_sprite_forge as F  # noqa: E402
import metal_drum as drum  # noqa: E402
import wood_drum  # noqa: E402

OUT = ROOT / "build" / "hb_barrel_cells"


def build_barrel() -> list[bpy.types.Object]:
    parts = drum.build_drum(wood_drum.wood_drum_materials(), grooves=False,
                            seam_strap=False, bolts=False,
                            hoop_bands=(0.16, 0.62))
    # Iron spigot: a small peg low on the south face, the drawing-off cue
    # every fermenter carries.
    spigot_mat = F.forge_material("hbbarrel_spigot", "metal",
                                  (0.150, 0.152, 0.146))
    # Sized for the sprite, not for realism: a to-scale spigot rendered 2 px
    # and vanished; this one reads as ~5x8 px of iron, placed BETWEEN the hoops -- at hoop height it disappeared into the band.
    r = drum.DIAMETER / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.028, depth=0.12,
                                        location=(0.0, -(r + 0.045), 0.30))
    spigot = bpy.context.active_object
    spigot.name = "spigot"
    spigot.rotation_euler = (math.radians(90), 0.0, 0.0)
    spigot.data.materials.append(spigot_mat)
    parts.append(spigot)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.016, depth=0.055,
                                        location=(0.0, -(r + 0.085), 0.255))
    tap = bpy.context.active_object
    tap.name = "spigot_tap"
    tap.data.materials.append(spigot_mat)
    parts.append(tap)
    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    wood_drum.make_grain()
    drum.make_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "hb_barrel_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "1"
    props.show_guide = False
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 512
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_barrel():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
