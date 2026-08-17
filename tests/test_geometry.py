"""Check the addon's projection maths against the geometry measured from the game.

The addon imports ``bpy``, which only exists inside Blender, so it is loaded here
against a stub. That is enough to exercise every pure-maths function, which is
where a mistake would silently produce misaligned sprites.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_addon():
    """Import blender/pz_sprite_forge.py with a stubbed-out bpy."""
    bpy = types.ModuleType("bpy")

    class _Prop:
        def __init__(self, *a, **k):
            pass

    props = types.ModuleType("bpy.props")
    for name in ("BoolProperty", "EnumProperty", "FloatProperty", "IntProperty",
                 "StringProperty", "PointerProperty"):
        setattr(props, name, _Prop)
    bpy.props = props

    bpy_types = types.ModuleType("bpy.types")
    for name in ("Operator", "Panel", "PropertyGroup"):
        setattr(bpy_types, name, type(name, (), {}))
    bpy.types = bpy_types
    bpy.utils = types.SimpleNamespace(register_class=lambda c: None,
                                      unregister_class=lambda c: None)
    bpy.data = types.SimpleNamespace()
    bpy.path = types.SimpleNamespace(abspath=lambda p: p)

    mathutils = types.ModuleType("mathutils")
    mathutils.Euler = lambda seq, order="XYZ": tuple(seq)

    class Vector(tuple):
        def __new__(cls, seq):
            return super().__new__(cls, seq)

        def __mul__(self, k):
            return Vector(v * k for v in self)

        def __add__(self, other):
            return Vector(a + b for a, b in zip(self, other))

    mathutils.Vector = Vector

    class Matrix:
        def __init__(self, cos_a: float, sin_a: float):
            self._c, self._s = cos_a, sin_a

        @classmethod
        def Rotation(cls, angle: float, size: int, axis: str) -> "Matrix":
            assert axis == "Z", "stub supports Z rotations only"
            return cls(math.cos(angle), math.sin(angle))

        def __matmul__(self, v):
            return Vector((self._c * v[0] - self._s * v[1],
                           self._s * v[0] + self._c * v[1], v[2]))

    mathutils.Matrix = Matrix

    for name, mod in (("bpy", bpy), ("bpy.props", props), ("bpy.types", bpy_types),
                      ("mathutils", mathutils)):
        sys.modules[name] = mod

    path = ROOT / "blender" / "pz_sprite_forge.py"
    spec = importlib.util.spec_from_file_location("pz_sprite_forge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load_addon()
FAILURES: list[str] = []


def check(label: str, got, want, tol=1e-6):
    ok = abs(got - want) <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<46} got {got!r:<22} want {want!r}")
    if not ok:
        FAILURES.append(label)


print("== projection ==")
# Tiles2x.floor.pack: the floor diamond trims to 126x64 inside a 128x256 cell,
# i.e. a full-bleed 128x64 diamond -> exactly 2:1.
check("camera elevation is 2:1 dimetric",
      math.degrees(F.CAMERA_ELEVATION), math.degrees(math.asin(0.5)), 1e-9)
check("ortho scale == tile diagonal", F.ortho_scale(), math.sqrt(2.0))
check("cell size 2x", F.cell_size(True)[0] * 1.0, 128.0)
check("cell size 2x height", F.cell_size(True)[1] * 1.0, 256.0)
check("cell size 1x", F.cell_size(False)[0] * 1.0, 64.0)

print("\n== cell framing ==")
CW, CH = F.cell_size(True)
ppm = F.pixels_per_metre(CW, CH)
check("pixels per metre (2x)", ppm, math.cos(math.radians(30)) * 128 / math.sqrt(2), 1e-9)
check("pixels per metre (1x) is half of 2x",
      F.pixels_per_metre(*F.cell_size(False)) * 2, ppm, 1e-9)

# The tile centre must land exactly half a diamond-height above the cell bottom,
# so the floor sits flush with the bottom edge like every vanilla floor tile.
aim = F.aim_height(CW, CH)
view_h = F.ortho_scale() * CH / CW
centre_offset_px = (aim * math.cos(F.CAMERA_ELEVATION)) / view_h * CH
check("tile centre sits a half-diamond above the cell bottom",
      CH / 2 - centre_offset_px, CW / 4, 1e-9)
check("aim height", aim, math.sqrt(1.5), 1e-9)
check("clear height is scale independent",
      F.clear_height(*F.cell_size(False)), F.clear_height(CW, CH), 1e-9)
check("clear height ~ a storey", F.clear_height(CW, CH), 2.4494897, 1e-6)

print("\n== camera placement ==")
d = F.camera_direction()
check("camera direction is unit length", math.sqrt(sum(v * v for v in d)), 1.0, 1e-9)
check("camera looks down 30 degrees", math.degrees(math.asin(d[2])), 30.0, 1e-9)
# Vanilla draws Facing=S (395 sprites) and Facing=E (404) far more than N/W (26 each),
# so the camera must sit to the south-east and see exactly those two faces.
check("camera is east of the tile", 1.0 if d[0] > 0 else 0.0, 1.0)
check("camera is south of the tile", 1.0 if d[1] < 0 else 0.0, 1.0)
check("camera azimuth is 45 degrees",
      math.degrees(math.atan2(d[0], -d[1])), 45.0, 1e-9)

print("\n== key light ==")
# Solved from the measured wall luminances: A + K*cos(a - t) with
# S=119.18, E=96.37 and ambient ~ the mean of the two unlit faces.
ambient = (F.VANILLA_TARGETS["W"] + F.VANILLA_TARGETS["N"]) / 2
ks = F.VANILLA_TARGETS["S"] - ambient
ke = F.VANILLA_TARGETS["E"] - ambient
solved = math.degrees(math.atan2(ke, ks))
# The rig ships the render-calibrated azimuth, which sits a couple of degrees below
# the closed-form one: in a real render, light bouncing off the lit faces brightens
# the shaded face, so a slightly tighter azimuth is needed to hit vanilla's contrast.
check("light azimuth is close to the closed-form solution",
      math.degrees(F.LIGHT_AZIMUTH_FROM_SOUTH), solved, 3.0)
check("render-calibrated azimuth is the tighter of the two",
      1.0 if math.degrees(F.LIGHT_AZIMUTH_FROM_SOUTH) < solved else 0.0, 1.0)
check("vanilla S/E contrast", F.VANILLA_TARGETS["S"] / F.VANILLA_TARGETS["E"], 1.2367, 1e-3)
rot = F.sun_rotation()
check("sun tilt from straight down",
      math.degrees(rot[0]), 90 - math.degrees(F.LIGHT_ELEVATION), 1e-9)

# The key must actually strike the two faces the game draws. Illumination of a face
# with outward normal n from light travelling along d is max(0, -n . d).
d = F.sun_travel_direction()
south_face, east_face = (0.0, -1.0, 0.0), (1.0, 0.0, 0.0)
north_face, west_face = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)


def lit(normal):
    return -sum(a * b for a, b in zip(normal, d))


check("light travels downward", 1.0 if d[2] < 0 else 0.0, 1.0)
check("south face is lit", 1.0 if lit(south_face) > 0 else 0.0, 1.0)
check("east face is lit", 1.0 if lit(east_face) > 0 else 0.0, 1.0)
check("north face is unlit", 1.0 if lit(north_face) <= 0 else 0.0, 1.0)
check("west face is unlit", 1.0 if lit(west_face) <= 0 else 0.0, 1.0)
# Vanilla's S is brighter than its E, and the ratio of the two cosine terms is what
# fixes the light's azimuth: tan(azimuth) = (E - ambient) / (S - ambient).
check("key favours south over east by the calibrated amount",
      math.atan2(lit(east_face), lit(south_face)) * 180 / math.pi,
      math.degrees(F.LIGHT_AZIMUTH_FROM_SOUTH), 1e-9)

print(f"\n{'ALL PASS' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
