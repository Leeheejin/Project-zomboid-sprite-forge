"""Recreate the vanilla metal drum (crafted_01_32) to test style fidelity.

Dimensions were read off the vanilla sprite with tools/show_sprite.py:

* the body silhouette is 64 px wide, and a horizontal circle projects to
  ``diameter * 90.51`` px across, so the drum is 0.707 tiles in diameter;
* the base ellipse dips 16 px below the tile centre, which is exactly
  ``0.707 * 45.25 / 2`` -- an independent confirmation of the same diameter;
* the silhouette tops out 117 px above the cell bottom, so the body is 0.880 tall.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P examples/metal_drum.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

OUT = ROOT / "build" / "drum_cells"
TEXTURE_PATH = ROOT / "build" / "drum_surface.png"
LID_TEXTURE_PATH = ROOT / "build" / "drum_lid_surface.png"

DIAMETER = 0.707
#: 0.880 puts the silhouette one pixel taller than the vanilla sprite once the chime
#: ring is included, so the barrel is trimmed by exactly one 2x pixel (1/78.38 m).
HEIGHT = 0.8672
#: Both rolling grooves sit low on the barrel in the vanilla sprite, close together,
#: not at the tidy one-third / two-thirds of a real drum.
GROOVE_HEIGHTS = (0.40, 0.29)
#: Where the vertical seam strap sits, as a compass bearing on the barrel. The camera
#: looks from the south-east, so due east (90 deg) lands right of the silhouette.
SEAM_AZIMUTH_DEG = 101.0
#: Minor radius of the top chime ring, subtracted from HEIGHT so the ring tops out
#: exactly at the silhouette height rather than adding to it. Small on purpose:
#: seen from above, the vanilla rim shows NO concentric grey band -- the lid runs
#: almost to the silhouette and the rim is only a rolled dark edge whose weight
#: varies (thin at the back, heavy at the front where the near wall overlaps the
#: recessed lid). Every attempt to make the ring *bigger* produced exactly the
#: concentric band that reads as a hula hoop resting on the drum.
CHIME_RADIUS = 0.014


def drum_warm(p):
    """The measured hue correction: the styled drum rendered at hue 45 against
    vanilla's 21.8, and narrowing the green-blue span pulls the near-neutral
    steel toward vanilla's warm grey. The lid is exempt -- its green is the
    reference's own paint."""
    r, g, b = p
    return (r, b + 0.55 * (g - b), b)


def shade_curved_sides(angle_degrees: float = 40.0) -> None:
    """Smooth shading that still keeps hard edges, across Blender versions.

    ``Mesh.use_auto_smooth`` was removed in 4.1 in favour of the shade_auto_smooth
    operator, so fall back to plain smooth shading if neither is available.
    """
    import math
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_degrees))
    except (AttributeError, TypeError, RuntimeError):
        bpy.ops.object.shade_smooth()


def metal_textured(name: str, dark, light, roughness: float, texture_path: Path,
                   specular: float = 0.10):
    """Painted metal whose wear comes from a generated detail map, not shader noise.

    Shader noise gave no control over which spatial band the contrast landed in.
    Measured against the reference, the recreation matched vanilla at 1-8 px and fell
    short almost entirely above 8 px -- the band of whole-panel tonal patches. The map
    from :mod:`pzforge.texture` is built octave by octave so that band can be aimed at
    directly, and it is applied through the mesh's own UVs so texture pixels land on
    sprite pixels predictably.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(texture_path), check_existing=True)
    tex.image.colorspace_settings.name = "Non-Color"
    tex.interpolation = "Cubic"
    tex.extension = "REPEAT"

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.08
    ramp.color_ramp.elements[1].position = 0.92
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)

    links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def metal(name: str, colour, roughness: float, weathering: float = 0.0):
    """A painted-metal look rather than a physically metallic one.

    ``Metallic = 1`` has almost no diffuse term, so under PZ's near-uniform ambient a
    metallic surface reflects the environment nearly equally in every direction and
    the south/east contrast collapses -- measured at 1.06 against vanilla's 1.42.
    Vanilla tile art is painted, essentially diffuse, so the rig gets a diffuse
    surface with a weak specular instead.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.10

    if weathering > 0:
        # Vanilla sprites carry hand-painted wear: their internal value spread is
        # 0.137 where a clean procedural render manages 0.05. A little noise in the
        # albedo puts that missing texture back.
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 14.0
        noise.inputs["Detail"].default_value = 8.0
        noise.inputs["Roughness"].default_value = 0.7
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.72
        dark = tuple(max(0.0, c * (1.0 - weathering)) for c in colour)
        light = tuple(min(1.0, c * (1.0 + weathering * 0.6)) for c in colour)
        ramp.color_ramp.elements[0].color = (*dark, 1.0)
        ramp.color_ramp.elements[1].color = (*light, 1.0)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def drum_materials() -> dict:
    """Stage 1 -- the steel drum's material set, one entry per part role.

    Base colours are not invented here: they come from the reference sprite's
    own measured palette, converted back through the rig's lighting response
    (``pzforge spec crafted_01_32 --sprite``: #707070 at 13.6% is albedo 0.438
    on a south face). Every entry routes through ``forge_material`` so the
    class supplies the metal grammar (steel hue correction, step ramp, rust
    accent stop) and only the paint choices are drum-specific. The rust stop
    is a hue shift, not just a value step, and lives in the darkest streak
    areas only -- redder or higher and the whole barrel went wood-brown.
    A recipe rebuilt with another class (see wood_drum.py) swaps this function
    and keeps the geometry.
    """
    m = dict(hue=drum_warm)  # measured at drum strength 0.55
    return {
        "body": F.forge_material("drum_body", "metal", texture_path=TEXTURE_PATH,
                                 dark=(0.262, 0.256, 0.248),
                                 light=(0.578, 0.558, 0.532),
                                 accent=(0.315, 0.272, 0.238), **m),
        # The lid keeps its own greenish paint (the reference's own colour) and
        # a soft low-contrast map -- a top face gets exactly one ramp level, so
        # a plain colour goes dead flat. Landed on vanilla's 0.43 top value.
        "lid": F.forge_material("drum_lid", "metal", texture_path=LID_TEXTURE_PATH,
                                dark=(0.281, 0.329, 0.285),
                                light=(0.329, 0.386, 0.329),
                                accent=(0.311, 0.329, 0.281),
                                accent_position=0.45, hue=lambda p: p),
        # Rings and grooves read as drawn dark lines: value 0.20-0.25 against
        # the 0.42 lid -- clearly drawn, still stepped by the ramp.
        "dark": F.forge_material("drum_dark", "metal", (0.150, 0.152, 0.146), **m),
        "chime": F.forge_material("drum_chime", "metal", (0.158, 0.161, 0.154), **m),
        # The seam strap is a raised seam: dark backing edges with a lit face.
        "strap_edge": F.forge_material("drum_strap_edge", "metal",
                                       (0.140, 0.140, 0.134), **m),
        "strap_face": F.forge_material("drum_strap_face", "metal",
                                       (0.400, 0.365, 0.335), **m),
        "lip": F.forge_material("drum_lip", "metal", (0.430, 0.410, 0.380),
                                hue=lambda p: p),
    }


def build_drum(mats: dict | None = None) -> list[bpy.types.Object]:
    """Stage 2 -- the drum's SHAPE, material-agnostic.

    A first attempt with three fat bright rings and isotropic mottling scored inside
    every vanilla tone band and still looked nothing like the target, because the
    difference was structural rather than statistical. Reading the sprite at 8x, the
    features that define it are: a dark raised chime ring at the top with the lid
    recessed inside it, a small bung plug, two *thin dark* rolling grooves low on the
    barrel with bolt heads along them, a vertical seam strap down the right with
    notches, and weathering that runs vertically. ``mats`` maps the part roles
    (body/lid/dark/chime/strap_edge/strap_face/lip) to materials; the default is
    the steel set, and wood_drum.py passes a wooden one over the same geometry.
    """
    mats = mats or drum_materials()
    body_mat = mats["body"]
    lid_mat = mats["lid"]
    dark_mat = mats["dark"]
    chime_mat = mats["chime"]
    strap_edge_mat = mats["strap_edge"]
    strap_face_mat = mats["strap_face"]
    lip_mat = mats["lip"]

    r = DIAMETER / 2
    parts = []

    def cylinder(name, radius, depth, z, material, smooth=True, verts=64):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                            depth=depth, location=(0, 0, z))
        obj = bpy.context.active_object
        obj.name = name
        obj.data.materials.append(material)
        if smooth:
            shade_curved_sides()
        parts.append(obj)
        return obj

    # HEIGHT is the silhouette's overall top, so the barrel has to stop short of it by
    # the chime ring's radius. Leaving the ring proud of HEIGHT made the recreation
    # two pixels taller than the vanilla sprite.
    body_top = HEIGHT - CHIME_RADIUS
    #: The lid sits this far below the rim wall's top. A chime at lid level read as
    #: a hula hoop resting on the drum; the vanilla rim is the *wall continuing up
    #: past the lid* and rolling over, so the lid has to be recessed inside it --
    #: deeply enough (2.5 px) that the recess survives at sprite resolution.
    LID_RECESS = 0.026

    # The lid is the body's own top cap, given its own material slot. Stacking a
    # separate disc on top does not work: Blender's cylinder primitive is capped, so
    # whichever ring sits highest covers the whole top with its own flat lid -- which
    # is what turned an earlier attempt's drum into a featureless dark disc.
    body = cylinder("drum_body", r, body_top - LID_RECESS,
                    (body_top - LID_RECESS) / 2, body_mat)
    body.data.materials.append(dark_mat)
    # Select the cap by its normal, not by z. The primitive's location goes into the
    # object transform, so mesh coordinates are centred on the origin and a world-z
    # test (poly.center.z > body_top) matched nothing -- the lid silently rendered
    # with the body's texture, warm streaks and all, and every lid material tweak
    # was a no-op.
    for poly in body.data.polygons:
        if poly.normal.z > 0.5:
            poly.material_index = 1
    # The lid proper: a smaller disc floating just above the dark cap, so the
    # exposed cap shows as the dark ring *inside* the top ellipse -- wall, ring,
    # then lid, the vanilla order. The ring must not reach the silhouette.
    # The rim is a standing collar: the wall rises past the lid with no outward
    # bulge, and the cue that it stands UP is the far side, where the collar's
    # inner face shows as a band between the wall's top edge and the recessed
    # lid. The lid stays wide -- a fat dark annulus on top read as a filled-in
    # ring, not a raised rim.
    lid = cylinder("drum_lid", r - 0.016, 0.010,
                   body_top - LID_RECESS + 0.005, lid_mat, smooth=False)

    # The rim wall: an open tube continuing the barrel past the recessed lid up to
    # the chime centre. Open, because a capped cylinder here would roof the lid
    # right back over.
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=r, depth=LID_RECESS,
                                        location=(0, 0, body_top - LID_RECESS / 2),
                                        end_fill_type="NOTHING")
    rim_wall = bpy.context.active_object
    rim_wall.name = "drum_rim_wall"
    rim_wall.data.materials.append(body_mat)
    shade_curved_sides()
    parts.append(rim_wall)

    def ring(name, major, minor, z, material):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                         major_segments=64, minor_segments=10,
                                         location=(0, 0, z))
        obj = bpy.context.active_object
        obj.name = name
        obj.data.materials.append(material)
        shade_curved_sides()
        parts.append(obj)
        return obj

    # Inset so the torus's OUTER edge sits flush with the barrel wall: centred on
    # r it bulged outward by its minor radius and the rim read as flaring outside
    # the lid. Vanilla's rim is a ring *inside* the top ellipse.
    ring("drum_chime", r - CHIME_RADIUS, CHIME_RADIUS, body_top, chime_mat)
    # Rolling grooves: thin, dark lines -- the opposite of a proud bright hoop.
    for i, z in enumerate(GROOVE_HEIGHTS):
        ring(f"drum_groove_{i}", r, 0.007, z, dark_mat)

    # The vanilla bung sits near the lid's front-left rim, not its centre: its pixel
    # position (44, 172) against the lid centre (64, 155) inverts through the
    # projection (screen-right = 64 px/m of x+y, screen-up = 32 px/m of y-x) to a
    # point at 85% of the lid radius toward the front-left.
    bung_z = body_top + 0.006
    cylinder("drum_bung", 0.036, 0.012, bung_z, dark_mat,
             smooth=False, verts=16).location = (0.075, -0.29, bung_z)

    # Bolt heads dotted along the lower groove, as in the sprite.
    for k in range(9):
        angle = math.radians(k * 40.0)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.013,
                                             location=(math.sin(angle) * (r + 0.006),
                                                       math.cos(angle) * (r + 0.006),
                                                       GROOVE_HEIGHTS[0] - 0.055))
        bolt = bpy.context.active_object
        bolt.name = f"drum_bolt_{k}"
        bolt.data.materials.append(dark_mat)
        parts.append(bolt)

    # Vertical seam strap. The sprite shows it about three quarters across, which for
    # a south-east camera puts it a little north of due east on the barrel.
    strap_angle = math.radians(SEAM_AZIMUTH_DEG)
    sx, sy = math.sin(strap_angle), math.cos(strap_angle)
    # Tangent along the barrel surface; -t points screen-right of the strap.
    tx, ty = math.cos(strap_angle), -math.sin(strap_angle)
    # The strap must not reach the floor: standing proud of the barrel, a full-height
    # strap pushed the base ellipse a pixel lower than the vanilla sprite's.
    strap_bottom, strap_top = 0.04, body_top - 0.02
    strap_h = strap_top - strap_bottom
    strap_mid = (strap_bottom + strap_top) / 2

    def strap_box(name, tangent_w, radial_t, proud, height, z, material,
                  tangent_shift=0.0):
        bpy.ops.mesh.primitive_cube_add(
            size=1.0, location=(sx * (r + proud) - tx * tangent_shift,
                                sy * (r + proud) - ty * tangent_shift, z))
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (tangent_w, radial_t, height)
        obj.rotation_euler = (0.0, 0.0, -strap_angle)
        obj.data.materials.append(material)
        parts.append(obj)
        return obj

    # Backing plate, visible only as the two dark edge lines...
    strap_box("drum_strap_back", 0.044, 0.022, 0.002, strap_h, strap_mid,
              strap_edge_mat)
    # ...because a narrower body-toned face sits proud of it. This is what makes the
    # seam read raised: paint on its face, shadow lines at its borders. The vanilla
    # strap is petite -- about 5 px overall with a 3 px face and 1 px lines -- and
    # every wider or prouder build read as tape stuck on the barrel: the box is
    # tangent-flat against a curved surface, so excess width shows up as a dark
    # side face and excess proudness as silhouette bumps.
    strap_box("drum_strap_face", 0.026, 0.024, 0.004, strap_h, strap_mid,
              strap_face_mat)

    # Notches ride the strap's right edge in the sprite -- small lit blocks bridging
    # the border line, not holes punched through the strap.
    for k in range(5):
        z = HEIGHT * (0.16 + 0.17 * k)
        strap_box(f"drum_notch_{k}", 0.013, 0.022, 0.005, 0.020, z,
                  strap_face_mat, tangent_shift=0.021)

    return parts


def make_texture() -> Path:
    """Generate the barrel's detail map, weighted toward the band renders miss.

    Written next to the cells so a run is self-contained, and regenerated each time so
    the spec in this file is the single source of truth for what the surface looks like.
    """
    sys.path.insert(0, str(ROOT))
    from pzforge.texture import SurfaceSpec, bolden, write_surface_map

    # Sized in texture pixels. The visible half of the barrel is 64 sprite pixels wide
    # and 256 texture pixels around, so 4 texture px is 1 sprite px horizontally -- the
    # missing band above 8 sprite px starts at roughly 32 texture px.
    #
    # A 128 px lead octave was tried first and did nothing: at that size the wrap holds
    # only four lattice cells across and one up the barrel, so the visible face landed
    # on a single smooth ramp. Enough cells have to fall inside the visible face for
    # the patches to register at all.
    # Stroke layer: stretched value noise still reads as blotches; the vanilla drum's
    # wear runs in coherent vertical streaks, which only drawn strokes produce.
    # 512 px around / 64 sprite px visible -> a 2 px stroke is ~0.5 sprite px wide,
    # merging into the streak bundles the reference shows.
    # bolden(): in game the tile renders far smaller than the working zoom,
    # so the wear features are drawn a size class bigger -- fewer, wider,
    # stronger -- or the material read washes out at play distance.
    spec = bolden(SurfaceSpec(
        octaves=[(64, 1.00), (32, 0.65), (16, 0.32), (8, 0.18)],
        vertical_stretch=2.0,
        contrast=1.9,
        stroke_count=170,
        stroke_length=90,
        stroke_width=2,
        stroke_amplitude=0.17,
        seed=13,
    ))
    # The lid map is soft and broad: no strokes, gentle contrast, cells large
    # enough to read as patches of weathering on a disc rather than streaks.
    lid_spec = bolden(SurfaceSpec(octaves=[(96, 1.00), (48, 0.55), (24, 0.30)],
                                  vertical_stretch=1.0, contrast=1.25,
                                  seed=41))
    write_surface_map(LID_TEXTURE_PATH, 256, 256, lid_spec)
    return write_surface_map(TEXTURE_PATH, 512, 256, spec)


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    make_texture()
    F.register()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    props = scene.pz_forge
    props.sheet_name = "forgedrum_01"
    props.output_dir = str(OUT)
    props.footprint_x = props.footprint_y = 1
    props.facings = "4"
    props.show_guide = False
    # Under the toon ramp the light levels are fixed by the ramp itself, so the
    # contrast knob (which trades ambient for key) no longer shapes the output;
    # 1.0 keeps the calibration the ramp stops were measured under.
    props.contrast_boost = 1.0
    props.toon_shading = True

    F.build_rig(bpy.context)
    scene.cycles.samples = 512
    scene.cycles.use_denoising = True

    subject = bpy.data.objects[F.SUBJECT_NAME]
    # This sprite is drawn one pixel right of the cell centre. Vanilla objects average
    # 63.76 across 195 symmetric sprites, so the rig's centring is right and this one
    # is the outlier -- nudging the model matches the reference without moving the rig.
    # Screen-right is north-east, so one 2x pixel is 1/90.51 m along that diagonal.
    step = 1.0 / 90.5097 / (2 ** 0.5)
    subject.location = (step, step, 0.0)
    for part in build_drum():
        part.parent = subject

    manifest = F.render_cells(bpy.context)
    print(f"rendered {len(manifest['cells'])} cell(s) to {OUT}")


if __name__ == "__main__":
    main()









