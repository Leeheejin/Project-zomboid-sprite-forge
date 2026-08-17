"""A WOODEN drum from the steel drum's geometry -- the composition test.

The two-stage workflow's whole point: stage 2 (the drum's SHAPE, in
metal_drum.build_drum) is reused verbatim, and only stage 1 (the material set)
is swapped -- oak staves for the shell, while the hoops, grooves and seam
strap stay in the metal class, because the fittings on a wooden barrel are
iron. If this file renders a convincing wooden barrel without touching the
geometry, materials and objects are genuinely orthogonal.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/wood_drum.py
Build with:
    uv run --python 3.12 --with pillow python -m pzforge.cli build \
        build/wood_drum_cells --mod-id ForgeWoodDrum --preset furniture \
        --out dist --stroke-amplitude 0.05 --grounding 2.0 \
        --contour-top 0.77 --contour 1.8
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT / "examples"))

import pz_sprite_forge as F  # noqa: E402
import metal_drum as drum  # noqa: E402

OUT = ROOT / "build" / "wood_drum_cells"
GRAIN_PATH = ROOT / "build" / "wood_drum_grain.png"


def make_grain() -> Path:
    """Wood grain wrapped around the barrel: the generator's native vertical
    streaks run along the staves under the cylinder's UV unwrap."""
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import material_spec, write_surface_map

    return write_surface_map(GRAIN_PATH, 512, 256, material_spec("wood", seed=11))


def wood_drum_materials() -> dict:
    """Stage 1 in oak. Paints borrow the wooden table's measured family; the
    class supplies everything else (wood hue correction, 0.40-1.60 swing,
    0.22-0.78 ramp). Fittings keep the metal class untouched."""
    return {
        "body": F.forge_material("wooddrum_body", "wood", (0.405, 0.223, 0.075),
                                 texture_path=GRAIN_PATH, projection="UV"),
        "lid": F.forge_material("wooddrum_lid", "wood", (0.356, 0.193, 0.066),
                                texture_path=GRAIN_PATH, projection="UV"),
        "dark": F.forge_material("wooddrum_hoop", "metal", (0.150, 0.152, 0.146)),
        "chime": F.forge_material("wooddrum_chime", "metal",
                                  (0.158, 0.161, 0.154)),
        "strap_edge": F.forge_material("wooddrum_strap_edge", "metal",
                                       (0.140, 0.140, 0.134)),
        "strap_face": F.forge_material("wooddrum_strap_face", "wood",
                                       (0.440, 0.240, 0.082)),
        "lip": F.forge_material("wooddrum_lip", "wood", (0.430, 0.250, 0.090)),
    }


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_grain()
    drum.make_texture()  # the metal fittings' maps still ship with the recipe
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgewooddrum_01"
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
    for part in drum.build_drum(wood_drum_materials()):
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
