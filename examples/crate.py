"""Worked example: build a wooden crate and render it as PZ tile cells.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/crate.py

then package it:
    uv run --python 3.12 --with pillow python -m pzforge.cli build build/crate_cells \
        --mod-id ForgeCrate --mod-name "Forge Crate" --preset furniture \
        --prop CustomName=Crate --out dist
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "crate_cells"


def wood(name: str, colour: tuple[float, float, float]):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.1
    return mat


def box(name: str, centre, size, material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    obj.data.materials.append(material)
    return obj


def build_crate() -> list[bpy.types.Object]:
    """A crate 0.8 tiles across and 0.62 m tall, sitting on the tile.

    Vanilla furniture keeps a little air around the tile edge -- an object that runs
    the full 1.0 m looks wedged against its neighbours -- so this stops at 0.8.
    """
    plank = wood("crate_plank", (0.42, 0.28, 0.15))
    frame = wood("crate_frame", (0.30, 0.19, 0.10))

    w, d, h = 0.80, 0.80, 0.62
    parts = [box("crate_body", (0, 0, h / 2), (w * 0.96, d * 0.96, h), plank)]

    # Corner posts and rails, so the silhouette reads as a crate rather than a cube.
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(f"post_{sx}_{sy}",
                             (sx * w / 2, sy * d / 2, h / 2),
                             (0.07, 0.07, h), frame))
    for z in (0.08, h - 0.08):
        parts.append(box(f"rail_x_{z:.2f}", (0, 0, z), (w * 1.02, d * 1.03, 0.07), frame))
        parts.append(box(f"rail_y_{z:.2f}", (0, 0, z), (w * 1.03, d * 1.02, 0.07), frame))
    parts.append(box("lid", (0, 0, h + 0.02), (w * 1.02, d * 1.02, 0.05), plank))
    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgecrate_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "4"
    props.show_guide = False

    F.build_rig(bpy.context)
    scene.cycles.samples = 256
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_crate():
        part.parent = subject

    print(f"crate stands {0.67:.2f} m in a cell that clears "
          f"{F.clear_height(*F.cell_size(props.scale_2x)):.2f} m")
    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cells to {OUT}")
    for cell in manifest["cells"]:
        print(f"   {cell['file']}  facing={cell['facing']}")


if __name__ == "__main__":
    main()
