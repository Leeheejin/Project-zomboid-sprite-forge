"""Recreate the vanilla metal crate (constructedobjects_01_46).

A second reference, chosen to be a *box* rather than a cylinder. The drum's left/right
falloff was capped by curvature -- each half of a cylinder averages over a range of
normals, so even zero ambient reads as only ~1.14. A box shows two flat faces, which is
exactly what the rig's lighting was calibrated against, so this is the case that says
whether that explanation was right.

Geometry read off the sprite with tools/show_sprite.py, using the projection directly:

* screen width is ``128 * (a + b)`` px for a box of half-extents a, b -- 114 px gives
  a plan diagonal of 0.891 tiles, so a square footprint of 0.891;
* the lowest silhouette point is the near corner at ``(a + b) * 32`` px below the tile
  centre -- measured 28 px against a predicted 28.5, confirming the same footprint;
* the top corner sits 96 px above the tile centre, so the body is 0.861 tall.

Note this is why ``pzforge spec`` reports 1.260 tiles wide: that figure is the screen
width in tile units, which for a box is its plan *diagonal*, and for a round object is
its diameter.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/metal_crate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "crate_metal_cells"
TEXTURE_PATH = ROOT / "build" / "crate_metal_surface.png"

#: The widest element decides the silhouette, so the body is sized so that the lid
#: lip -- body + overhang + lip -- lands on the measured 0.891, not the body itself.
FOOTPRINT = 0.857
HEIGHT = 0.849
#: The lid is a separate slab sitting proud of the body, with reinforcing ribs.
LID_THICKNESS = 0.10
LID_OVERHANG = 0.012
#: Corner posts and the bottom rail read as lighter edging against the panels.
POST = 0.030


def surface_texture() -> Path:
    from pzforge.texture import SurfaceSpec, bolden, write_surface_map

    # A cube's default unwrap gives every face the whole 0-1 UV square, so a 64 px
    # octave on a 512 px map lands at about 5 sprite pixels -- the fine band, which was
    # already matched. The map is enlarged instead of the octaves shrunk, so features
    # reach the coarse band while still having enough lattice cells to vary across a
    # face; too few cells is what made the drum's 128 px octave do nothing at all.
    # Rewritten to the drum's texture grammar: the old spec was pure value noise
    # with a 220 px lead octave -- soft watercolour patches, nothing like the
    # directional wear vanilla paints -- and it read as a different art style
    # sitting next to the drum. Strokes dominate now, octaves stay small.
    # ~9 texture px land on one sprite pixel at this UV scale, so strokes are
    # 9 px wide to survive sampling (the recurring texel-density lesson).
    # bolden(): drawn a size class bigger so the wear survives play-distance
    # shrink -- the same principle as the drum.
    spec = bolden(SurfaceSpec(octaves=[(120, 0.50), (60, 0.40), (28, 0.25)],
                              vertical_stretch=1.8, contrast=1.6,
                              stroke_count=180, stroke_length=420,
                              stroke_width=9, stroke_amplitude=0.22, seed=29))
    return write_surface_map(TEXTURE_PATH, 1024, 1024, spec)


def crate_warm(p):
    """The drum's measured hue correction, at crate strength: the crate rendered
    only 1.3 deg yellow of vanilla (34.3 vs 33.0), so the green-blue span narrows
    gently rather than by the drum's 0.55."""
    r, g, b = p
    return (r, b + 0.94 * (g - b), b)


def textured(name: str, dark, light, roughness: float, specular: float = 0.15):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(TEXTURE_PATH), check_existing=True)
    tex.image.colorspace_settings.name = "Non-Color"
    tex.interpolation = "Cubic"
    tex.extension = "REPEAT"

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.10
    ramp.color_ramp.elements[1].position = 0.90
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def plain(name: str, colour, roughness: float, specular: float = 0.15):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    return mat


def build_crate() -> list[bpy.types.Object]:
    """Body, proud lid with ribs, corner posts, bottom rail and a front latch.

    Colours come from the sprite's own palette via
        pzforge spec constructedobjects_01_46 --sprite
    which reports #908880 (12.2% of the sprite) as albedo 0.754/0.665/0.583 on a south
    face. The weathering runs around that rather than spanning the palette.
    """
    # 0.754 straight from the spec rendered the crate at the 51st percentile of vanilla
    # brightness against the reference's 37th, because the palette's brightest shade is
    # a highlight rather than the average of the panel. Scaling the range down to sit
    # around it, not on top of it, is what matches.
    # Rust in the darkest streak areas only, barely more saturated than the paint
    # -- the same restraint the drum needed; a redder stop higher up turns the
    # whole panel to wood.
    m = dict(hue=crate_warm)  # crate strength 0.94 -- measured 1.3 deg off only
    body_mat = F.forge_material("crate_body", "metal", texture_path=TEXTURE_PATH,
                                dark=(0.205, 0.182, 0.160),
                                light=(0.655, 0.578, 0.508),
                                accent=(0.285, 0.240, 0.200), **m)
    # The posts and ribs carry the body's texture too: as plain fills they came
    # out dead flat under the ramp (one normal, one level -- the drum-lid lesson).
    # Posts measure 0.85x of the wall interior in vanilla -- a dark edging band
    # inside the thin bright silhouette rim, which is what makes the box corner
    # read as a structural edge instead of wallpaper wrapping around.
    post_mat = F.forge_material("crate_post", "metal", texture_path=TEXTURE_PATH,
                                dark=(0.295, 0.264, 0.235),
                                light=(0.525, 0.472, 0.420), **m)
    # The S/E corner junction line: vanilla draws it at 0.76x of the faces.
    corner_mat = F.forge_material("crate_corner", "metal",
                                  (0.245, 0.228, 0.208), **m)
    dark_mat = F.forge_material("crate_dark", "metal", (0.160, 0.152, 0.140), **m)
    # Top-face variants, 8% brighter: the form graft used to lift the lid to the
    # reference's level, but top faces are excluded from it now (they misregister),
    # so the lift moves into the paint -- the drum-lid pattern.
    lid_mat = F.forge_material("crate_lid", "metal", texture_path=TEXTURE_PATH,
                               dark=(0.239, 0.213, 0.187),
                               light=(0.764, 0.674, 0.593),
                               accent=(0.333, 0.280, 0.233), **m)
    # Metallic read lives in the lid: vanilla's top band spans 0.34-0.60 where
    # ours sat at 0.37-0.60 -- the deep shadows between ribs were missing, and
    # metal is exactly that pairing of glinting rib tops with hard dark gaps.
    rib_mat = F.forge_material("crate_rib", "metal", texture_path=TEXTURE_PATH,
                               dark=(0.310, 0.278, 0.248),
                               light=(0.800, 0.720, 0.640), **m)

    parts = []
    half = FOOTPRINT / 2
    body_top = HEIGHT - LID_THICKNESS

    def box(name, centre, size, material):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = size
        obj.data.materials.append(material)
        parts.append(obj)
        return obj

    box("crate_body", (0, 0, body_top / 2), (FOOTPRINT, FOOTPRINT, body_top), body_mat)

    # Corner posts: four vertical edges, and a rail around the foot.
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"post_{sx}_{sy}", (sx * half, sy * half, body_top / 2),
                (POST, POST, body_top), post_mat)
    # The plinth: vanilla's crate sits on a distinctly darker base band -- with
    # the bottom luminance already matched, the remaining float came from the
    # rail reading as trim rather than as a base carrying weight.
    box("rail", (0, 0, POST / 2),
        (FOOTPRINT + POST * 0.6, FOOTPRINT + POST * 0.6, POST), corner_mat)
    # The front vertical corner where the S and E faces meet.
    box("corner_line", (-half, -half, body_top / 2), (0.018, 0.018, body_top),
        corner_mat)

    # Lid, proud of the body all round, ribbed. The ribs run along +X, which reads as
    # up-and-right in this projection -- the first attempt ran them along +Y and the
    # whole lid pattern came out mirrored about the wrong diagonal.
    lid_size = FOOTPRINT + LID_OVERHANG * 2
    box("lid", (0, 0, body_top + LID_THICKNESS / 2),
        (lid_size, lid_size, LID_THICKNESS), lid_mat)
    box("lid_lip", (0, 0, body_top + 0.014),
        (lid_size + 0.008, lid_size + 0.008, 0.030), rib_mat)
    for i in range(6):
        y = (i - 2.5) * 0.098
        box(f"rib_{i}", (0, y, HEIGHT + 0.010), (lid_size, 0.046, 0.026), rib_mat)
    # One heavier band crossing them, as the sprite shows.
    box("rib_cross", (0.02, 0, HEIGHT + 0.020), (0.085, lid_size, 0.042), rib_mat)

    # Hasp on the south face, the detail that fixes the sprite's orientation.
    box("hasp", (-0.12, -half - 0.012, body_top - 0.02), (0.075, 0.030, 0.16), post_mat)
    box("hasp_eye", (-0.12, -half - 0.026, body_top - 0.075),
        (0.038, 0.016, 0.055), dark_mat)
    return parts


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    surface_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgemetalcrate_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "4"
    props.show_guide = False
    # The ramp owns the contrast under toon shading; 1.0 is what its stop
    # positions were calibrated at.
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 384
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    for part in build_crate():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()


