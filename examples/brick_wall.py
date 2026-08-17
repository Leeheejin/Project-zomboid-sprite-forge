"""Recreate the vanilla brick wall set (walls_exterior_house_01_0..3).

The wall case exercises what furniture never did: paper-thin slabs pinned to
tile EDGES, a four-sprite set (WallW, WallN, corner, SE post) that is not one
multi-tile object, and the face-luminance rule on near-vertical geometry only.

Read off the reference with pixel measurements (bbox + column profiles):

* WallW is 66 px wide = the 64 px west-edge run + a 2 px thickness lip, so the
  slab is 2/64 = 0.031 tiles thick; the WallSE post is 6 px wide = 128 * t, a
  0.047 tile square post.
* the wall stands 192 px tall at 2x -> 192/78.38 = 2.4497 m.
* the SE post's bottom sits at the N diamond corner's ground line: WallSE is
  the corner post at its OWN tile's north-west corner, completing wall runs
  that end on the neighbouring tiles.
* faces: N wall (south-facing) v0.65 vs W wall (east-facing) v0.57 -> ratio
  0.88, the same face-luminance rule the furniture followed.
* brick courses are 8 px on screen at 2x with mortar 1-2 px and ~13 levels
  LIGHTER than the brick -- cool blue-grey, h224 s0.15, spread only 0.06-0.08.

Each of the four wall pieces stands on its own tile of a 2x2 footprint; the
tile pass then cuts the render into the four sprites, in vanilla's sprite
order: (0,0)=WallW, (1,0)=WallN, (0,1)=corner, (1,1)=SE post.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/brick_wall.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "brick_wall_cells"
BRICK_PATH = ROOT / "build" / "brick_surface.png"

#: 192 px at 2x, at the measured 78.38 px/m.
HEIGHT = 2.4497
#: Slab thickness: the 2 px lip past the 64 px edge run.
THICK = 0.031
#: The SE post: 6 px total width = 128 * t.
POST = 0.047


def make_brick() -> Path:
    """The brick map: regular bond with light mortar joints.

    Dimensions are multiples of the course/brick sizes so the map tiles.
    """
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import material_spec, write_surface_map

    # Width a multiple of the brick length and height of the course, so the
    # bond tiles without a seam.
    return write_surface_map(BRICK_PATH, 546, 520, material_spec("brick"))


def build_walls() -> list[bpy.types.Object]:
    # Paint calibrated against the rendered N face: first pass from the sofa's
    # S-face factor 0.733, then corrected by the measured render/vanilla ratio
    # per channel (147,152,161 -> 141,147,165). Mortar sits ~13 levels above
    # the brick, so the light stop is the mortar and the dark stop the brick's
    # shadow end. Walls shade shallower than furniture: vanilla's W face is
    # 0.88 of its N face where the stock E level renders 0.787 (E 0.711 got
    # 0.83 -- the stop-to-render map is not linear, hence the second step).
    # And wall shadows stay COOL: vanilla's B/R is 1.17 on both faces, so the
    # shade band reuses the lit tint instead of the furniture warm shadow.
    # The brick class carries the wall grammar (the shallower E level, cool
    # shadows, BOX at the render-calibrated 1.13 -- at 2.0 a course landed on
    # ~2 screen px and the sampling averaged the bond away). Explicit stops:
    # split-calibrated body (137,145,161) h220 vs mortar (150,154,178) h231 --
    # the mortar is not just lighter, it is BLUER -- with the dark stop pushed
    # below the body median so the joints and accent bricks survive the ~40%
    # sampling blur and stay BOLD at play distance.
    brick_mat = F.forge_material(
        "brick", "brick", texture_path=BRICK_PATH,
        dark=(0.630, 0.675, 0.820),
        light=(0.790, 0.820, 1.0))

    parts = []

    def box(name, centre, size):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = size
        obj.data.materials.append(brick_mat)
        parts.append(obj)
        return obj

    # Tile (0,0): WallW -- a slab along the tile's west edge, its east face
    # toward the camera.
    box("wall_w", (-0.5 + THICK / 2, 0.0, HEIGHT / 2), (THICK, 1.0, HEIGHT))

    # Tile (1,0): WallN -- along the north edge, south face toward the camera.
    box("wall_n", (1.0, 0.5 - THICK / 2, HEIGHT / 2), (1.0, THICK, HEIGHT))

    # Tile (0,1) = world (0,-1): the NW corner, both slabs joined. The north
    # slab butts against the west slab's inner face so no faces are coplanar,
    # and stops 2 mm short of the east tile edge -- a face exactly ON the
    # boundary plane belongs to the neighbour tile and the cut would drop it.
    box("corner_w", (-0.5 + THICK / 2, -1.0, HEIGHT / 2), (THICK, 1.0, HEIGHT))
    box("corner_n", ((-0.5 + THICK + 0.498) / 2, -0.5 - THICK / 2, HEIGHT / 2),
        (0.998 - THICK, THICK, HEIGHT))

    # Tile (1,1) = world (1,-1): the SE post at its own tile's NW corner.
    box("post_se", (0.5 + POST / 2, -0.5 - POST / 2, HEIGHT / 2),
        (POST, POST, HEIGHT))

    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_brick()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgebrickwall_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 2
    props.facings = "1"
    # Wall pieces are independent per-tile sprites: without isolation the
    # southern tiles' walls occlude -- and amputate -- the pieces behind them.
    props.isolate_tiles = True
    props.show_guide = False
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 512
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_walls():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()
