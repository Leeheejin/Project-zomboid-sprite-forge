"""HomeBrewing's still tile: the metal_still recipe on the mod's sheet.

This replaced the original hand-built hb_still (pre-toon Cycles materials,
hand-tuned lighting) with the two-stage workflow recipe -- same geometry and
materials as examples/metal_still.py, rendered as the single S-facing sprite
the mod's `face SINGLE` entity uses, on the HomeBrewing sheet name.

Run:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/hb_still.py
Build (tileset id 2000 -- first free id across installed mods, `pzforge ids`):
    uv run --python 3.12 --with pillow python -m pzforge.cli build \
        build/hb_still_cells --mod-id HomeBrewingTiles --preset appliance \
        --tileset-id 2000 --out dist \
        --stroke-amplitude 0.05 --grounding 1.7 --contour 1.5
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT / "examples"))

import pz_sprite_forge as F  # noqa: E402
import metal_still as still  # noqa: E402

OUT = ROOT / "build" / "hb_still_cells"


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    still.make_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "hb_still_01"
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
    # A face-SINGLE entity shows one view forever -- pick the reading where
    # the whole train (boiler, lyne arm, keg) is visible: metal_still's E
    # facing, pre-rotated here since only one facing renders.
    import math
    subject.rotation_euler = (0.0, 0.0, math.radians(90))
    for part in still.build_still():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
