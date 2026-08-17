"""Verify the addon inside a real Blender, by rendering and measuring the result.

The decisive check is the floor plane: a 1x1 plane lying on the tile must render as
a diamond exactly as wide as the cell, half as tall, and flush with the cell's bottom
edge -- that is what every vanilla floor sprite does, and if the camera maths were
off by even a degree it would not.

Run with:
    "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" -b \
        -P tests/test_blender_render.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import pz_sprite_forge as F  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -- ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(label)


def alpha_bbox(path: str) -> tuple[int, int, int, int, int, int]:
    """(left, right, bottom, top, width, height) of opaque pixels.

    ``bottom``/``top`` are rows counted up from the bottom edge of the cell, which is
    the edge PZ aligns its floor diamonds to.
    """
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = list(img.pixels)  # Blender stores images bottom-up, which is what we want
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[(y * w + x) * 4 + 3] > 0.5:
                xs.append(x)
                ys.append(y)
    bpy.data.images.remove(img)
    if not xs:
        return (0, 0, 0, 0, w, h)
    return (min(xs), max(xs), min(ys), max(ys), w, h)


def clear_scene() -> None:
    """Blender's startup file ships a cube, a camera and a light -- none of them ours."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="pzforge_blender_")

    print("== addon registration ==")
    clear_scene()
    F.register()
    check("addon registers", hasattr(bpy.types.Scene, "pz_forge"))

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"          # deterministic in background, no GPU needed
    scene.cycles.samples = 16
    props = scene.pz_forge
    props.sheet_name = "rigtest_01"
    props.alignment = "FLOOR"   # the floor-plane check below is a floor tile
    props.output_dir = tmp

    print("\n== rig ==")
    F.build_rig(bpy.context)
    cam = bpy.data.objects[F.CAMERA_NAME]
    check("camera is orthographic", cam.data.type == "ORTHO")
    check("ortho scale spans one tile diagonal",
          abs(cam.data.ortho_scale - F.ortho_scale()) < 1e-6, f"{cam.data.ortho_scale:.6f}")
    check("sensor fit is horizontal", cam.data.sensor_fit == "HORIZONTAL")
    check("render is 128x256",
          (scene.render.resolution_x, scene.render.resolution_y) == (128, 256))
    check("view transform is Standard (not AgX)",
          scene.view_settings.view_transform == "Standard",
          scene.view_settings.view_transform)
    check("film is transparent", scene.render.film_transparent)
    check("key light exists", F.SUN_NAME in bpy.data.objects)
    check("subject anchor exists", F.SUBJECT_NAME in bpy.data.objects)

    print("\n== floor plane alignment (the projection test) ==")
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.parent = bpy.data.objects[F.SUBJECT_NAME]

    out = os.path.join(tmp, "plane.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)

    left, right, bottom, top, w, h = alpha_bbox(out)
    width, height = right - left + 1, top - bottom + 1
    print(f"    diamond spans x {left}..{right} ({width}px), "
          f"y {bottom}..{top} ({height}px) up from the bottom of a {w}x{h} cell")
    check("diamond fills the cell width", abs(width - 128) <= 2, f"{width}px")
    check("diamond is half as tall as it is wide", abs(height - 64) <= 2, f"{height}px")
    check("diamond is 2:1", abs(width / max(height, 1) - 2.0) < 0.06,
          f"{width / max(height, 1):.3f}")
    check("diamond sits flush with the bottom of the cell", bottom <= 1, f"bottom={bottom}")
    check("diamond is horizontally centred", abs((left + right) / 2 - (w - 1) / 2) <= 1.5,
          f"centre={(left + right) / 2:.1f}")

    # The single strongest check available: 325 of the floor sprites in the game's own
    # Tiles2x.floor.pack trim to exactly (ox=0, oy=192, w=126, h=64) inside their
    # 128x256 cell. A correct rig has to reproduce that box exactly, not approximately.
    vanilla = (0, 192, 126, 64)
    rendered = (left, h - 1 - top, width, height)
    check("trim box is identical to vanilla's most common floor tile",
          rendered == vanilla, f"rendered {rendered} vs vanilla {vanilla}")

    print("\n== clear height ==")
    plane.hide_render = True
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    post = bpy.context.active_object
    post.scale = (0.05, 0.05, F.clear_height(128, 256))
    post.location = (0.0, 0.0, F.clear_height(128, 256) / 2)
    post.parent = bpy.data.objects[F.SUBJECT_NAME]

    out2 = os.path.join(tmp, "post.png")
    scene.render.filepath = out2
    bpy.ops.render.render(write_still=True)
    _, _, _, top2, _, h2 = alpha_bbox(out2)
    height_m = F.clear_height(128, 256)
    # A post standing at the tile centre starts half a diamond up the cell, so its
    # top should land at 32 + height * pixels-per-metre.
    expected = 32 + height_m * F.pixels_per_metre(128, 256)
    print(f"    a {height_m:.3f} m post reaches y={top2} of {h2} (predicted {expected:.0f})")
    check("post height matches the projection", abs(top2 - expected) <= 2,
          f"top={top2} expected={expected:.1f}")
    check("post still fits inside the cell", top2 <= h2 - 1, f"top={top2}")

    print("\n== lighting matches vanilla ==")
    post.hide_render = True
    plane.hide_render = True
    message = F.calibrate(bpy.context)
    print("    " + message)
    check("shipped light settings reproduce vanilla face brightness",
          "matches vanilla" in message, message)

    print("\n== batch render ==")
    plane.hide_render = False
    props.footprint_x, props.footprint_y = 2, 1
    props.facings = "2"
    manifest = F.render_cells(bpy.context)
    check("manifest lists every cell", len(manifest["cells"]) == 4,
          f"{len(manifest['cells'])} cells")
    check("all cell files exist",
          all(os.path.exists(os.path.join(tmp, c["file"])) for c in manifest["cells"]))
    check("manifest records the cell size", manifest["cell"] == [128, 256])
    check("manifest records both facings", manifest["facings"] == ["S", "E"])
    check("subject rotation is restored after batching",
          abs(bpy.data.objects[F.SUBJECT_NAME].rotation_euler.z) < 1e-9)

    print(f"\n{'ALL PASS' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()

